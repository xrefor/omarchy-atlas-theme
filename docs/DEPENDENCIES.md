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

## Optional Codex agent panel

The apps component also includes the optional [Codex agent panel](AGENT-PANEL.md).
Using it requires local Codex CLI 0.154.0, Linux `/proc`, tmux and Python's
standard-library curses/SQLite modules. Codex is not required to install ATLAS.
The observer does not add an API key, SDK dependency or Codex hook.

## Local ATLAS panels

The apps component includes the read-only [System panel](SYSTEM-PANEL.md). It
uses Python's standard library and Linux's existing `/proc` and `/sys`
interfaces; it adds no package, privileged helper, network request or
background service. tmux is used only to host the sidebar. btop remains a
separate full-screen tool and is not used to collect System-panel metrics.

The [Projects and Maintain panels](PANELS.md) use the same Python/tmux runtime.
Projects calls the installed Git command only against the originating pane's
local directory; it never fetches. Maintain reads systemd, the local pacman sync
database, the installed kernel modules and a bounded tail of the pacman log. It
never refreshes package databases, invokes sudo or changes a unit. These panels
add no package beyond the normal Omarchy tools they report on.

The same component includes the [Codex interface-color adapter](CLI.md#codex-interface-colors).
It uses Linux pseudo-terminals and Python's standard library; no additional
package or Codex modification is required. Its color mapping is based on the
Codex 0.154.0 interface. Native syntax colors still use the separate `/theme`
selection.

## Optional NymVPN panel

The apps component includes `atlas-vpn`; using it requires a working NymVPN
daemon, a matching `nym-vpnc` CLI on PATH or in `~/.local/bin`, and Nym
authentication/account setup. Tested with 2026.12.2. Neither binary nor account
data is bundled. See [VPN.md](VPN.md). Nym is not required to install ATLAS.

## Optional EVE Frontier panel

The apps component includes the read-only [EVE Frontier intelligence panel](FRONTIER.md).
It uses Python's standard library, tmux and a user-configured public Sui GraphQL
endpoint. No EVE account login, wallet extension, private key or additional SDK
is required. EVE Frontier and network access are not required to install ATLAS;
offline tests use fake transports and contain no account data.

## Building and validating the source

Rendering SVG artwork requires `rsvg-convert`. Portable tests use Python 3.11+,
PyYAML, Node.js, Lua, Bash, Git, tmux and the standalone `omarchy-theme-color`
resolver. CI checks Python 3.11 and 3.14 with Node.js 24, Lua 5.4 and PyYAML 6.0.3.
`tools/ci-deps.sh` can fetch a commit-pinned, checksum-verified Omarchy 4.0.4
resolver into a selected temporary directory; it does not install Omarchy.

The default checker additionally uses Quickshell for isolated monitor-panel
fixtures, Omarchy's plugin validator, installed Neovim plugins and `qmllint`
with Quickshell/Omarchy imports when available.
Portable mode explicitly skips these desktop-specific checks. See
[validation commands and CI coverage](VALIDATION.md#portable-checks-and-ci).

Regenerating showcase wallpaper previews with `tools/build_previews.py` requires
Pillow with WebP support. The generated previews are committed, so ordinary
site staging, release builds and CI do not require Pillow.
