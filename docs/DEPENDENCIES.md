# Dependencies

The bundle installs appearance files, not application binaries or accounts.
Existing applications continue to use their own package managers and logins.

## Required

- Python 3.11+ (`tomllib` is used) and PyYAML (`python-yaml` on Arch).
- Omarchy with semantic `colors.toml`, `omarchy-theme-color`, Lua Hyprland config,
  Quickshell shell plugins, and the normal theme-set hooks.
- The `shell` component requires the command and PAM checks in [AUTH.md](AUTH.md).
- The `apps` component requires Bash, Foot, tmux, Starship and btop. Yazi is
  optional: its theme, drive menu and shortcuts are installed but remain dormant
  until Yazi is installed.

## Appearance and optional applications

- IBM Plex fonts (`ttf-ibm-plex`), a JetBrainsMono Nerd Font fallback, and Yaru icons.
  Fonts are external dependencies; no font binaries are redistributed.
- `spotify-player`, `lazygit`, `lazydocker`, and Zen Browser for their corresponding
  application integrations. Missing optional applications can be installed later.
- The Yazi drive menu uses `udisks2`, `lsblk`, `findmnt`, and Polkit. Omarchy's
  existing udiskie automount service is reused when installed.
- Network skins require their real commands: `nmap`, `iputils`, `iproute2`, `bind`,
  `tcpdump`, `metasploit`, or the official Shodan Python package as appropriate.
- The standalone Matrix screensaver uses `ttfx`, `jq`, and Omarchy's screensaver
  launcher. Matrix inside the lock screen is native QML/JavaScript.

Run `python3 install.py doctor --all` for a local prerequisite check. Install
missing packages with Omarchy's package commands; select only components that
match the applications you intend to use. Fonts and icons retain their package
licenses and are managed separately from this bundle.

## Optional NymVPN panel

The apps component includes `atlas-vpn`; using it requires a working NymVPN
daemon, a matching `nym-vpnc` CLI on PATH or in `~/.local/bin`, and Nym
authentication/account setup. Tested with 2026.12.2. Neither binary nor account
data is bundled. See [VPN.md](VPN.md). Nym is not required to install ATLAS.

## Building and validating the source

Rendering SVG artwork requires `rsvg-convert`. Tests additionally use Python
unittest, Lua, Bash, and Omarchy's plugin validator. If available, `qmllint`
checks the Quickshell files using the installed Omarchy import paths.
