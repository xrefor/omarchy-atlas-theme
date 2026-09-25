# Terminal layout

ATLAS provides two reversible presentation styles:

```bash
atlas-settings layout framed
atlas-settings layout classic
```

The same choice is available at **Omarchy → ATLAS → Terminal layout**. Classic
preserves the original terminal appearance and is the default when no preference
exists. Framed uses a divided tmux identity/header strip, ivory active-tab text
with a small orange locator and neutral pane dividers with focus arrows. Panels
use one continuous surface and perimeter, an attached heading with right-aligned
status when space permits, and an inset command footer. Agent tasks have thin
rectangular outlines, aligned fields, and solid cells for reported plan steps. Cells are
omitted if the complete plan cannot fit; numeric counts remain. Elapsed time
does not imply a completion percentage.

The desktop window border remains the terminal’s outer frame. Individual panels
have their own connected internal outline; no separate desktop window is added. The header’s lower rule uses
one additional terminal row; Classic restores the previous status height and
pane indicators. Agents, NymVPN, Git Status,
and Ports keep their existing opening, closing, scrolling, focus and resizing
behaviour. The usual sidebar widths and separate tmux-window fallback apply.
Closing a panel frees its space immediately. Small panes simplify decoration
to preserve content and controls.

The setting persists in `~/.config/atlas/layout.json` and
`~/.config/atlas/layout.conf`, through the installer restoration journal. Updates
and palette synchronization preserve it. Selecting a style refreshes the tmux
appearance configuration without reloading bindings or restarting sessions.
Open panels read the preference on their normal refresh. After a code update,
close and reopen panels once to load their new renderer; closing panels leaves
agents and VPN connections running.

To undo only the visual change, use `atlas-settings layout classic`. This does
not uninstall ATLAS or restore unrelated settings. If tmux rejects a live style
reload, the setting operation restores the previous preference and appearance.

## Framed panel content

Agents pair the task title with its role and the execution status with its
elapsed clock. Plan counts and step cells share a row when they fit. The stable
objective, distinct current activity and next named pending step explain purpose
and sequence. Press **p** to expand or collapse the reported named checklists;
missing plans are not invented.
Completed tasks retain their metadata and move into history after 30 seconds.
Git groups checkout state, changed files, commits and worktrees into framed
sections. Ports uses listener/service cards with separate address, scope, owner,
account and service fields. NymVPN groups connection, configuration, service and
history in cards, keeping the active route separate from the next connection's
settings. Unknown states remain explicit.

Cards use thin outlines on one continuous panel background. Borders, padding,
content and space between cards share that surface; no darker tile surrounds
the border and no shaded strip sits behind header or footer text. Content starts
directly inside the card border with one empty row between cards. All four
panels share the same inset and pinned header/footer renderer. Normal-width
footers split controls across readable rows; narrow views retain essential keys. Long lists scroll; small
terminals retain bounded rendering and controls. Classic remains available.
Files (Yazi) frames its native Parent, Files and Preview sections with dark
surfaces, warm headings and neutral borders. Native navigation, mouse handlers,
selection markers and syntax colors remain intact. `T` expands the preview and
restores the browsing proportions; the frames follow those proportions and
disappear in small layouts to preserve usable content. Yazi reads the shared
layout preference when it starts, so reopen Files after switching styles.
Classic uses its original manager layout. Setup occupies a marked block in
`~/.config/yazi/init.lua`, preserving existing user initialization.
Spotify retains its own TUI layout.
