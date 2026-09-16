# Release validation

This release candidate was prepared on the reference workstation and exercised
in a clean Omarchy 4.0.4 VM. Packaging did not change the workstation's active
desktop, application setup, authentication policy or boot configuration.

## Automated and isolated checks

Run `python3 tools/check.py` for the current test counts. It covers:

- Full user installation into temporary homes, repeat installation with no
  changes, palette synchronization and exact original-file restoration.
- Direct execution of installed application commands with mocked application
  backends, including execute permissions independent of source-file modes.
- Homes containing spaces and percent signs, browser profile discovery,
  preservation of existing application preferences and startup commands.
- Path traversal and symlink escape rejection, original symlink/mode recovery,
  user-edit protection, write-failure rollback and interrupted-install recovery.
- Authentication clone merging, rejection of competing custom clones,
  preservation of unrelated bar widgets and settings, and removal of the
  file-based askpass bridge from the distributed Polkit code.
- Boot transactions against simulated EFI partitions; preservation of boot
  entries, original appearance restoration, mocked rebuild failures, and
  boot-image/kernel-change recovery safeguards.
- CLI byte/exit/signal preservation, machine-readable output bypass and
  selected optional-integration behavior. Tests do not scan or capture traffic.
- Nym panel protocol, stale-status regression, mode/settings readback and invalid
  input checks; isolated tmux menu navigation and closing without disconnecting.
- Seven mocked Yazi drive-menu cases: authorization, clean removal, busy failure,
  internal-device rejection, argument handling, mounted siblings and optical media.
- Python, JSON, TOML, XML and shell syntax; four Omarchy plugin manifests;
  generated root theme files compared to their palette/templates.

The four shell clones additionally passed QML/JavaScript lint/syntax checks
against the installed Quickshell/Omarchy modules. An isolated tmux server loaded
the workspace configuration; its Ctrl+Space prefix and ATLAS status header were
queried successfully, and the private test server was removed afterward.

The final archive is extracted into a temporary directory and its internal
SHA256SUMS verified. The user installer is exercised from that extracted copy,
and the build is repeated to check deterministic archive output. Release files
must be tracked by Git and explicitly selected; bytecode, private state, backups,
logs, credentials, hardware layouts and account profiles are excluded.

## Before promoting the candidate to a stable release

Use a separate supported Omarchy installation or VM with a recoverable snapshot:

1. Check and install the user components; activate ATLAS and inspect the bar,
   launcher, windows, GTK apps, terminal, Yazi, browser and Spotify terminal UI.
2. Exercise a real lock/unlock and Polkit authorization with password input;
   check fractional scaling and optional fingerprint behavior on suitable hardware.
3. Install boot components, reboot, and inspect Limine, Plymouth disk unlock and
   SDDM where enabled. Confirm the successful boot using the documented command.
4. Change themes, update a kernel, then test boot and user restoration.
5. Exercise removable USB media (including busy files) and application workflows
   such as media playback and browser restart persistence.

The clean VM covers installation, reboot, password authentication, virtual USB
media and recovery logic. It does not validate physical firmware rendering,
GPU variation, fingerprint readers, encrypted Plymouth prompts, real Nym account
connectivity or every optional application version. The archive is suitable for
sharing as **1.0.0-rc4** with those limitations stated.
