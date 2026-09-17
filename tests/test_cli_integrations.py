import importlib.machinery
import importlib.util
import json
from pathlib import Path
import plistlib
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "components/cli"
sys.path.insert(0, str(CLI))


def load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


TCPDUMP = load_script("atlas_tcpdump", CLI / "integrations/tcpdump")


class IntegrationTests(unittest.TestCase):
    def test_tcpdump_wrapper_options_are_removed(self):
        mode, args = TCPDUMP.parse_wrapper_args(["--color=always", "-nn", "host", "192.0.2.1"])
        self.assertEqual(mode, "always")
        self.assertEqual(args, ["-nn", "host", "192.0.2.1"])

    def test_tcpdump_capture_modes(self):
        self.assertTrue(TCPDUMP.scan_tcpdump_args(["-w", "capture.pcap"])["write"])
        self.assertTrue(TCPDUMP.scan_tcpdump_args(["-wout.pcap"])["write"])
        self.assertTrue(TCPDUMP.scan_tcpdump_args(["-r", "capture.pcap"])["read"])
        self.assertTrue(TCPDUMP.scan_tcpdump_args(["-rinput.pcap"])["read"])
        self.assertTrue(TCPDUMP.scan_tcpdump_args(["-lnn"])["has_l"])

    def test_tcpdump_privilege_decision(self):
        live = TCPDUMP.scan_tcpdump_args(["-i", "eth0"])
        saved = TCPDUMP.scan_tcpdump_args(["-r", "capture.pcap"])
        with patch.object(TCPDUMP.os, "geteuid", return_value=1000):
            self.assertTrue(TCPDUMP.needs_privileges(live))
            self.assertFalse(TCPDUMP.needs_privileges(saved))
        with patch.object(TCPDUMP.os, "geteuid", return_value=0):
            self.assertFalse(TCPDUMP.needs_privileges(live))

    def test_install_map_is_safe_and_complete(self):
        manifest = json.loads((CLI / "install-map.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], 1)
        targets = set()
        for record in manifest["files"]:
            source = Path(record["source"])
            target = Path(record["target"])
            self.assertFalse(source.is_absolute())
            self.assertFalse(target.is_absolute())
            self.assertNotIn("..", source.parts)
            self.assertNotIn("..", target.parts)
            self.assertTrue((CLI / source).is_file(), source)
            self.assertIn(record["mode"], {"0644", "0755"})
            self.assertNotIn(str(target), targets)
            targets.add(str(target))
        self.assertIn(".local/lib/atlas-cli/atlas_cli/runner.py", targets)
        self.assertIn(".codex/themes/atlas.tmTheme", targets)
        self.assertIn(".codex/themes/atlas-readable.tmTheme", targets)
        self.assertNotIn(".local/bin/wifite", targets)
        self.assertNotIn(".local/bin/codex", targets)

    def test_reference_adapters_are_non_executable(self):
        wifite = CLI / "extras/wifite/theme.py"
        self.assertTrue(wifite.is_file())
        self.assertFalse(wifite.stat().st_mode & 0o111)
        compile(wifite.read_text(encoding="utf-8"), str(wifite), "exec")
        with (CLI / "extras/codex/atlas.tmTheme").open("rb") as source:
            self.assertEqual(plistlib.load(source)["name"], "ATLAS")
        with (CLI / "extras/codex/atlas-readable.tmTheme").open("rb") as source:
            self.assertEqual(plistlib.load(source)["name"], "ATLAS Readable")

    def test_sources_contain_no_legacy_or_machine_paths(self):
        checked = []
        for path in CLI.rglob("*"):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".py", ".md", ".rc", ".tmTheme", ""}
                and path.name != "install-map.json"
            ):
                checked.append(path.read_text(encoding="utf-8"))
        text = "\n".join(checked).lower()
        self.assertNotIn("blackburn", text)
        self.assertNotIn("graviton", text)

    def test_metasploit_resource_contains_no_key_material(self):
        resource = (CLI / "integrations/msfconsole.rc").read_text(encoding="utf-8").lower()
        self.assertNotIn("api_key", resource)
        self.assertNotIn("password", resource)
        self.assertIn("promptchar", resource)


if __name__ == "__main__":
    unittest.main()
