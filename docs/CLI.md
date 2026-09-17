# ATLAS command-line styling

ATLAS includes optional presentation wrappers for common network and security
tools. They do not add scan, capture, exploitation, or API features. Each
wrapper passes the original arguments to the distribution executable in
`/usr/bin`, keeps stderr separate, and returns the underlying exit status.

Install the core wrappers with:

```sh
python3 install.py install --components cli
```

Add selected integrations by passing their group names:

```sh
python3 install.py install --components cli \
  --cli-groups cli-core,cli-tcpdump,cli-metasploit,cli-shodan,cli-codex
```

`--all` installs every user component and every CLI group. Group selection
changes what is activated; all source remains in the bundle for review.

## Core wrappers

The `cli-core` group styles human-readable terminal output from `nmap`, `ping`,
`ip`, `ss`, and `dig`. It reads the active Omarchy `colors.toml` at process
startup and falls back to the ATLAS palette if Omarchy is unavailable.

Color is enabled only when stdout is a terminal. `NO_COLOR=1` or
`ATLAS_COLOR=never` disables it. `ATLAS_COLOR=always` enables color for an
explicitly redirected human-readable stream.

Machine-oriented modes bypass the formatter. This includes Nmap output files
and resume modes, ip JSON/batch/native-color modes, ss diagnostic dumps, ping
flood mode, and dig short/YAML output. Native ANSI output is passed through
unchanged.

The real tools must already be installed. The wrappers expect these executable
paths:

- `/usr/bin/nmap`
- `/usr/bin/ping`
- `/usr/bin/ip`
- `/usr/bin/ss`
- `/usr/bin/dig` (provided by Arch's `bind` package)

Place `~/.local/bin` before `/usr/bin` in `PATH`. Run `hash -r` in an existing
Bash session after installation. Use the absolute `/usr/bin/<tool>` path to
bypass a wrapper immediately.

## Optional integrations

`cli-tcpdump` installs a `tcpdump` wrapper. Human packet text is styled, while
pcap write mode, help, and version output bypass formatting. Live capture still
uses the distribution `/usr/bin/tcpdump`; the wrapper requests `sudo` when the
current user lacks root privileges and uses the configured askpass helper for a
non-interactive stdin. It does not change capture filters or grant privileges.

`cli-metasploit` installs a launcher that adds `-q` and a native
`~/.msf4/msfconsole.rc` prompt resource. The resource runs as Metasploit startup
code and only reads the active palette before setting `Prompt` and `PromptChar`.
The installer appends a managed styling block to an existing startup resource,
preserving its other commands and backing up the original file for restoration. An explicit `msfconsole -r FILE` continues to
select the resource passed by the user.

`cli-shodan` styles the official `/usr/bin/shodan` client's terminal output.
JSON/raw/field output and download, parse, or convert commands bypass the
formatter. This bundle never reads, writes, or ships a Shodan API key and does
not include the former custom Shodan HUD or its saved target/export data.

The tested Wifite 2.9.9-beta presentation adapter is retained as reviewable
source in `components/cli/extras/wifite`. It is deliberately absent from the
install map. The old launcher depended on one user's source checkout and
executed mutable home-directory Python under `sudo`. The included README states
the root-owned packaging and version-pinning requirements for a downstream
integration.

`cli-codex` installs two native TextMate syntax palettes in `~/.codex/themes/`
(the standard Codex home): `atlas.tmTheme` and `atlas-readable.tmTheme`.
In Codex, use `/theme` to preview/select **ATLAS** or **ATLAS Readable**, or set
`tui.theme = "atlas"` / `tui.theme = "atlas-readable"` in its config. If using a
custom `CODEX_HOME`, copy the assets into that home's `themes/` directory.

**ATLAS Readable** is the optional comment-readability preset. It changes comment
text from `#6e675c` to the palette's existing secondary color, `#a69b8c`. Against
opaque ATLAS carbon (`#100e0c`), that raises contrast from 3.45:1 to 7.05:1. This
preset changes only syntax comments; typography and other syntax colors retain
the standard theme's values. Installation adds the choice without selecting it.

The official [syntax-theme controls](https://learn.chatgpt.com/docs/developer-commands?surface=cli#choose-a-syntax-theme-with-theme)
persist the selection; the installed 0.154.0 client also documents custom
`.tmTheme` loading in its built-in theme picker. Selection is left to the user.

### Codex interface colors

The `apps` component also installs `atlas-codex`. In a fresh ATLAS Bash terminal,
launch `codex` normally to get orange action accents and warm carbon prompt and
approval backgrounds. The adapter reads the active Omarchy palette on launch
and applies this mapping only to an ATLAS-family palette (accent `#ff5a12`).
Native truecolor syntax foregrounds remain controlled by the `/theme` choice.

The managed Bash integration preserves existing custom `codex` functions and
aliases. It does not patch the Codex executable or a mise launcher. To use the
adapter explicitly with a custom Bash setup:

```bash
atlas-codex --observe -- "$(type -P codex)"
```

`--observe` enables the agent observer when running in tmux. The observer follows
the actual Codex child process inside the adapter's terminal. Closing Codex
cleans up its observer and panel as before. The adapter does not record terminal
input or output, or read Codex credentials.

`ATLAS_CODEX_COLORS=0 codex` disables interface coloring while retaining normal
agent observation. `command codex` bypasses both integrations. Redirected input,
output or error output, utility/noninteractive commands, `NO_COLOR`, and missing/invalid or
non-ATLAS palettes bypass the color adapter. Unknown terminal control sequences
are passed through, and the adapter preserves native truecolor foregrounds.

The mapping is based on the Codex 0.154.0 interface; future client versions may
use different colors. Report visual differences with the client version and a
screenshot. `atlas-theme restore` restores the prior managed launcher and Bash
integration through the normal backup journal.

## Installation and rollback contract

`components/cli/install-map.json` lists every source, home-relative target,
mode, and optional group. A conforming installer must preflight all selected
targets, refuse parent-directory symlinks, write atomically, back up existing
regular files before replacement, lock its state, and stop if a managed file
has been edited since installation. Rollback restores the original bytes and
mode or removes a file that did not previously exist.

Never publish installer state, backups, command output, packet captures, Shodan
exports, API configuration, or Python bytecode with the bundle.
