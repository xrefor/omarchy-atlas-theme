# ATLAS development priorities

Use **“One palette. From boot to desktop.”** as a release acceptance standard:
verify visual consistency across the advertised boot/login, desktop/lock,
terminal and supported application surfaces. Preserve semantic colors where
they communicate errors, diagnostics or editing modes. Showcase claims and
captures should match the shipped behavior; keep optional components and their
requirements clear, credit the projects behind integrations, and state the
limits of validation.

The selected pass covers **1: interface consistency** and **3: accessible
settings**. Contrast variants and project workspaces remain future proposals.

## 1. Interface consistency — implemented

Neovim explorers, pickers, completion menus, command/search dialogs, help overlays
and the normal status line share the active palette's accent. Ordinary text
uses ivory and selection surfaces use carbon. Syntax, Git, diagnostics, completion
kind icons and editing modes retain their semantic colors. Completion icons now
match code roles; standard comments, punctuation and editor hints use readable
secondary text rather than the decorative border color.

Yazi's Enter key enters directories and retains the ordinary file opener,
including multi-selection. Right-arrow navigation remains available.
Its generated code-preview theme shares Neovim's core syntax roles. Ivory
directory names and orange markers distinguish file type from current-row
focus. The 1:4:3 layout gives filenames half the width; T expands the preview
and restores the prior layout. Images remain bounded, now at 800×800 pixels.

Agents and Nym share terminal panel styling: title and footer strips, content
spacing, semantic colors and sidebar sizing. Both reload palette changes while
open. Extending the surrounding tmux layout conventions to other tools, and
coordinating logo sizing across boot, login, lock and wallpaper, remain separate
follow-up work.

Integration checks cover startup, repeated palette changes, switching away from
Aether, and returning to it. Demonstrations keep the normal 9 pt typography.

## 2. Higher-contrast variant — proposed

The base theme now uses a brighter derived red for authentication error text
and bar alerts. The Classic lock input is opaque to preserve text contrast over
wallpapers. See the measured pairs in [VALIDATION.md](VALIDATION.md).

Review muted text, comments, inactive panes, selections and disabled controls
together before creating a variant. Improve readability without enlarging the
demonstration font or changing the ATLAS identity.

The optional **ATLAS Readable** CLI syntax preset implements the demonstrated
comment-only adjustment: `#6e675c` → `#a69b8c`. It is selected through the native
theme picker; see [CLI.md](CLI.md). Neovim also offers an optional brighter-comment
setting, with palette-aware colors, focus refresh and preservation through updates
and restoration; see [SETTINGS.md](SETTINGS.md). A broader desktop variant remains
proposed and needs separate review of its actual text/background pairs.

## 3. Settings and diagnostics — implemented

The native Omarchy menu has an ATLAS entry for wallpapers, opacity presets,
component status, local diagnostics, shortcuts and managed-file restoration.
See [SETTINGS.md](SETTINGS.md).

Preferences use existing configuration files and the installation journal.
Opacity presets preserve fullscreen and app-specific exceptions, survive bundle
updates, and roll back on failed compositor validation. Restoration previews
affected files and preserves later manual edits.

## 4. Project workspaces — proposed

A small project chooser could resume a named tmux session in its directory, with
shell, editor and files tabs. Monitoring and VPN panels would remain optional.
Restore layout and location without automatically re-executing previous shell
commands. Keep this optional so a new terminal can behave as it does today.

Continue the [release validation checklist](VALIDATION.md) throughout, including
the remaining hardware, authentication, boot and update/restore checks.
