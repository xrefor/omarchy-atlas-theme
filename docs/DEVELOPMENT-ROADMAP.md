# ATLAS development priorities

The selected pass covers **1: interface consistency** and **3: accessible
settings**. Contrast variants and project workspaces remain future proposals.

## 1. Interface consistency — implemented

Neovim explorers, pickers, completion menus, command/search dialogs, help overlays
and the normal status line share the active palette's accent. Ordinary text
uses ivory and selection surfaces use carbon. Syntax, Git, diagnostics, completion
kind icons and editing modes retain their semantic colors.

Yazi's Enter key enters directories and retains the ordinary file opener,
including multi-selection. Right-arrow navigation remains available.

Integration checks cover startup, repeated palette changes, switching away from
Aether, and returning to it. Demonstrations keep the normal 9 pt typography.

## 2. Higher-contrast variant — proposed

Review muted text, comments, inactive panes, selections and disabled controls
together before creating a variant. Improve readability without enlarging the
demonstration font or changing the ATLAS identity.

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
