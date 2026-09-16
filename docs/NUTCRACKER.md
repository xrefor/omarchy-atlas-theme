# ATLAS Nutcracker

ATLAS provides an optional terminal interface for
[drneox/nutcracker](https://github.com/drneox/nutcracker). It is not installed
by the normal theme installation. Use the ATLAS settings menu or run:

```sh
atlas-theme nutcracker-install --with-tools
```

The integration fetches upstream commit
`c0980227fabd910ce4e4597937a5b88be39527f2` into a private, user-scoped data
directory. It installs exact declared Python package versions into a dedicated
virtual environment. It does not alter the system Python environment.

`--with-tools` also downloads JADX 1.5.6 and Eclipse Temurin JRE 21.0.12.1+1.
Those archives have pinned SHA-256 checksums and are available for Linux
x86-64 and AArch64. Without that option, the integration uses compatible
`java` and `jadx` commands already on `PATH`.

## Paths

The default paths follow the XDG base-directory environment:

- source, virtual environment, tools, reports, logs and database:
  `$XDG_DATA_HOME/atlas-nutcracker` (normally
  `~/.local/share/atlas-nutcracker`)
- configuration: `$XDG_CONFIG_HOME/atlas/nutcracker.yaml` (normally
  `~/.config/atlas/nutcracker.yaml`)
- launchers: `~/.local/bin/nutcracker` and
  `~/.local/bin/atlas-nutcracker`

The frontend creates a conservative local configuration on first launch.
Static regex scanning and JSON/PDF reporting are enabled; OSINT, the scheduler,
post hooks and the container toolbox are disabled. It uses the machine's local
timezone. Existing configuration is preserved.

## Use and maintenance

Run `nutcracker` for the TUI. `nutcracker --help` includes the themed upstream
CLI, `nutcracker doctor` lists available tools, and `nutcracker reports` lists
saved reports. The TUI's Analyze action accepts an existing APK and always uses
the upstream `--static-only` flow. It does not connect to a device. Native
upstream commands can provide dynamic and device features when the operator
explicitly selects them.

Check or remove the optional integration with:

```sh
atlas-theme nutcracker-doctor
atlas-theme nutcracker-restore
```

Restore removes the state-journaled launchers and desktop entry and deletes
only the recognized generated source, virtual environment and tool trees.
Reports, logs, database and configuration remain for the user to retain or
remove separately. A missing or unexpected install marker blocks runtime-tree
removal so an unrelated directory is preserved.

## Packaging boundaries

The ATLAS archive contains the frontend and installer declarations, but no
Nutcracker upstream source, JRE or JADX binaries. Setup therefore requires Git,
Python 3.11+ with `venv`, pip and network access. Optional dependency engines
such as Semgrep, APKTool, Gitleaks and apkeep are not installed. The installer
does not run an APK scan, start a service or perform a device action.
