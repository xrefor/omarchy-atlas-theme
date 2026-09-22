# ATLAS local panel suite

System, Projects and Maintain are read-only terminal panels included in the apps
component. They share the Nym and Agents presentation contract: a palette-aware
title strip, four pinned header rows, scrolling content, semantic colors, an
adaptive keyboard footer, a 60- or 48-column sidebar and a separate tmux window
when the originating pane is narrow. Closing a panel stops its collector and
does not stop, restart or modify anything it reports on.

| Shortcut | Panel | Local data |
| --- | --- | --- |
| **Ctrl+Space → o** | System | CPU, memory, root storage, load, network rates, thermals, battery and sampled process activity |
| **Ctrl+Space → g** | Projects | Originating directory, Git state, changed files, local ahead/behind counts, commits and worktrees |
| **Ctrl+Space → u** | Maintain | Running/installed kernel, failed system and user units, timers, local package-database upgrades and pacman transactions |
| **Ctrl+Space → m** | btop | Existing full-screen monitor; retained separately for deeper inspection |

Every panel supports **↑/↓** or **j/k**, Page Up/Page Down, Home/End, **r** to
refresh and **q** or Escape to close. Number keys select its pages. Toggling a
panel while it has focus resolves its exact originating pane, so it closes the
owned panel instead of nesting another one.

## Collection boundaries

System reads bounded Linux `/proc` and `/sys` data and the local filesystem API.
The process page uses sampled CPU counter deltas and the kernel's short process
name; command arguments are not displayed because they can contain secrets.

Projects runs bounded, time-limited Git commands with optional locks, pagers and
lazy fetching disabled. It reads no file contents and makes no network request.
A directory outside Git remains a useful, explicit empty state.

Maintain uses bounded, time-limited local commands and log reads. `pacman -Qu`
compares only the existing local sync database; the panel never runs
`checkupdates`, refreshes a database, invokes sudo, updates packages or changes a
systemd unit. Missing tools and partial observations remain visible as
unavailable rather than becoming healthy zeroes.

Run a panel without tmux using `atlas-system show`,
`atlas-projects show --path PATH`, or `atlas-maintain show`.
