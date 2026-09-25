# ATLAS Git Status panel

Git Status answers what remains before handing this checkout over to another
machine: uncommitted changes, unpushed commits, upstream changes and when the
remote was last checked. It is included in the apps component.

**Ctrl+Space → g** toggles Git Status for the originating pane's directory. The
directory is captured when the panel opens; close and reopen it after changing
repositories. A wide terminal gets a sidebar; a narrow one gets a separate tmux
window.

## Controls

| Key | Action |
| --- | --- |
| **1** | Handoff overview and changed files |
| **2** | Local commits and worktree paths |
| **f** | Check the configured upstream remote |
| **r** | Refresh local state without contacting the remote |
| **↑/↓**, **j/k**, Page Up/Down, Home/End | Scroll |
| **q**, Escape | Close |

Local data refreshes every two seconds. Toggling Git Status while it has focus
closes its owned panel. Run it outside tmux with
`atlas-projects show --path PATH`. The `snapshot --path PATH` command prints a
single local observation and does not contact a remote.

## Reading the handoff view

With **Terminal layout → Framed**, the header leads with the branch. The overview
then puts working-tree state, cached ahead/behind counts, remote-check outcome and
last successful check above changed files. Counts that could not be collected
show `UNKNOWN`; a failed remote check retains its separate last-success timestamp
and shows the latest attempt. The history page keeps the same summary, followed
by distinct local-commit and worktree cards. Each section uses a continuous panel
surface inside a neutral outline, with horizontal padding and space between
cards. The connected header and two-row controls share that same background. Long file paths wrap inside the cards; use scrolling for longer views.
**Classic** keeps the original presentation. Both layouts use the same pages,
shortcuts and collection behavior; changing layout never contacts a remote.

- Uncommitted changes include staged, unstaged and untracked files. Conflicts
  need attention before a handoff. A file can be both staged and unstaged;
  the changed-file total counts that file once.
- Unpushed and upstream counts compare this branch with its upstream ref. Until
  a successful remote check, these are cached local facts. If both counts are
  nonzero, the histories have diverged; Git Status does not reconcile them.
- The remote-check outcome and timestamp describe a check made by this open
  panel, not a promise that the remote has remained unchanged. Reopening starts
  with no verified remote check. Changing the branch or tracking identity
  invalidates the previous check.
- Missing upstreams, detached HEAD, failed queries and unavailable comparisons
  remain explicit. A failed query must not appear as a clean working tree or an
  empty history.

A clean checkout with no commits ahead or behind was aligned with its upstream
at the last successful check. Git Status does not inspect ignored files, validate
builds or CI, verify backups, or see another machine's uncommitted work. Worktree
history lists paths and branches, not each worktree's uncommitted changes.

## Remote checks

Pressing **f** fetches only the configured upstream branch into its remote-tracking
ref. This downloads Git objects and updates that ref; it does not modify working
files, stage changes, commit, push, merge, switch branches, prune refs or fetch
submodules. Ordinary refresh never fetches. Repeated keypresses while a check is
running do not start overlapping fetches, and navigation and closing remain
available.

Checks use the current user's Git credential helper or SSH configuration for
this repository. The theme does not ship an account, token, SSH key or login
session. Existing noninteractive access is reused; public HTTPS repositories
can usually be checked without signing in. Being signed into a browser or a
hosting-service CLI alone does not guarantee that Git is configured to use it.

The panel does not open a login prompt. Terminal credential prompts are
disabled; if access requires authentication, sign in through your normal Git
workflow in a terminal, then retry **f**. Local status remains available without
remote authentication. OpenSSH configuration and explicit SSH identity
arguments are preserved with batch mode enabled. Custom SSH commands must be
an executable plus arguments; shell pipelines and other SSH variants are
reported as unavailable. A timeout or failed check is shown as a failure,
even if an earlier successful timestamp exists. Remote checks and their
freshness are scoped to the selected branch and upstream.

Collection uses bounded output and time limits. Local queries disable optional
Git locks and lazy fetching. No persistent collector, account configuration or
background service is installed.
