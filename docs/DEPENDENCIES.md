# Dependencies

The bundle installs appearance files. The interactive `./install.sh` also offers
missing optional applications through Omarchy package commands, with a separate
default-No prompt for each. A separate prompt offers a missing `nym-vpnc` from
the official release matching the installed daemon, with SHA-256 verification.
Existing applications are skipped. Package failures
are reported without stopping theme installation. Accounts remain separate.
Dry runs, staged installs and noninteractive runs never install packages.
Run `python3 lib/atlas/optional.py` in a terminal to revisit the choices.

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

Rendering SVG artwork requires `rsvg-convert`. Portable tests use Python 3.11+,
PyYAML, Node.js, Lua, Bash, Git, tmux and the standalone `omarchy-theme-color`
resolver. CI checks Python 3.11 and 3.14 with Node.js 24, Lua 5.4 and PyYAML 6.0.3.
`tools/ci-deps.sh` can fetch a commit-pinned, checksum-verified Omarchy 4.0.4
resolver into a selected temporary directory; it does not install Omarchy.

The default checker additionally uses Omarchy's plugin validator, installed
Neovim plugins and `qmllint` with Quickshell/Omarchy imports when available.
Portable mode explicitly skips these desktop-specific checks. See
[validation commands and CI coverage](VALIDATION.md#portable-checks-and-ci).

Regenerating showcase wallpaper previews with `tools/build_previews.py` requires
Pillow with WebP support. The generated previews are committed, so ordinary
site staging, release builds and CI do not require Pillow.
