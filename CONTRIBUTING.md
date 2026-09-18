# Contributing to ATLAS

ATLAS targets the Omarchy versions and architecture in
[compatibility](docs/COMPATIBILITY.md). Review the relevant component before
changing it, and keep its tests and public documentation aligned.

## Repository layout

| Path | Purpose |
| --- | --- |
| Root theme files and `backgrounds/` | Palette, generated theme configurations and original artwork consumed by Omarchy |
| `assets/` | Original vector artwork used by the desktop and boot components |
| `components/apps/` | Application templates, terminal workspace, Agents and Nym panels |
| `components/cli/` | Optional presentation wrappers and explicit installation map |
| `components/desktop/` | Terminal preferences, canonical desktop templates and shell plugins |
| `components/boot/` | Limine, Plymouth and SDDM appearance assets |
| `lib/atlas/` | Installation, backup/recovery, palette and settings implementation |
| `tests/` | Isolated behavior tests, model tests and native integration fixtures |
| `tools/` | Source validation, deterministic release packaging and showcase staging |
| `docs/` | User guides, compatibility/validation evidence and media provenance |
| `index.html` | Source for the separately published showcase website |
| `.github/workflows/` | GitHub's portable test workflow |
| `LICENSES/` | Retained upstream license notices |
| `dist/` | Ignored, reproducible build output; never a source of truth |

Some small assets intentionally occur in multiple places: Omarchy expects root
preview/lock images, and each boot or shell plugin must carry its own resources.
The CLI entry points also share content but dispatch using their installed names.
Keep these interfaces intact when deduplicating files.

## Change and validate

Install the [development dependencies](docs/DEPENDENCIES.md#building-and-validating-the-source)
and run focused checks for the changed component first. Then run:

```bash
python3 tools/check.py
python3 tools/check_release.py
python3 tools/build_site.py
git diff --check
```

The full checker uses installed Omarchy, Neovim and Quickshell integrations.
On a headless Linux system, use the [portable commands](docs/VALIDATION.md#portable-checks-and-ci).
The GitHub runner is Ubuntu, so its test dependency setup uses `apt-get`.
ATLAS installation still targets Omarchy/Arch. Portable tests do not establish
live desktop, authentication or boot compatibility; report skipped checks.

Release packaging includes tracked, allowlisted working-tree files. Add intended
new files and stage deletions before release verification, review the diff, and
keep private fixtures, local state and generated output out of the index.
Building an archive does not publish it. Do not replace an already published
version with different bytes; assign a new version when preparing a release.

Desktop template changes belong in `components/desktop/themed/`; regenerate the
corresponding root files from `colors.toml` with `atlas.palette` and run the
checker to verify they agree. Application templates live in
`components/apps/templates/`. Keep shared palette changes coordinated across
both sets. See [artwork provenance](docs/CREDITS.md) before adding media and
[website development](docs/WEBSITE.md) before updating the showcase.

Use temporary homes, staged system roots and separate tmux servers for tests.
Exercise privileged installation and recovery in a disposable Omarchy VM with
a recoverable snapshot. Never include a real user's backup journal, browser
profile, account data or machine-specific boot configuration in a contribution.

## Report a problem

Include the ATLAS version, relevant Omarchy/application versions, selected
components, reproduction steps and expected versus observed behavior. Share
only the relevant error output after removing private information. Distinguish
native observations from mocked or staged test results.
