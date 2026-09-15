# Blackburn to ATLAS

The distributable identity, commands, application palette names, shell plugin IDs,
file names and runtime paths now use ATLAS:

| Earlier installation | New bundle |
| --- | --- |
| Blackburn / Graviton theme experiments | ATLAS |
| `omarchy-blackburn-theme` | `omarchy-atlas-theme` |
| `blackburn-theme` | `atlas-theme` |
| `~/.config/blackburn/` | `~/.config/atlas/` |
| `~/.local/lib/blackburn-system/` | `~/.local/share/atlas/` |
| legacy CLI runtime | `~/.local/lib/atlas-cli/atlas_cli/` |
| Blackburn wallpaper filenames | `atlas-*.png` |

Legacy names in provenance and copyright notices are historical attribution,
not active branding. Runtime files have no dependency on the author's username
or workspace paths.

## Existing local experiments

Packaging creates an independent distribution. It does not rename old workspace
folders, discard their backups, or silently apply the new installer to the
creator's active desktop.

For an existing experimental installation, keep its backup/manifests and use its
own restore workflow before installing the new bundle. The new installer has a
separate ownership record and cannot infer the originals from unrelated legacy
manifests. A `--all --dry-run` is useful for reviewing the transition.

Active third-party shell clones stop the installation for review so two
lock/authentication agents cannot run at the same time. Legacy code directories
remain available for rollback.

Before migrating a live setup, disable the old `blackburn-system` theme-set hook
using that integration's restore workflow: running both the old and new palette
writers would let them overwrite each other's app files. The bundle detects
this active legacy hook and asks for it to be resolved before a live install.
