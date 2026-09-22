# ATLAS System panel

The apps component includes `atlas-system`, a compact read-only view of the
machine beside the current tmux pane. Press **Ctrl+Space, then o** to toggle it.
On a wide terminal it opens as a 60- or 48-column sidebar; when the originating
pane is too narrow, it opens in a separate `system` window. Run
`atlas-system show` outside tmux for a normal full-window view.

The panel is deliberately narrower than a full system monitor. Its overview
keeps current CPU, load, memory, root-filesystem, network, thermal and battery
state visible while you work. A second page shows local processes ordered by
current sampled CPU activity, with resident memory use.
btop remains available when a full-screen process and resource explorer is the
better tool.

## Controls

| Key | Action |
| --- | --- |
| `1` | System overview |
| `2` | Processes |
| `↑` / `↓`, `j` / `k` | Scroll |
| `r` | Refresh immediately |
| `q` / Escape | Close the panel |

## Data and dependencies

`atlas-system` uses Python's standard library and Linux's existing `/proc` and
`/sys` interfaces. It does not install a metrics service, open a network
connection, request administrator access or retain history. Filesystem capacity
comes from the local filesystem API. Optional thermal and battery rows appear
only when the kernel exposes readable values.

Counters are sampled to calculate CPU and network activity. The first sample can
therefore show an initializing or unavailable rate instead of inventing a value.
An unreadable or disappearing process is skipped; an unavailable source is
reported without preventing the rest of the panel from updating. Process names
come from the kernel's short `comm` field. Command arguments are intentionally
not displayed because they can contain credentials or other private values.

The panel inherits the terminal font and reloads semantic colors from
`~/.config/atlas/system-palette.json` while open. Closing it stops collection and
does not change any process or system setting.

## Panel direction

Core ATLAS panels should remain useful on a normal Omarchy installation without
adding daemons or language SDKs. External-service panels, such as NymVPN or EVE
Frontier, stay optional and fail clearly when their own application or endpoint
is absent. Projects (tmux and Git context) and Maintain (locally known updates,
kernels, failed units and timers) now follow this rule. Aegis—an explicitly
observational local-exposure view—is the next candidate.
