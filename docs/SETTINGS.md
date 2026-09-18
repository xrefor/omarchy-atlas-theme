# ATLAS settings

Open **Omarchy → ATLAS**, or run `atlas-settings`. Installation adds a marked
block to `~/.config/omarchy/extensions/omarchy-menu.jsonc`, preserving other menu
entries and comments. Omarchy reloads the extension automatically.

| Control | Behavior |
| --- | --- |
| Wallpaper | Opens Omarchy's image picker for the active theme and user backgrounds. Cancelling leaves the current wallpaper alone. |
| Window opacity | Offers 80%, 87%, 95%, or 100% (ATLAS default, fully opaque); the current preset gets a checkmark. Zen Browser stays fully opaque at every preset. Fullscreen and existing app exceptions keep their own rules. |
| Lock screen | Selects Classic or Terminal for the next lock; shown when the shell component is installed. |
| Neovim comments | Selects Standard or Brighter comments in the ATLAS Aether integration. The choice applies when Neovim regains focus or reloads its colorscheme. |
| Component status | Shows the active theme, configured Foot font, wallpaper, opacity, and installer-managed or separately detected components. |
| Diagnostics | Compares local files with saved snapshots and reports interrupted transactions and application availability. No uploads or privileged commands. |
| Shortcuts & help | A compact guide to the terminal workspace and file navigation. |
| Restore managed files | Lists affected files, requires another active theme, runs a dry-run, and asks for `RESTORE` before applying. Enter cancels. |

The font is not an adjustable preset here: normal ATLAS typography remains 9 pt.

The desktop component keeps **Super+T** as the tile/float toggle. Switching a
tiled window to floating sizes it to **75% of its monitor's width and height**
and centers it. Monitor scaling and rotation are accounted for. Pressing the
shortcut again returns the window to tiling. Applications can impose their own
minimum or maximum window size.

With the optional `cli-codex` integration installed, Codex's native `/theme`
picker also offers **ATLAS Readable**. This preset uses a brighter warm gray for
code comments. Select **ATLAS** to return to the standard comment color; Codex
persists the selection. See [the CLI presets](CLI.md#optional-integrations).

For Neovim, choose **Omarchy → ATLAS → Neovim comments → Brighter**, or run
`atlas-settings readability readable`. Return with `atlas-settings readability
standard`. The standard preset remains the default. Existing Neovim windows
refresh when they regain focus; `:colorscheme aether` also applies the choice.
The setting only affects Aether's ordinary comments, including linked Treesitter
comments; TODO/error annotations, syntax colors and comment italics retain their
existing styles. Other Neovim colorschemes keep their own appearance.

Neovim's standard comments now use 65% foreground mixed with 35% background
(`#918b84` on ATLAS). Brighter comments use 75% foreground and 25% background
(`#a59f96`). Both follow the active Omarchy palette. Line numbers, inlay hints,
code lenses and punctuation use the standard secondary text color; decorative
borders keep the darker muted color. The CLI's separate readable preset uses
`#a69b8c`. These are comment presets, not a whole-desktop accessibility mode;
font sizes stay unchanged.

## Configuration and restoration

Opacity is read from the existing ATLAS all-window rule in `looknfeel.lua` or
`hyprland.lua`; there is no second preference store. Ambiguous/custom rules are
left for manual review. New installations default to 100%; updates retain the
selected opacity. The control checks
Hyprland before and after changing the rule and rolls back if validation fails.
It changes focused and unfocused opacity together, keeping fullscreen at 100%.

Neovim's choice is stored in `~/.config/atlas/neovim-readability`. Bundle updates
and palette changes preserve it. It uses the same restoration journal as other
settings; restoring removes a newly created preference or restores its original
value. Use the menu or command to change it without creating manual-file drift.

All managed changes use `~/.local/state/atlas-bundle/`. Original snapshots remain
available across repeated setting changes. Later edits to a managed file block
updates and restoration; save and reconcile them before proceeding.

Existing desktops may have ATLAS components installed outside the bundle. Status
labels these separately: detection does not claim installer ownership. Restore
only covers files listed in the journal, not every detected component. Existing
legacy theme hooks should be migrated with [MIGRATION.md](MIGRATION.md) before a
full bundle install.

After restoration, log out and back in. Running desktop processes can retain
the old `FONTCONFIG_FILE` environment value after its managed file is removed;
opening another terminal within that same session does not always clear it.

```bash
atlas-settings status
atlas-settings diagnostics
atlas-settings opacity 100
atlas-settings readability readable
atlas-settings restore
```

Reports support `--pause` for menu-launched terminals. `--home` supports isolated
staging; it never reloads the live compositor when selecting a different home.

## Editor consistency

The shared Aether templates style Neo-tree, Snacks pickers and input dialogs,
Blink completion, Noice command/search dialogs, Which-key help and native popup
surfaces. Orange marks navigation and focus; ivory carries ordinary text.
Functions and methods use steel blue, types use amber, constants use bright
amber, strings use olive, and parameters use sage. Completion-kind icons follow
the same roles as code. Keywords retain terracotta and numbers retain ember,
with brighter derived colors for reading against normal and highlighted lines.
Git status and diagnostic severity colors stay unchanged; unnecessary-code hints
use the brighter secondary text color.
Lualine resolves colors again on every theme application, with an automatic
fallback when another Neovim colorscheme is selected.

Yazi uses the same core syntax roles in code previews, generated from the active
palette independently of the optional Codex integration. Its comments use the
standard secondary text color. Directory names are ivory, with orange markers;
the current row uses orange text on a tinted surface.
Installing the managed theme disables existing Yazi flavor selections so they
cannot override these preview colors; restoration recovers the original theme.
Yazi's grammar-based highlighting can classify some tokens differently from
Neovim's Tree-sitter and language-server highlighting.

The normal pane ratio is **1:4:3** (parent, files, preview). Press **T** to expand
the preview to **0:1:7**, then press it again to restore the previous layout.
Image previews are bounded at **800×800** pixels. Existing cached images may
retain their old size; run `ya cache clear` once after upgrading to regenerate
them. Larger previews can use more cache space and processing time.

Yazi's Enter key enters directories inside Yazi and uses the normal file opener
for files, including the existing multi-selection behavior.

Lock appearance and its command are described in [LOCK-SCREEN.md](LOCK-SCREEN.md).
