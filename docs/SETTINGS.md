# ATLAS settings

Open **Omarchy → ATLAS**, or run `atlas-settings`. Installation adds a marked
block to `~/.config/omarchy/extensions/omarchy-menu.jsonc`, preserving other menu
entries and comments. Omarchy reloads the extension automatically.

| Control | Behavior |
| --- | --- |
| Wallpaper | Opens Omarchy's image picker for the active theme and user backgrounds. Cancelling leaves the current wallpaper alone. |
| Window opacity | Offers 80%, 87% (ATLAS default), 95%, or 100%; the current preset gets a checkmark. Fullscreen and existing app exceptions keep their own rules. |
| Component status | Shows the active theme, configured Foot font, wallpaper, opacity, and installer-managed or separately detected components. |
| Diagnostics | Compares local files with saved snapshots and reports interrupted transactions and application availability. No uploads or privileged commands. |
| Shortcuts & help | A compact guide to the terminal workspace and file navigation. |
| Restore managed files | Lists affected files, requires another active theme, runs a dry-run, and asks for `RESTORE` before applying. Enter cancels. |

The font is not an adjustable preset here: normal ATLAS typography remains 9 pt.

## Configuration and restoration

Opacity is read from the existing ATLAS all-window rule in `looknfeel.lua` or
`hyprland.lua`; there is no second preference store. Ambiguous/custom rules are
left for manual review. Updates retain the selected opacity. The control checks
Hyprland before and after changing the rule and rolls back if validation fails.
It changes focused and unfocused opacity together, keeping fullscreen at 100%.

All managed changes use `~/.local/state/atlas-bundle/`. Original snapshots remain
available across repeated setting changes. Later edits to a managed file block
updates and restoration; save and reconcile them before proceeding.

Existing desktops may have ATLAS components installed outside the bundle. Status
labels these separately: detection does not claim installer ownership. Restore
only covers files listed in the journal, not every detected component. Existing
legacy theme hooks should be migrated with [MIGRATION.md](MIGRATION.md) before a
full bundle install.

```bash
atlas-settings status
atlas-settings diagnostics
atlas-settings opacity 87
atlas-settings restore
```

Reports support `--pause` for menu-launched terminals. `--home` supports isolated
staging; it never reloads the live compositor when selecting a different home.

## Editor consistency

The shared Aether templates style Neo-tree, Snacks pickers and input dialogs,
Blink completion, Noice command/search dialogs, Which-key help and native popup
surfaces. Orange marks navigation and focus; ivory carries ordinary text.
Syntax, completion-kind icons, Git status and diagnostics keep their meanings.
Lualine resolves colors again on every theme application, with an automatic
fallback when another Neovim colorscheme is selected.

Yazi's Enter key enters directories inside Yazi and uses the normal file opener
for files, including the existing multi-selection behavior.
