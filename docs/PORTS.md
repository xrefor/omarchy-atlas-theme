# ATLAS Ports & Services panel

Ports & Services shows which local ports are listening and which processes own
them. It is included in the apps component. **Ctrl+Space → p** toggles the panel.
It follows the active Omarchy palette and the existing panels' layout: a sidebar
on wide terminals and a separate tmux window when space is limited.

## Controls

| Key | Action |
| --- | --- |
| **1** | TCP listeners (default) |
| **2** | UDP sockets |
| **3** | Both protocols |
| **/** | Edit the filter |
| Enter | Apply the edited filter |
| Ctrl+U while editing | Clear the filter text |
| Escape while editing | Cancel the edit |
| **a** | Retry desktop authorization for live administrator details |
| **r** | Refresh; leave administrator mode and resume ordinary user collection |
| **↑/↓**, **j/k**, Page Up/Down, Home/End | Scroll |
| **q**, Escape | Close when not editing |

Filtering is case-insensitive and matches port, address, process, service,
account or UID.
To clear a filter, press **/**, **Ctrl+U**, then Enter. Local data refreshes every
two seconds; the header marks incomplete results as **PARTIAL**.
Run `atlas-ports show` outside tmux, or `atlas-ports show --user` to skip the
initial authorization request and use ordinary user details.
`atlas-ports snapshot` prints a single ordinary user observation without an
authorization request. `atlas-ports toggle --pane PANE_ID` toggles the panel from
a specified tmux pane.

## Reading the panel

Each entry identifies its protocol, local address and port, with the owning
account and UID, process name, PID and systemd unit when available. Account
names come from local `/etc/passwd`; numeric UIDs remain visible when no local
name is found. Collection does not query remote account directories through NSS.
Units are inferred from the owning
process's Linux cgroup; they are context for the listener, not a service health
check. The panel lists sockets on this machine, not every installed service.

Loopback addresses accept local connections. Wildcard addresses bind across
interfaces, but do not prove that a port is reachable from another machine:
firewalls, routing and network configuration still apply. UDP entries describe
bound sockets; UDP does not use TCP's listening handshake.

Ordinary user collection uses `ss` without elevation and reads available
`/proc` metadata.
Other users' processes may be hidden, processes can exit between observations,
and some processes have no identifiable systemd unit. Restricted or unavailable
process details stay explicit; an unavailable query is reported rather than
shown as no listeners.

## Live administrator details

Opening the panel with **Ctrl+Space → p** or `atlas-ports show` automatically
requests authorization through the desktop Polkit popup. Approving enables
process details hidden from ordinary collection. Cancelling or unsuccessful
authorization leaves the panel available with ordinary user details and a
notice. Press **a** to retry, or start with `atlas-ports show --user` to skip the
initial request. The panel does not capture your password or run its interface
as root.

Administrator collection displays **ADMIN LIVE** and refreshes every two
seconds. Press **r** to stop administrator collection and return to ordinary
user details, or **q** to close. Ordinary collection also refreshes every two
seconds. Systemd units can still be unavailable because cgroup lookup remains
unprivileged.

This requires `pkexec` (Polkit) and a running desktop authentication agent. A
single authorized, isolated system Python reader runs fixed `ss` queries; the
popup may identify that system Python executable. Password entry stays in the
desktop authentication agent. The reader ends on close, after ten seconds without
a request, or after five minutes. If it ends, the panel returns to ordinary
collection without another popup; press **a** to authorize again. No system
authorization policy is installed or changed.

The panel does not scan hosts, probe web services, change firewall rules, stop
processes or control services. Closing it leaves the listed processes running.
Ordinary collection requires `iproute2` (`ss`), Linux `/proc` and Python's curses module; tmux
hosts the sidebar.
