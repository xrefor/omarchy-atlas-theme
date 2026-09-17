# ATLAS agent panel

The apps component includes a read-only Codex agent dashboard. In the ATLAS Bash
workspace, launch `codex` normally: a panel opens when the conversation has an
active child agent. It lists nested agents from that conversation, with running,
waiting, completed, interrupted or error status, elapsed time and recent public
activity. Active agents appear before completed results. Successful agents stay
in the main list for 30 seconds after completion, then move into a collapsed
**Recently completed** section. Press **h** to show or hide those results.
Waiting, interrupted and failed agents remain visible; a resumed agent returns
to the main list automatically. Entries without a valid completion time also
stay visible.

Press **Ctrl+Space → a** to show or hide it. The panel uses 48 columns beside the
originating pane when there is room; on narrow terminals it opens a separate
`agents` window. Automatic opening keeps focus where you were typing. Use normal
tmux navigation to select it. **↑/↓** or **j/k** scroll, **h** toggles completed
history, **r** refreshes the view, and **q** closes it. Dismissed panels stay
closed for that Codex launch, unless you reopen them manually. Closing a panel
never interrupts an agent.

Reported plans show completed step counts when available. Activity and elapsed
time do not imply a completion percentage. The panel closes when its Codex
session exits or its originating tmux pane closes. Completed results remain
available through the manual toggle from the originating pane after the CLI
exits; an incomplete final observation is marked unknown.

## Palette and launch behavior

The panel inherits the terminal font, including the normal ATLAS 9 pt setting.
Its carbon background, orange accent, warm text and semantic status colors come
from `~/.config/atlas/agents-palette.json`, generated alongside the other app
themes. Theme synchronization updates this file; an open panel reloads it.
Terminals with 256-color support use the nearest available colors without
redefining terminal palette slots.

The managed Bash configuration adds a `codex` function only when no custom
function or alias already exists. When interface coloring is active, `atlas-codex`
places the observer launcher inside its terminal; that launcher replaces itself
with the actual Codex executable, so observation follows the CLI process rather
than the color adapter. Arguments pass through unchanged. Help, utility commands, noninteractive commands and remote clients do
not start an observer. `command codex` bypasses the function; setting
`ATLAS_AGENTS_AUTO=0` disables automatic observation for a launch.
`ATLAS_CODEX_COLORS=0` independently disables the interface-color adapter.

For Codex already running when ATLAS was installed, the toggle can attach from
its pane. From another terminal, use its exact pane and thread when necessary:

```bash
atlas-agents attach --pane %22 --thread THREAD_ID
atlas-agents toggle --pane %22
```

No Codex hooks, credentials, model settings or daemon configuration are changed.

## Local observer compatibility

The initial adapter is validated with **Codex CLI 0.154.0 on Linux**, including
its paginated-history JSONL lifecycle records. It reads the local `state_*.sqlite`
database in read-only mode and incrementally reads child session files. It
accepts non-forked legacy and paginated child sessions that omit
`subagent_history_start_ordinal`, waiting for a `task_started` event before
displaying activity. Forked sessions still require that boundary so copied
parent lifecycle events are skipped.

It identifies the root by the CLI process's open session file and follows only
that root's recorded descendants. It never selects a conversation by directory
or modification time. Automatic observation follows conversation changes within
the same CLI process, including new and resumed conversations. While the current
conversation cannot be identified, previous observations are marked stale. An
explicit `--thread` selection stays pinned. Ambiguous roots require an explicit
thread selection.

This is a version-sensitive local adapter, not a stable Codex API guarantee.
Unsupported schemas, missing records and disconnections produce an unavailable
or stale indicator. Database spawn-edge state alone is not treated as execution
status. Remote Codex sessions are outside this adapter's scope.

Only public assistant updates, execution lifecycle labels and reported plan
steps are displayed. Reasoning content, shell output, authentication files and
tool arguments are not displayed. The observer starts no agent turns and sends
no approvals or other commands to Codex. A lightweight observer exists only
while its CLI process is alive, identified by PID and process start time.

Snapshots and locks are private to the user under `$XDG_RUNTIME_DIR/atlas-agents`
(or `/tmp/atlas-agents-UID` when no private runtime directory exists). Snapshots
contain the short public activity shown in the panel. The installer journals
the command, Bash integration and palette for normal ATLAS restoration.
