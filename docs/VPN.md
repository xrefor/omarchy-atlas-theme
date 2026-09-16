# ATLAS / NymVPN

The `apps` component installs `~/.local/bin/atlas-vpn` and binds **Ctrl+Space,
then N** in tmux. It opens a side pane in wide terminals and a window in narrow
ones. Repeat the shortcut to close it, or run `atlas-vpn` directly.

Requires Python with curses and a working NymVPN daemon with a matching
`nym-vpnc` CLI. This integration was tested against Nym 2026.12.2. Install Nym
through the optional `./install.sh` prompt, or follow the
[official Linux installation instructions](https://nym.com/download/linux).
The prompt installs the AUR `nym-vpnd-bin` and `nym-vpn-app-bin` packages.
When a daemon is installed but `nym-vpnc` is missing, a separate default-No
prompt offers the CLI from the [official Nym release](https://github.com/nymtech/nym-vpn-client/releases)
matching `nym-vpnd --version`. This also works when the daemon was installed
before ATLAS. The installer supports Linux x86_64 and aarch64, verifies the
archive against GitHub's published SHA-256 digest, and installs only the CLI to
`~/.local/bin/nym-vpnc`. Existing CLI installations are left untouched.
If the matching release or digest is unavailable, it reports the failure and
continues installing ATLAS. Retry with `python3 lib/atlas/optional.py`.
The downloaded CLI is separate from ATLAS theme restore and is not updated by
pacman; after a daemon upgrade, keep your CLI version aligned with it.
Complete daemon setup with `sudo systemctl enable --now nym-vpnd.service`
and set up your Nym account separately. The panel uses Nym's normal authentication
prompt and keeps one authenticated CLI session; it does not store credentials.

## Controls

| Key | Action |
| --- | --- |
| C / D | Connect / disconnect |
| M | Choose mode: 1 dVPN (two-hop WireGuard), 2 Mixnet; then view options |
| S | Current mode's settings |
| A in settings | Advanced options |
| Number keys | Toggle a setting or open its numeric editor |
| Enter / Escape in editor | Apply / cancel |
| Escape in menus | Back |
| R / I | Refresh / raw Nym details |
| Up / Down | Scroll |
| Q / Escape on dashboard | Close panel; VPN remains running |

The live tunnel reading is separate from the selected mode and timestamped
state history. Settings are read back before success is reported. Changing
mode or tunnel settings can reconnect an active tunnel.

- Common: IPv6.
- dVPN: circumvention transports; advanced Netstack (testing only, normally off).
- Mixnet advanced: loop-cover interval, per-mixnode delay, message-send interval,
  and Poisson timing. Turning Poisson timing off reduces timing randomization.
- Background cover traffic is read-only because this CLI has no setter.

`None` is displayed as **Auto (Nym default)**. Custom delays use milliseconds
(0–4294967295); zero means zero delay, not Auto. This CLI cannot reset custom
delays to Auto. Extreme values can substantially affect latency and bandwidth.

## Theme lifecycle

The panel uses the shared generated `~/.config/atlas/vpn-palette.json`, read on
opening, with an ATLAS fallback. `atlas-theme sync` updates that palette along
with other application colors. Reopen the panel to see new colors.

The normal bundle installer tracks the panel, palette and shortcut for restore,
including any pre-existing standalone panel. No Nym binaries, logs, accounts,
gateway addresses or device settings are packaged. Installation, synchronization
and restore do not connect/disconnect the VPN or change its service startup.
The workstation-specific Wi-Fi startup gate is not part of theme installation.

The bundle's copy in `components/apps/bin/atlas-vpn` is the maintained source.
Protocol tests are in `tests/test_vpn.py`; isolated UI tests in `tests/vpn_tmux.py`
use a fake CLI and never change the real VPN.
