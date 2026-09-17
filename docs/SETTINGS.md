# ATLAS settings

Open **Omarchy → ATLAS**, or run `atlas-settings`. Installation adds a marked
block to `~/.config/omarchy/extensions/omarchy-menu.jsonc`, preserving other menu
entries and comments. Omarchy reloads the extension automatically.

| Control | Behavior |
| --- | --- |
| Wallpaper | Opens Omarchy's image picker for the active theme and user backgrounds. Cancelling leaves the current wallpaper alone. |
| Window opacity | Offers 80%, 87% (ATLAS default), 95%, or 100%; the current preset gets a checkmark. Fullscreen and existing app exceptions keep their own rules. |
| Lock screen | Selects Classic or Terminal for the next lock; shown when the shell component is installed. |
| Neovim comments | Selects Standard or Brighter comments in the ATLAS Aether integration. The choice applies when Neovim regains focus or reloads its colorscheme. |
| Component status | Shows the active theme, configured Foot font, wallpaper, opacity, and installer-managed or separately detected components. |
| Diagnostics | Compares local files with saved snapshots and reports interrupted transactions and application availability. No uploads or privileged commands. |
| Shortcuts & help | A compact guide to the terminal workspace and file navigation. |
| Restore managed files | Lists affected files, requires another active theme, runs a dry-run, and asks for `RESTORE` before applying. Enter cancels. |

The font is not an adjustable preset here: normal ATLAS typography remains 9 pt.

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

Neovim's brighter comment role follows the active Omarchy palette: 75% foreground
mixed with 25% background. On ATLAS this changes `#3a342c` to `#a59f96`. The CLI
preset uses the slightly warmer demonstrated `#a69b8c`. These are comment presets,
not a whole-desktop accessibility mode; font sizes stay unchanged.

## Configuration and restoration

Opacity is read from the existing ATLAS all-window rule in `looknfeel.lua` or
`hyprland.lua`; there is no second preference store. Ambiguous/custom rules are
left for manual review. Updates retain the selected opacity. The control checks
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
atlas-settings opacity 87
atlas-settings readability readable
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

Lock appearance and its command are described in [LOCK-SCREEN.md](LOCK-SCREEN.md).
