import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from atlas import boot


BUNDLE = Path(__file__).resolve().parents[1]
BASE_LIMINE = """# local boot configuration
timeout: 7
default_entry: 2
hash_mismatch_panic: yes
interface_branding: Old machine
term_background: 000000

/Omarchy
    protocol: linux
    path: boot():/vmlinuz-linux
    cmdline: root=UUID=keep-me rw
"""


class BootInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "boot").mkdir()
        (self.root / "boot/limine.conf").write_text(BASE_LIMINE)
        (self.root / "etc/plymouth").mkdir(parents=True)
        (self.root / "etc/plymouth/plymouthd.conf").write_text(
            "[Daemon]\nTheme=previous\nShowDelay=1\n\n[Other]\nKeep=this\n"
        )
        (self.root / "etc/sddm.conf.d").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def args(self, action="boot", **overrides):
        values = dict(action=action, root=self.root, esp=None, dry_run=False,
                      limine=False, plymouth=False, sddm=False)
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_global_limine_merge_preserves_boot_policy_and_entries(self):
        values = boot._limine_values(BUNDLE)
        result = boot._edit_limine(BASE_LIMINE, values)
        self.assertIn("interface_branding: ATLAS Bootloader", result)
        self.assertIn("interface_branding_color: ff5a12", result)
        self.assertIn("term_background: 100e0c", result)
        self.assertIn("timeout: 7", result)
        self.assertIn("default_entry: 2", result)
        self.assertIn("hash_mismatch_panic: yes", result)
        self.assertEqual(result[result.index("/Omarchy"):], BASE_LIMINE[BASE_LIMINE.index("/Omarchy"):])
        self.assertNotIn("UUID=", result[:result.index("/Omarchy")])

    def test_staged_install_and_restore_preserve_later_entries_and_ini_keys(self):
        higher = self.root / "etc/sddm.conf.d/zzz-local.conf"
        higher.write_text("[Theme]\nCurrent=local-choice\n")
        output = io.StringIO()
        with mock.patch("atlas.boot.subprocess.run", side_effect=AssertionError("subprocess called")):
            with contextlib.redirect_stdout(output):
                boot.run(BUNDLE, self.args())
        self.assertIn("may override", output.getvalue())
        self.assertTrue((self.root / "usr/share/plymouth/themes/atlas/atlas.plymouth").is_file())
        self.assertTrue((self.root / "usr/share/sddm/themes/atlas/Main.qml").is_file())
        self.assertFalse((self.root / "usr/share/omarchy").exists())
        self.assertIn("Theme=atlas", (self.root / "etc/plymouth/plymouthd.conf").read_text())
        self.assertEqual((self.root / "etc/sddm.conf.d/zz-atlas-theme.conf").read_text(),
                         "[Theme]\nCurrent=atlas\n")
        installed = (self.root / "boot/limine.conf").read_text()
        self.assertIn("root=UUID=keep-me", installed)
        self.assertIn("hash_mismatch_panic: yes", installed)
        self.assertIn("ATLAS Bootloader", installed)
        boot.run(BUNDLE, self.args("boot-confirm"))

        # Simulate a kernel update and an unrelated local Plymouth edit after install.
        (self.root / "boot/limine.conf").write_text(
            installed.replace("path: boot():/vmlinuz-linux", "path: boot():/vmlinuz-linux-new") +
            "\n/New kernel\n    protocol: efi\n    path: boot():/EFI/Linux/new.efi\n"
        )
        plymouth = self.root / "etc/plymouth/plymouthd.conf"
        plymouth.write_text(plymouth.read_text().replace("ShowDelay=1", "ShowDelay=9") + "LocalKey=preserve\n")
        with mock.patch("atlas.boot.subprocess.run", side_effect=AssertionError("subprocess called")):
            boot.run(BUNDLE, self.args("boot-restore"))
        restored = (self.root / "boot/limine.conf").read_text()
        self.assertIn("interface_branding: Old machine", restored)
        self.assertIn("term_background: 000000", restored)
        self.assertNotIn("ATLAS APPEARANCE", restored)
        self.assertIn("vmlinuz-linux-new", restored)
        self.assertIn("/New kernel", restored)
        restored_ini = plymouth.read_text()
        self.assertIn("Theme=previous", restored_ini)
        self.assertIn("ShowDelay=9", restored_ini)
        self.assertIn("LocalKey=preserve", restored_ini)
        self.assertFalse((self.root / "usr/share/plymouth/themes/atlas/atlas.plymouth").exists())
        self.assertFalse((self.root / "usr/share/sddm/themes/atlas/Main.qml").exists())
        self.assertFalse((self.root / "var/lib/atlas-bundle/boot-state.json").exists())

    def test_rc3_sddm_selector_is_migrated_to_winning_name(self):
        old = Path("/etc/sddm.conf.d/99-atlas-theme.conf")
        with mock.patch.object(boot, "SDDM_SELECTOR", old):
            boot.run(BUNDLE, self.args(sddm=True))
            boot.run(BUNDLE, self.args("boot-confirm"))
        self.assertTrue((self.root / old.relative_to('/')).is_file())
        boot.run(BUNDLE, self.args(sddm=True))
        self.assertFalse((self.root / old.relative_to('/')).exists())
        self.assertTrue((self.root / "etc/sddm.conf.d/zz-atlas-theme.conf").is_file())

    def test_dry_run_does_not_write_or_call_subprocess(self):
        original = (self.root / "boot/limine.conf").read_bytes()
        with mock.patch("atlas.boot.subprocess.run", side_effect=AssertionError("subprocess called")):
            status = boot.run(BUNDLE, self.args(dry_run=True))
        self.assertEqual(status, 0)
        self.assertEqual((self.root / "boot/limine.conf").read_bytes(), original)
        self.assertFalse((self.root / "usr").exists())
        self.assertFalse((self.root / "var").exists())

    def test_ambiguous_esp_requires_explicit_choice(self):
        (self.root / "efi").mkdir()
        (self.root / "efi/limine.conf").write_text(BASE_LIMINE)
        with self.assertRaisesRegex(ValueError, "Multiple ESP"):
            boot.run(BUNDLE, self.args(limine=True, dry_run=True))
        status = boot.run(BUNDLE, self.args(limine=True, dry_run=True, esp=Path("/boot")))
        self.assertEqual(status, 0)

    def test_symlink_escape_and_traversal_are_rejected(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        try:
            (self.root / "usr").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                boot.run(BUNDLE, self.args(sddm=True, dry_run=True))
            with self.assertRaises(ValueError):
                boot._rooted(self.root, Path("/../escape"))
        finally:
            outside.rmdir()

    def test_edited_managed_asset_is_preserved_and_restore_refuses(self):
        boot.run(BUNDLE, self.args(sddm=True))
        boot.run(BUNDLE, self.args("boot-confirm"))
        asset = self.root / "usr/share/sddm/themes/atlas/Main.qml"
        asset.write_text("local edit\n")
        with self.assertRaisesRegex(ValueError, "Preserving a later edit"):
            boot.run(BUNDLE, self.args("boot-restore", sddm=True))
        self.assertEqual(asset.read_text(), "local edit\n")

    def test_mocked_rebuild_failure_rolls_back_config_and_generated_images(self):
        esp = self.root / "boot"
        config = esp / "limine.conf"
        image = esp / "EFI/Linux/current.efi"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"old-signed-image")
        state_path = self.root / "var/lib/atlas-bundle/boot-state.json"
        changed = boot._file_value("changed config\n")
        new_state = {"version": 1, "components": ["plymouth"], "files": {}, "selectors": {}}

        def failing_rebuild():
            image.write_bytes(b"partly-rebuilt")
            (esp / "EFI/Linux/new.efi").write_bytes(b"new-generation")
            raise RuntimeError("mock rebuild failed")

        with self.assertRaisesRegex(RuntimeError, "mock rebuild failed"):
            boot._commit(self.root, esp, [(config, changed)], state_path, new_state,
                         rebuild=failing_rebuild)
        self.assertEqual(config.read_text(), BASE_LIMINE)
        self.assertEqual(image.read_bytes(), b"old-signed-image")
        self.assertFalse((esp / "EFI/Linux/new.efi").exists())
        self.assertFalse(state_path.exists())

    def test_restore_rebuilds_from_current_state_instead_of_saved_uki(self):
        boot.run(BUNDLE, self.args(plymouth=True))
        boot.run(BUNDLE, self.args("boot-confirm"))
        image = self.root / "boot/EFI/Linux/current.efi"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"kernel-upgrade")
        boot.run(BUNDLE, self.args("boot-restore", plymouth=True))
        self.assertEqual(image.read_bytes(), b"kernel-upgrade")

    def test_completed_checkpoint_blocks_writes_until_confirmed(self):
        boot.run(BUNDLE, self.args(sddm=True))
        transaction = boot._active_transaction(self.root)
        self.assertIsNotNone(transaction)
        journal = json.loads((transaction / "journal.json").read_text())
        self.assertEqual(journal["status"], "completed")
        with self.assertRaisesRegex(ValueError, "boot-confirm"):
            boot.run(BUNDLE, self.args(sddm=True))
        boot.run(BUNDLE, self.args("boot-confirm"))
        self.assertIsNone(boot._active_transaction(self.root))
        self.assertEqual((self.root / "var/lib/atlas-bundle").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "var/lib/atlas-bundle/boot.lock").stat().st_mode & 0o777, 0o600)

    def test_completed_recovery_restores_pretransaction_state(self):
        original = (self.root / "boot/limine.conf").read_text()
        boot.run(BUNDLE, self.args(limine=True))
        self.assertIn("ATLAS Bootloader", (self.root / "boot/limine.conf").read_text())
        boot.run(BUNDLE, self.args("boot-recover"))
        self.assertEqual((self.root / "boot/limine.conf").read_text(), original)
        self.assertFalse((self.root / "var/lib/atlas-bundle/boot-state.json").exists())

    def test_completed_recovery_preserves_unrelated_esp_drift(self):
        boot.run(BUNDLE, self.args(limine=True))
        later = self.root / "boot/EFI/Linux/later.efi"
        later.parent.mkdir(parents=True)
        later.write_bytes(b"later rebuild")
        empty = self.root / "boot/keep-empty"
        empty.mkdir()
        boot.run(BUNDLE, self.args("boot-recover"))
        self.assertEqual(later.read_bytes(), b"later rebuild")
        self.assertTrue(empty.is_dir())
        self.assertEqual((self.root / "boot/limine.conf").read_text(), BASE_LIMINE)

    def test_completed_recovery_refuses_drift_in_an_atlas_touched_esp_file(self):
        boot.run(BUNDLE, self.args(limine=True))
        (self.root / "boot/limine.conf").write_text("recipient edit\n")
        with self.assertRaisesRegex(ValueError, "ESP file changed"):
            boot.run(BUNDLE, self.args("boot-recover"))

    def test_completed_recovery_rejects_unsafe_journal_esp_path(self):
        boot.run(BUNDLE, self.args(limine=True))
        transaction = boot._active_transaction(self.root)
        journal_path = transaction / "journal.json"
        journal = json.loads(journal_path.read_text())
        journal["esp_after"]["/victim"] = "0" * 64
        journal_path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError, "Unsafe completed ESP manifest"):
            boot.run(BUNDLE, self.args("boot-recover"))
        journal["esp_after"].pop("/victim")
        journal["esp_after"]["."] = "0" * 64
        journal_path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError, "Unsafe completed ESP manifest"):
            boot.run(BUNDLE, self.args("boot-recover"))

    def test_completed_recovery_rejects_unsafe_change_and_state_paths(self):
        boot.run(BUNDLE, self.args(limine=True))
        transaction = boot._active_transaction(self.root)
        journal_path = transaction / "journal.json"
        journal = json.loads(journal_path.read_text())
        journal["changes"].append({"path":"/victim","before":{"kind":"absent"},
                                   "after":{"kind":"absent"}})
        journal_path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError, "Unsafe boot transaction change path"):
            boot.run(BUNDLE, self.args("boot-recover"))
        journal["changes"].pop()
        journal["state_path"] = "/victim"
        journal_path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError, "Unsafe boot transaction state path"):
            boot.run(BUNDLE, self.args("boot-recover"))

    def test_prepared_checkpoint_recovers_interrupted_rebuild(self):
        esp = self.root / "boot"
        config = esp / "limine.conf"
        state_path = self.root / "var/lib/atlas-bundle/boot-state.json"
        new_state = {"version": 1, "components": ["limine"], "files": {}, "selectors": {}}
        transaction, _ = boot._prepare_transaction(
            self.root, esp, [(config, boot._file_value("attempted\n"))], state_path, new_state
        )
        config.write_text("attempted\n")
        generated = esp / "EFI/Linux/partial.efi"
        generated.parent.mkdir(parents=True)
        generated.write_bytes(b"partial")
        boot.run(BUNDLE, self.args("boot-recover"))
        self.assertEqual(config.read_text(), BASE_LIMINE)
        self.assertFalse(generated.exists())
        self.assertFalse(transaction.exists())

    def test_selector_and_limine_appearance_edits_are_preserved(self):
        boot.run(BUNDLE, self.args(plymouth=True))
        boot.run(BUNDLE, self.args("boot-confirm"))
        conf = self.root / "etc/plymouth/plymouthd.conf"
        conf.write_text(conf.read_text().replace("Theme=atlas", "Theme=local"))
        with self.assertRaisesRegex(ValueError, "later edit"):
            boot.run(BUNDLE, self.args("boot-restore", plymouth=True))
        self.assertIn("Theme=local", conf.read_text())

        # A separate root avoids the deliberately preserved Plymouth drift.
        self.tearDown()
        self.setUp()
        boot.run(BUNDLE, self.args(limine=True))
        boot.run(BUNDLE, self.args("boot-confirm"))
        limine = self.root / "boot/limine.conf"
        limine.write_text(limine.read_text().replace("ATLAS Bootloader", "LOCAL Bootloader"))
        with self.assertRaisesRegex(ValueError, "later edit"):
            boot.run(BUNDLE, self.args("boot-restore", limine=True))
        self.assertIn("LOCAL Bootloader", limine.read_text())

    def test_backup_capacity_is_checked_before_mutation(self):
        original = (self.root / "boot/limine.conf").read_text()
        usage = SimpleNamespace(total=1, used=1, free=0)
        with mock.patch("atlas.boot.shutil.disk_usage", return_value=usage):
            with self.assertRaisesRegex(OSError, "Insufficient backup storage"):
                boot.run(BUNDLE, self.args(limine=True))
        self.assertEqual((self.root / "boot/limine.conf").read_text(), original)

    def test_enrollment_effective_literals_and_complex_values(self):
        dropins = self.root / "etc/limine-entry-tool.d"
        dropins.mkdir(parents=True)
        (dropins / "10-base.conf").write_text('ENABLE_ENROLL_LIMINE_CONFIG="yes"\n')
        self.assertTrue(boot._enrollment_enabled(self.root))
        defaults = self.root / "etc/default"
        defaults.mkdir(parents=True)
        (defaults / "limine").write_text("ENABLE_ENROLL_LIMINE_CONFIG=no\n")
        self.assertFalse(boot._enrollment_enabled(self.root))
        (defaults / "limine").write_text("ENABLE_ENROLL_LIMINE_CONFIG=$(probe)\n")
        with self.assertRaisesRegex(ValueError, "Complex"):
            boot._enrollment_enabled(self.root)


if __name__ == "__main__":
    unittest.main()
