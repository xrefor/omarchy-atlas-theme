# GHOSTLINE

GHOSTLINE is the ATLAS six-panel animated operations display. It is installed
with the `apps` component and runs entirely from the local theme payload.

The repository's `docs/media/atlas-ghostline.png` is concept artwork from the
original design pass, not a capture of this implementation. Its labels, version
number, addresses and operational data are fictional display content.

Start it with:

```bash
ghostline
```

Stop the director and every GHOSTLINE window on its workspace with either:

```bash
ghostline stop
ghostline kill
```

`kill` is a backwards-compatible alias for `stop`. Closing the last of the six
main panels also stops the director and dismisses any active overlay.

By default GHOSTLINE takes over workspace 2. Set
`ATLAS_GHOSTLINE_WORKSPACE` to a positive workspace number to use another:

```bash
ATLAS_GHOSTLINE_WORKSPACE=4 ghostline
```

Starting the display focuses its workspace and closes the existing unpinned
windows there before opening the six-panel wall. GHOSTLINE revalidates each
window's compositor address, process ID, class and workspace before closing it.
It never kills unrelated processes by name.

The larger equipment overlays are original terminal schematics: a centrifugal
booster-pump train and a generic instrumented inline pipeline-inspection tool.
They are display-only and do not control or query real equipment.

GHOSTLINE requires Alacritty, Hyprland's `hyprctl`, `jq`, Bash and Python 3.
When Bubblewrap is installed, renderer processes are launched without network
access. Director ownership state is kept in a private directory under
`$XDG_RUNTIME_DIR` and is removed with the login session.

Run `ghostline stop` before `atlas-theme restore`. Restoration removes the
installed launcher and runtime, so it cannot stop a display that was already
running after those files are gone.
