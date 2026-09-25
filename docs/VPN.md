# ATLAS / NymVPN

[NymVPN](https://nym.com/) is an open-source, decentralized VPN developed by
[Nym Technologies SA](https://nym.com/trust-center) in Switzerland. Its Fast mode
uses two-hop WireGuard routing; its Mixnet mode routes traffic through five hops,
adding cover traffic and packet mixing to obscure traffic patterns, with higher
latency. See Nym's [explanation of the two modes](https://support.nym.com/hc/en-us/articles/24326365096721-What-s-the-difference-between-NymVPN-Fast-Anonymous-mode).
ATLAS provides an optional themed terminal panel for the service.

The `apps` component installs `~/.local/bin/atlas-vpn` and binds **Ctrl+Space,
then N** in tmux. Like the Agents panel, it prefers a 60-column side pane when
the originating pane has at least 141 columns. It uses 48 columns for origins
of 130–140 columns, or a separate window below that. Manual resizing remains
available. Repeat the shortcut to close it, or run `atlas-vpn` directly.

Requires Python with curses. Tunnel controls require a running NymVPN daemon
with a matching `nym-vpnc` CLI; service setup is available even without the CLI.
This integration was tested against Nym 2026.12.2. Install Nym
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
The panel detects whether `nym-vpnd.service` is running and enabled at boot.
When setup is needed it opens the service page, which also remains available
with **B**. Choose **1** to start the service for this session or **2** to enable
it at boot and start it now. Review the confirmation and press **Y** to proceed;
the panel temporarily leaves its interface for the normal `sudo` password prompt.
It reads the service state back before reporting success, then opens the Nym app
as your normal user so you can log in or sign up. **O** opens the app again when
needed. Opening the panel alone does not enable the service or launch the app.

Missing, masked or unavailable services are reported rather than installed or
unmasked automatically. A missing app or CLI is reported with setup guidance.
Account setup remains in Nym's app; ATLAS does not read or store account secrets.
The panel uses Nym's normal authentication
prompt and keeps one authenticated CLI session; it does not store credentials.

## Controls

| Key | Action |
| --- | --- |
| C / D | Connect / disconnect |
| B / O | Service setup / open Nym app for account setup |
| 1 / 2 on service page | Start once / enable at boot and start, after confirmation |
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

The **Framed** layout pins the reported connection state and short active mode
in its header, then leads with **ACTIVE TUNNEL MODE**. It identifies dVPN or
Mixnet only when Nym's connected status explicitly reports `wg` or `mix`.
A disconnected tunnel shows no active mode;
transitions show **NOT CONFIRMED**, and incomplete or unfamiliar readings show
**UNKNOWN**. It never substitutes the selected setting for the active mode.
The dashboard groups connection and live route, next-connection settings, service,
notices, and history into outlined sections with horizontal padding, all on the
same continuous background. Fields
use aligned continuations inside each card when the pane narrows. Optional raw
details have their own card. **NEXT CONNECTION / CONFIGURATION** separates
the selected mode and gateway policy from that live reading; these settings
can differ during reconnection. Existing settings pages and controls are
unchanged, as is the **Classic** presentation.

- Common: IPv6.
- dVPN: circumvention transports; advanced Netstack (testing only, normally off).
- Mixnet advanced: loop-cover interval, per-mixnode delay, message-send interval,
  and Poisson timing. Turning Poisson timing off reduces timing randomization.
- Background cover traffic is read-only because this CLI has no setter.

`None` is displayed as **Auto (Nym default)**. Custom delays use milliseconds
(0–4294967295); zero means zero delay, not Auto. This CLI cannot reset custom
delays to Auto. Extreme values can substantially affect latency and bandwidth.

## Theme lifecycle

The panel uses the generated `~/.config/atlas/vpn-palette.json`, with the same
semantic colors and ATLAS fallback as Agents. `atlas-theme sync` updates both
palettes along with other application colors; open panels reload them. Terminal
color slots are not redefined. Framed panels share a continuous background, connected header and perimeter,
content inset, outlined sections and neutral pinned keyboard-hint footer. Nym's controls wrap
to fit the pane, and its title remains visible while the content scrolls.
Status fields move as complete label/value groups when resized; long individual
values use aligned continuation lines. Dashboard shortcuts appear in the footer
instead of being repeated inside those fields.

The normal bundle installer tracks the panel, palette and shortcut for restore,
including any pre-existing standalone panel. No Nym binaries, logs, accounts,
gateway addresses or device settings are packaged. Installation, synchronization
and restore do not connect/disconnect the VPN or change its service startup.
Explicit service actions in the panel can start or enable the daemon. They do
not send a VPN connect command; Nym may apply its own existing autoconnect policy
when started. The workstation-specific Wi-Fi startup gate is not part of theme
installation.

The bundle's copy in `components/apps/bin/atlas-vpn` is the maintained source.
Protocol tests are in `tests/test_vpn.py`; isolated UI tests in `tests/vpn_tmux.py`
use a fake CLI and never change the real VPN.
