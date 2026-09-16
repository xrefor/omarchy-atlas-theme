# ATLAS showcase media

## Current README and website

The approved overview is `atlas-overview.gif` / `atlas-overview.mp4`:

- 20 seconds, silent, with a 1920 × 1080 H.264 video and 1280 × 720 GIF at 10 fps.
- 0–2 seconds: desktop; 2–13: opening and navigating Python in Neovim;
  13–16: Yazi; 16–18: a brief Nym panel; 18–20: desktop.
- The Python scene was captured on 2026-09-16 in a temporary Foot/tmux workspace
  using the installed **IBM Plex Mono at 9 pt**, with its existing 8 pt Nerd Font
  fallback. No font override was applied. Preserve this size in future captures.
- Neovim uses the installed Aether plugin, the unmodified repository `neovim.lua`
  palette, the installed Python Tree-sitter parser, and Aether's lualine theme.
  Its temporary capture configuration does not install plugins or edit the user's
  Neovim configuration. `palette.py` is the demonstration source.
- `atlas-editor.png` is a still from that recording and the video poster.
- `atlas-lock.png` is an unchanged Omarchy VM validation capture of Matrix rain
  inside the lock surface. It is captioned as a VM capture in the showcase.

The remaining overview scenes use the original recording below, at source
24–26 seconds (desktop), 6–9 (Yazi), 1–3 (Nym), and 24–26 (desktop).
All interface elements are real captures; no UI was composited into the footage.

## rc5 additions

- `atlas-lock-terminal.png`: actual 1280 × 800 QEMU display capture of the
  packaged terminal lock on the Omarchy validation VM, 2026-09-16.
- `atlas-nutcracker.png`: headless Textual rendering of the packaged frontend
  at 100 × 32 cells, exported as SVG and rasterized. It is a UI preview, not a
  recording of an APK analysis or a physical terminal cursor.

## Original desktop recording

Recorded on 2026-09-16 with ATLAS active on Omarchy. These are real desktop
captures of Foot, tmux, Starship, the NymVPN panel, and Yazi. File browsing uses
a temporary copy of the public repository. Only the demonstration workspace
was captured.

- `atlas-desktop.gif`: 26-second silent loop, 1280 × 720, 10 fps.
- `atlas-desktop.mp4`: the same capture, 1920 × 1080, 10 fps, H.264, no audio.
- `atlas-terminal.png` and `atlas-files.png`: 1920 × 1080 stills from the capture.

The terminal uses the installed Foot configuration: IBM Plex Mono at 9 pt,
ATLAS colors, and a temporary tmux session. The hostname is omitted from that
session's status bar. The desktop uses the included ATLAS Boot wallpaper;
Yazi browses the included wallpaper collection. Commands and tab navigation
were automated against the demo session.

The Nym panel was opened with Ctrl+Space, then N, and authenticated before
recording. It shows live readings from the local daemon. The demo opens the
mode menu without changing the selected mode, settings, or VPN connection.
Authentication and password entry are not included in the recording.

The video joins the Nym and Yazi captures with straight cuts. The GIF is a
scaled, palette-optimized version of that video. No interface elements were
composited into the captures. The source wallpaper artwork is
credited in [the project credits](../CREDITS.md).
