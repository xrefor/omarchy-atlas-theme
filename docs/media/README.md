# ATLAS showcase media

## Responsive wallpaper previews

`previews/` contains WebP derivatives of the `backgrounds/*.png` files.
All eight PNG downloads are **3440 × 1440**. The website uses 160/320-pixel
thumbnail candidates and 640/1080/2160-pixel hero candidates.

On **2026-09-18**, seven wallpapers were rebuilt with AI image generation for
finer detail, then resized from the generator's approximately **1938 × 812**
output to exactly **3440 × 1440** using ImageMagick Lanczos resizing. These are
upscaled AI rerenders, not native 3440 × 1440 generations. ATLAS Boot retains
its existing 3440 × 1440 artwork.

Regenerate them with `python3 tools/build_previews.py` (Pillow with WebP support).
The generator uses Lanczos resizing and WebP quality 85; the current assets were
generated with Pillow 12.3.0 and libwebp 1.6.0. Commit the output with any changed
wallpaper source. If dimensions change, update the corresponding `srcset` and
`data-srcset` width descriptors in `index.html`.

`tools/build_site.py` stages and validates every responsive candidate and the
original downloads referenced by the wallpaper picker. The README uses these
previews for its wallpaper thumbnails, which link to the original PNG downloads.
Normal site builds use the committed previews and need only the Python standard
library.

## Current README and website · 2026-09-18

The current overview and workspace stills were captured on **2026-09-18** using
native applications on a temporary **1920 × 1080 headless Hyprland output at
1.25 scale**. They show the current Neovim readability, Yazi layout and preview,
and 100% default window opacity. The capture workspace used public tracked
repository files and [`palette.py`](palette.py), with no private project content.

Foot used its installed **IBM Plex Mono at 9 pt**, with the existing **8 pt Nerd
Font fallback**. No font override was applied. Process-specific capture-window
opacity was set to **100%**; the user's existing system setting remained **100%**,
and Zen's **100%** exception was unchanged.

Neovim used the current repository `neovim.lua`, the installed Aether plugin,
Aether's lualine theme and the installed Python Tree-sitter parser. Its temporary
capture configuration did not install plugins or edit the user's Neovim config.
Native installed Yazi used its **[1, 4, 3]** layout, matching syntax preview and
**T** to expand the preview.

The Agents and Nym panels use their **native installed production rendering with
explicitly labelled demonstration data**. A scratch capture helper feeds sample
agent tasks into the Agents UI and sample tunnel data into the VPN dashboard.
The VPN examples use documentation-only addresses. It runs no agent observer,
VPN backend, authentication, service command or connection action. The captures
show the interfaces; their sample status is not evidence of a live conversation
or VPN connection. Both the README and website disclose this distinction.

### Overview and stills

`atlas-overview.mp4` is a **20-second, silent, 1920 × 1080 H.264 video at 10 fps**.
`atlas-overview.gif` is the **1280 × 720, 10 fps** GIF version.

| Time | Scene |
| --- | --- |
| 0–3 seconds | Workspace hero: Neovim and Yazi's wallpaper preview |
| 3–8 seconds | Neovim with Python and TOML side by side |
| 8–11 seconds | Yazi's default layout with a code preview |
| 11–14 seconds | Yazi's expanded preview |
| 14–17 seconds | Agents panel with demonstration tasks |
| 17–20 seconds | Nym panel with demonstration tunnel status |

All new stills are frames from this recording:

| File | Use |
| --- | --- |
| `atlas-desktop.png` | Current workspace hero: Neovim and Yazi's wallpaper preview |
| `atlas-editor.png` | Neovim Python/TOML split and video poster |
| `atlas-files.png` | Yazi default layout with code preview |
| `atlas-agents.png` | Native Agents panel with demonstration tasks |
| `atlas-terminal.png` | Native Nym panel with demonstration status |

The applications were captured directly; no interface elements were composited
into the footage. The overview uses straight cuts between scenes. Source
wallpaper artwork is credited in [the project credits](../CREDITS.md).

## Lock-screen media

`atlas-lock.png` and `atlas-lock.gif` were recaptured on **2026-09-18** from
the current production `LockView.qml`, `MatrixRain.qml` and `MatrixModel.js`.
The temporary Quickshell wrapper enables Classic's screensaver state and captures
the native Qt Quick component directly with `grabToImage` at **1280 × 800**.
The production sources, palette, glyph size and animation remain unchanged;
the mouse pointer is excluded by capturing the component rather than the desktop.

The Matrix GIF repeats an **eight-second rain excerpt at 20 fps**, resampled from
the capture timestamps to preserve its recorded pace. The capture starts after a
two-second warm-up. It is a repeating excerpt of the randomized rain, not a full
rain-to-branding cycle or a seamless deterministic animation. The PNG is a still
from the same capture. These replace the older VM still in the showcase; no host
session was locked and this appearance preview is not an authentication test.

`atlas-lock-terminal.png` and `atlas-lock-terminal.gif` were recaptured on
**2026-09-18** from the current production `LockView.qml`, using Quickshell's
native Qt Quick renderer with the offscreen platform at **1280 × 800** and
**9 pt IBM Plex Mono**. The component source is unchanged. A temporary wrapper
selects Terminal style and captures the component directly with `grabToImage`,
so the compositor's mouse pointer is absent. This is an appearance preview,
not a new VM authentication test; no host session was locked.

The GIF loops one complete **1.2-second chevron cycle at 20 fps**: 500 ms visible,
100 ms fading out, 500 ms hidden, and 100 ms fading in, as defined by the native
animation. It uses 24 consecutive captured frames; the PNG is the first frame.
Only the chevron changes between frames. No interface elements were painted out
or composited into the capture. The website serves the PNG when
`prefers-reduced-motion: reduce` is enabled; the README also links the still.

Appearance media does not replace the authentication validation and limitations
recorded in [VALIDATION.md](../VALIDATION.md).

## Archived desktop recording · 2026-09-16

`atlas-desktop.mp4` is the retained **26-second, 1920 × 1080, 10 fps H.264 source
recording with no audio** from 2026-09-16. It supplied scenes for the previous
overview and is no longer used by the current README, website or refreshed media.

That recording shows Foot, tmux, Starship, Yazi and the Nym panel in a temporary
workspace using a public repository copy and the ATLAS Boot wallpaper. Foot used
IBM Plex Mono at 9 pt with the installed fallback. The temporary tmux status bar
omitted the hostname. Commands and tab navigation were automated against that
workspace, and scenes were joined with straight cuts.

Unlike the current demonstration-data panels, the archived Nym scene showed live
readings from the local daemon after authentication. It opened the mode menu
without changing the selected mode, settings or VPN connection. Authentication
and password entry were not recorded. The refreshed `atlas-terminal.png` comes
from the new demonstration-data recording, not this archived source.
