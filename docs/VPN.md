# ATLAS / NymVPN

The `apps` component installs `~/.local/bin/atlas-vpn` and binds **Ctrl+Space,
then N** in tmux. It opens a side pane in wide terminals and a window in narrow
ones. Repeat the shortcut to close it, or run `atlas-vpn` directly.

Requires Python with curses and a working NymVPN daemon with a matching
`nym-vpnc` CLI. This integration was tested against Nym 2026.12.2. Install Nym
and set up its account separately. The panel uses Nym's normal authentication
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
