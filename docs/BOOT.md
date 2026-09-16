# ATLAS boot and login integration

Boot integration is an explicit, privileged part of the bundle. It is not
included by the user-level `--all` option and it never invokes `sudo` or
`pkexec` itself. Review a dry run, then run the explicit boot command from an
interactive terminal with `sudo`.

```console
sudo python3 install.py boot --dry-run
sudo python3 install.py boot
```

With no component flags, the command installs all three integrations. Use
`--limine`, `--plymouth`, or `--sddm` to select a subset. If more than one of
`/boot`, `/efi`, and `/boot/efi` contains `limine.conf`, specify the target
with `--esp /path`. The path must be the mounted ESP containing the active
Limine configuration.

The installer applies only these system paths:

- `/usr/share/plymouth/themes/atlas` and the `Theme` key in
  `/etc/plymouth/plymouthd.conf`;
- `/usr/share/sddm/themes/atlas` and the dedicated selector
  `/etc/sddm.conf.d/zz-atlas-theme.conf`;
- ATLAS branding and palette keys in the global section of the ESP's existing
  `limine.conf`.

The Limine merge preserves boot entries, disk paths, UUIDs, kernel command
lines, timeout/default selection, config-hash policy, verification policy, and
enrollment policy. The bundle does not copy the source computer's boot
configuration. Colours come from the bundle's `colors.toml`. A later SDDM
selector or `/etc/sddm.conf` is reported because it may override ATLAS; the
installer preserves that local policy rather than deleting it.

Plymouth changes are followed by `limine-mkinitcpio`, which rebuilds images for
the kernels installed at that time. Before any boot config edit or rebuild, the
installer checks backup capacity, copies the current ESP, and persists a private
journal under `/var/lib/atlas-bundle/transactions/`. If a rebuild or enrollment
step fails, the config, generated images, theme files, and selectors are rolled
back together. If Limine config
enrollment is already enabled, the edited config is re-enrolled through the
installed Limine tooling; Secure Boot signing and verification settings are
left to that tooling and are never weakened.

The successful transaction and its backup remain until the first reboot has
been reviewed. This also makes an abrupt power loss or killed installer
recoverable. After a successful boot, acknowledge and remove the checkpoint:

```console
sudo python3 install.py boot-confirm
```

Do not confirm before rebooting: confirmation deletes the recovery backup and
does not activate the theme. New live installations refuse confirmation in the
same boot session. If ATLAS is missing after reboot, keep the checkpoint while
investigating. “No ATLAS boot recovery checkpoint” means there is no pending
backup, for example because it was already confirmed; it does not verify the
installed appearance.

If the new boot appearance fails, boot a working entry or chroot into the
installed system with its ESP mounted at the same recorded path, and run:

```console
sudo python3 install.py boot-recover
```

Recovery verifies the journal, managed selectors/files and kernel fingerprint.
For a completed transaction it restores only ESP files changed by ATLAS, while
preserving unrelated boot-time changes such as a refreshed random seed or new
unrelated files. It refuses if an ATLAS-touched ESP file, kernel set, or managed
appearance path was changed later. New boot writes remain locked out until the
checkpoint is confirmed or recovered.

To remove the integrations, select the same components or omit flags to remove
all installed boot components:

```console
sudo python3 install.py boot-restore
```

Restoration puts back the original appearance and selector values while
preserving later kernel entries and unrelated INI/global settings. Plymouth is
then rebuilt using the current kernels. Old UKIs from installation time are
used only for rollback during that transaction and are never restored as the
normal removal method. Review that reboot and run `boot-confirm` again.

Unsupported cases are refused before mutation: non-Limine ESPs, ambiguous ESP
detection, symlinks or special files in managed paths/the ESP, a missing
`limine-mkinitcpio`, and hand-edited bundle-managed theme assets. Multi-ESP
systems require `--esp`; the installer does not guess which copy firmware uses.
Staged roots are supported for package tests and perform no subprocess calls.
All non-dry boot operations are serialized by a private
`/var/lib/atlas-bundle/boot.lock` file.
