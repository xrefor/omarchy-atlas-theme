# Release validation

This release candidate was prepared on the reference workstation and exercised
in an isolated Omarchy 4.0.4 VM. The rc5 run upgraded an rc4 user installation.
Authentication policy and workstation boot configuration were not changed.

## Automated and isolated checks

Run `python3 tools/check.py` for the current test counts. The development checker
requires Node.js for JavaScript model tests. It covers:

- Full user installation into temporary homes, repeat installation with no
  changes, palette synchronization and exact original-file restoration.
- Direct execution of installed application commands with mocked application
  backends, including execute permissions independent of source-file modes.
- Homes containing spaces and percent signs, browser profile discovery,
  preservation of existing application preferences and startup commands.
- Path traversal and symlink escape rejection, original symlink/mode recovery,
  user-edit protection, write-failure rollback and interrupted-install recovery.
- Authentication clone merging, rejection of competing custom clones,
  preservation of unrelated bar widgets and settings, and removal of the
  file-based askpass bridge from the distributed Polkit code.
- Seeded Matrix rain/fill/resolve/restart cycles at 1080p, 4K and small sizes;
  unique glyph drawing, continued fill animation, final branding and empty input.
- Idle configuration bounds, event parsing and screensaver-window lifecycles;
  monitor brightness, fractional scaling, invalid presets and display counts;
  Polkit fingerprint hints, direct PAM module parsing and authorization labels.
- Boot transactions against simulated EFI partitions; preservation of boot
  entries, original appearance restoration, mocked rebuild failures, and
  boot-image/kernel-change recovery safeguards. Plymouth recovery also covers
  later settings/comments/permissions, originally absent selectors and files,
  interrupted recovery, duplicate-selector rejection, and edits during recovery.
- CLI byte/exit/signal preservation, machine-readable output bypass and
  selected optional-integration behavior. Tests do not scan or capture traffic.
- Codex interface-color parsing with split sequences and opaque terminal payloads;
  isolated PTY input, resize, signal/exit and terminal restoration; managed Bash
  dispatch and agent observation inside the color adapter. These fixtures use a
  fake CLI; they do not establish visual compatibility with future Codex versions.
- Nym panel protocol, stale-status regression, mode/settings readback and invalid
  input checks; service detection, explicit start/enable confirmation, cancellation,
  failure/readback and unprivileged app launch. Isolated tmux tests use fake service,
  privilege, CLI and app executables to exercise setup and closing without
  disconnecting. Live systemd authorization and Nym account setup still require
  hardware validation.
- Seven mocked Yazi drive-menu cases: authorization, clean removal, busy failure,
  internal-device rejection, argument handling, mounted siblings and optical media.
- Python, JSON, TOML, YAML, XML and shell syntax; four Omarchy plugin manifests;
  generated root theme files compared to their palette/templates.

The four shell clones additionally passed QML/JavaScript lint/syntax checks
against the installed Quickshell/Omarchy modules. An isolated tmux server loaded
the workspace configuration; its Ctrl+Space prefix and ATLAS status header were
queried successfully, and the private test server was removed afterward.

The final archive is extracted into a temporary directory and its internal
SHA256SUMS verified. The user installer is exercised from that extracted copy,
and the build is repeated to check deterministic archive output. Release files
must be tracked by Git and explicitly selected; bytecode, private state, backups,
logs, credentials, hardware layouts and account profiles are excluded.

## Portable checks and CI

The `ATLAS QA` GitHub Actions workflow runs on pushes, pull requests and manual
dispatch. It uses Ubuntu 24.04, Python 3.11/3.14, Node.js 24, Lua 5.4 and pinned
PyYAML. Actions use immutable commit references, repository permissions are
read-only, and checkout credentials are not persisted.

Each job runs all Python tests, authentication boundary checks, all four
JavaScript model suites, mocked Lua checks, an isolated tmux VPN-panel fixture,
source/configuration validation and palette/template consistency. Omarchy's
standalone palette resolver is pinned to v4.0.4's commit and verified by SHA-256.
No desktop, compositor, VPN account or live authentication service is needed.

With the [test dependencies](DEPENDENCIES.md#building-and-validating-the-source)
installed, run the same portable checks locally:

```bash
atlas_test_bin=$(mktemp -d)
bash tools/ci-deps.sh "$atlas_test_bin"
PATH="$atlas_test_bin:$PATH" python3 tools/check.py --portable
PATH="$atlas_test_bin:$PATH" python3 tools/check_release.py
python3 tools/build_site.py
```

`check_release.py` requires a Git checkout with the intended release files
tracked. It builds twice, compares archive bytes, checks extracted payload
hashes against both the manifest and source, runs the shipped model tests, then
installs/repeats/syncs/checks/restores within a temporary home. The workflow also
validates showcase assets and anchors. It does not publish or deploy artifacts.

Portable mode explicitly skips Neovim plugin integration, Omarchy plugin
validation and QML lint. Run `python3 tools/check.py` on Omarchy for those checks.
VM/hardware validation below remains necessary; a green portable job does not
establish live lock/unlock, fingerprint, boot or physical-display behavior.

The helper suites contain 5 idle, 15 monitor and 9 Polkit cases, alongside the
6 Matrix cases. They cover regressions discovered while adding coverage:
malformed/overflowing idle timeouts, invalid scaling options, malformed or
duplicate display rows, and misleading PAM/module or authorization-message
matches. Polkit's helper recognizes modules in the supplied PAM text; following
`include`/`substack` files and discovering alternate PAM config locations are
outside that helper's scope. It does not decide whether authentication succeeds.

## rc5 validation

- Both Terminal and Classic lock modes reached a secure session lock and
  unlocked through the VM account's real password PAM flow. An incorrect
  password left Terminal locked. Changing the preference while locked kept
  the existing surface until the next lock.
- The rc4-to-rc5 user upgrade, repeat installation, theme switch and original-file
  restoration completed in the VM.

## Recovery and Polkit follow-up — 2026-09-17

- The complete checker passed 114 Python tests, including 28 boot tests, and six
  authentication boundary checks, plus the existing integration and lint checks.
- A disposable Omarchy VM installed Plymouth through the privileged installer
  and rebuilt its real boot images. Confirmation was refused in that boot session.
  After reboot, recovery preserved later Plymouth settings, a comment and mode
  `0640`; every ESP entry changed by the installation matched its original
  manifest afterward. The recovered VM rebooted successfully.
- The installed Polkit clone displayed `<b>ATLAS QA</b> & <i>literal</i>` literally
  in a real authorization dialog. A temporary VM-only action required native
  administrator authentication and ran only `/usr/bin/true`. Cancellation denied
  the action, an incorrect password left it pending, and the correct password
  authorized it. The test policy was removed afterward.

These checks did not change the reference workstation's boot or authentication
configuration. The VM was unencrypted, so this run does not establish encrypted
Plymouth prompt behavior or physical firmware compatibility.

## Unchanged palette sync follow-up — 2026-09-17

The complete checker passed 127 Python tests, six authentication boundary checks
and the existing integration and lint checks. The personal security agent also
reviewed the transaction changes and their recovery regressions.

Unchanged installation and palette sync now validate the requested files and
installation metadata before returning without writing a journal or manifest.
Matching files being managed for the first time, new components, legacy directory
metadata and manifest permission repairs still use a recoverable transaction.
Dry runs also avoid copying the full manifest into a rollback snapshot.

In a temporary home with all user components, the same local benchmark measured:

| Operation | Journal/manifest bytes before → after | Transaction seconds before → after |
| --- | --- | --- |
| Repeat installation | approximately 81.5 MB → 0 | 0.831 → 0.200 |
| Unchanged palette sync | approximately 81.5 MB → 0 | 0.741 → 0.103 |

These are single local timing samples, not general storage benchmarks. The
existing lock still checks directory permissions; the zero-byte result refers
to journal/manifest payload writes. Peak RSS across fresh installation, repeat
installation and sync fell from approximately 520 MiB to 255 MiB; that peak is
not a measurement of sync alone.

Regression coverage includes unchanged full-bundle installation/sync, applying a
different palette and repeating it, original-file adoption, component/directory
metadata updates, permission repair, later edits, concurrent edits, metadata-only
failure/recovery and restoration with no file changes. The state format is
unchanged.

## Matrix drawing follow-up — 2026-09-17

Completed fill columns now belong only to the full-column collection. They
continue changing symbols and colors while other columns fill, and each glyph
appears once in the draw list. Production animation settings are unchanged.

Seeded simulations using 11×22-pixel cells measured the following maxima across
complete animation cycles:

| Resolution | Duplicate glyph references per frame before → after | Total draw-list entries before → after |
| --- | --- | --- |
| 1920×1080 | 8,477 → 0 | 17,002 → 8,526 |
| 3840×2160 | 34,104 → 0 | 68,305 → 34,202 |

These measure model drawing work, not live GPU frame rates or desktop CPU use.
Six deterministic Node tests check column ownership, unique glyphs, painting,
continued fill animation, complete cycles and fresh state after restart. Five
of those tests reproduced the original defect before the fix. They now run as
part of `tools/check.py`.

An isolated Qt 6.11.2 Canvas check also rendered the fill phase and the complete
262-glyph ATLAS mark from the shipped branding text. It used shortened timing
for screenshots; the Node cycles use the production timing configuration. This
follow-up did not invoke a live session lock or change authentication behavior.

## Caps Lock polling follow-up — 2026-09-17

Caps Lock polling now requires an active, visible lock or preview surface and a
visible password prompt. It pauses while the Matrix screensaver covers the
prompt. Activation refreshes the indicator immediately, and direct or deferred
refresh requests also respect that gate. A reader already in flight may finish;
no further reader starts while hidden. The visible polling interval remains
400 ms, and readers cannot overlap.

An isolated offscreen Quickshell harness exercised the production LockView with
native processes and controlled LED output. Styling and Matrix rendering were
stubbed. The original hidden preview launched three readers in 900 ms; the
updated view launched none. All 14 lifecycle assertions passed, covering
hidden/reopened windows, changed Caps Lock state, screensaver dismissal,
inherited Item visibility, Classic and Terminal prompts, inactive surfaces,
slow readers and a surface that is already active when created.

This is a process-launch check, not a live desktop CPU or power benchmark.
Authentication, session-lock transitions and physical keyboard LED behavior
were not exercised by this harness. Polling remains per visible surface.

## Semantic error-text follow-up — 2026-09-17

Authentication error text and bar alerts use `#e46147`, derived by mixing the
palette's bright red with 20% foreground. Terminal ANSI colors and error borders
retain their original values. The Classic lock input field is now opaque carbon,
so wallpaper brightness cannot wash out its password or error text.

| Text pair | Contrast before → after |
| --- | --- |
| Polkit error / carbon | 3.39:1 → 5.60:1 |
| Terminal lock error / carbon | 3.39:1 → 5.60:1 |
| Bar alert / carbon | 3.39:1 → 5.60:1 |
| Classic lock error / white wallpaper bound | 1.87:1 → 5.60:1 |

Ratios use sRGB luminance; checks compare the unrounded values against the
[4.5:1 normal-text benchmark](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
This is a check of these specific pairs, not whole-theme WCAG conformance.
The Classic white/black wallpaper bounds include its former 80% input background.
Offscreen Quickshell captures of the actual Classic and Terminal LockViews were
visually checked; sampled Classic field/text pixels matched the calculated colors.
Style/border helpers were isolated fixtures; no live authentication was invoked.

The Python renderer now supports Omarchy's native `mix` template expression.
Five unit tests cover its amount forms, rounding, clamping, ordinary tokens and
missing colors. Native Omarchy and Python output matched for all five desktop
templates and nine mix inputs with ATLAS, Tokyo Night and Catppuccin Latte.
The shared templates therefore continue following the active theme's palette.

Editor syntax, muted text, disabled controls and wallpaper-dependent contrast
in translucent application windows remain part of the proposed readability
variant. This change targets authentication errors and bar alerts.

## Responsive showcase previews — 2026-09-17

The wallpaper picker uses committed WebP thumbnails and responsive hero images.
Full-resolution PNG download links retain the original file bytes. Forty preview
files total 828,078 bytes; the generator never enlarges a source image.

A cold-cache Chromium check measured image response bodies for the initial
wallpaper and all eight visible thumbnails:

| Viewport / pixel density | Before | After |
| --- | --- | --- |
| 1280 px desktop / 1× | 12,706,150 bytes | 31,532 bytes |
| 1280 px desktop / 2× | 12,706,150 bytes | 76,222 bytes |
| 390 px mobile / 2× | 12,706,150 bytes | 31,532 bytes |
| 320 px mobile / 1× | 12,706,150 bytes | 15,698 bytes |

These are gallery image bytes, not whole-page transfer totals or page-load
timings. Original downloads remain in the deployed site, so the staged site's
total size increases by the preview assets while browsing transfers much less.
External fonts were excluded consistently from this local comparison.

All eight selections, captions, pressed states and keyboard activation passed at
each viewport. All eight original downloads matched their original hashes.
Switching previews fetched no original PNGs. The initial preview and original
link also work without page JavaScript.
Desktop/mobile captures were visually inspected; no horizontal overflow, page
exceptions or missing local assets were observed.

Three site-builder regressions cover staging responsive/dynamic paths, rejecting
missing candidates before replacing a prior build, and validating candidate
syntax and relative paths. Both source repositories use the same builder and
preview bytes. The public Pages workflow runs these tests before staging.

## Comment presets and release follow-up — 2026-09-17

Optional brighter comments are available in Neovim through `atlas-settings
readability readable`, and in the Codex CLI through its native **ATLAS Readable**
theme. Standard appearance remains the default. On opaque ATLAS carbon, the
Neovim comment pair changes from **1.57:1 to 7.34:1** (`#3a342c` → `#a59f96`);
the CLI pair changes from **3.45:1 to 7.05:1** (`#6e675c` → `#a69b8c`). These
measurements cover ordinary comments, not every editor highlight or translucent
surface. Font sizes, semantic annotations and comment styles are preserved.

The complete checker passes **140 Python tests**, six authentication boundary
checks and **35 JavaScript tests**, plus Lua, native Neovim, plugin manifests,
QML lint, isolated tmux and palette/template checks. The available Python 3.11.9
runtime also passes the portable checker, using the installed PyYAML package's
pure-Python implementation. These are local Arch results with Node.js 26.7;
see the repository's ATLAS QA workflow for Ubuntu/Node.js 24 hosted results.

Five new preference tests cover persistence, original-file restoration, no-op
selection, managed-edit protection, symlink rejection and command validation.
Native Neovim integration covers focus refresh, ordinary/Treesitter comments,
preserved TODO/error annotations and italics, palette changes and switching to
another colorscheme. Native Omarchy/Python template output matches for ATLAS,
Tokyo Night and Catppuccin Latte. The independent security review found no
material issues in the new preference path or journal integration.

A fresh disposable overlay of the existing Omarchy 4.0.4 recovery VM installed
the verified archive and all user components, including the Codex syntax assets:

- Classic and Terminal locks both stayed secure after an incorrect password and
  unlocked through native password PAM. A changed lock-style preference remained
  deferred until the next lock.
- The current Polkit model and agent displayed the markup fixture literally;
  cancellation returned 126, an incorrect password did not authorize, and the
  correct password authorized `/usr/bin/true`. The temporary action was removed.
  Additional model cases preserve LF/CRLF command and service messages.
- The installed Neovim template read the actual brighter-comment preference.
  ATLAS → Tokyo Night → ATLAS preserved that choice and respected Tokyo Night's
  own native editor configuration. A repeat installation made zero file changes
  and left the manifest timestamp unchanged; diagnostics reported no drift.
- Scaling to 1.25 worked, including secure lock/unlock. A second virtual output
  appeared in the monitor panel; removing it while locked left the remaining
  surface secure and usable for password unlock. These are virtual-output checks,
  not physical hotplug or GPU coverage.
- The production drive-action module ran against a real virtual USB through
  UDisks. It rejected a busy eject and an internal disk, then successfully
  unmounted, mounted and powered off the released USB. A Neovim adapter supplied
  Yazi's JSON/process/UI primitives; the actual Yazi menu was not installed here.
- H.264 playback advanced in mpv's Wayland software output (`--vo=wlshm`). The
  default renderer aborted at `vo_x11_init` after graphics-context failures. The
  same abort reproduced after ATLAS restoration with `--no-config`, so default
  renderer compatibility remains a VM/application limitation. No persistent
  renderer setting was changed; this does not establish accelerated playback.
- Native user restoration removed the managed runtime and newly introduced
  preferences/themes, restored saved files and restarted the original shell
  without compositor configuration errors. The restored VM then rebooted to
  its original SDDM login. Restoration guidance now explicitly requires logout
  and login to clear the session's inherited `FONTCONFIG_FILE` value.

The current archive's Limine/Plymouth/SDDM dry-run planned 20 boot-file changes
without changing files or boot images. Boot code and assets are unchanged from
the earlier real recovery/reboot validation; that evidence remains applicable.
This follow-up did not install another kernel or repeat boot-image rebuilding.

The Terminal lock now displays native authentication-failure messages as plain
text that wraps beneath its narrow password prompt. The input and logo retain
their positions and the normal font size. Feedback hides while typing, checking
a password or showing the screensaver. Classic retains its inline message.
An offscreen Quickshell check at 1× and 1.25× rendered native, long and multiline
messages without truncation, including fingerprint hints and a 320-pixel-wide
view. It also checked feedback visibility and fixed prompt geometry. Theme and
Matrix helpers were stubbed; this layout check did not invoke authentication.

Physical firmware/GPU variation, fingerprint readers, encrypted Plymouth prompts,
suspend/resume, power profiling, real Nym connectivity and native Zen/Spotify
workflows remain unverified in this pass.

## Codex agent panel — 2026-09-17

The complete Omarchy checker passed. After the final shell and relaunch
regressions were added, all **189 Python tests** passed with disposable tmux
tests enabled. Release checks verified byte-identical builds, all 248 extracted
payload files, staged installation, unchanged repeat/sync/check and restoration.
Showcase assets and links also passed validation.

Panel coverage includes exact conversation lineage, nested agents, inherited
history boundaries, completed/resumed/interrupted turns, partial and oversized
records, unavailable metadata, private snapshots and terminal control removal.
Reported plans are displayed without inventing percentage progress. Palette
tests cover source colors, live file reloads, invalid-role fallbacks and use of
indexed terminal colors without redefining shared palette slots.

Disposable tmux tests exercise detached wide/narrow layouts, focus preservation,
duplicate suppression, literal command arguments, automatic opening, dismissal,
CLI exit and quick relaunch handoff. PTY-driven Bash checks cover custom functions
and aliases, exact arguments and exit status, opt-out and utility/noninteractive
bypasses. The security review found no material remaining blocker.

A live read-only preview on Codex CLI **0.154.0** showed this conversation's
running and completed agents in the ATLAS palette, with active agents first and
focus retained in the originating pane. This validates the local adapter on
that version; it does not establish compatibility with future Codex metadata
schemas or remote sessions. See [agent panel behavior](AGENT-PANEL.md).

Agent panel exit cleanup follow-up: all nine lifecycle tests passed with real
disposable tmux sessions. Open side panels and separate panel windows close on
CLI exit. Removing the originating pane also closes its panel when the CLI
survives SIGHUP, while unrelated panes remain. Regression checks cover cleanup
after a final snapshot-write failure and ownership handoff during quick relaunch.
The last snapshot remains available for manual reopening from the original pane.
The complete Omarchy checker also passed, including all 193 Python tests.

Completed-agent history follow-up: the complete Omarchy checker passed with
**200 Python tests**, including the 30-second boundary, retained results,
invalid completion times, resumed agents and the history keyboard toggle.
A disposable 48-column tmux panel also verified automatic expiry, retained
error entries, showing/hiding completed results and a resumed agent returning
to the main list through the real curses viewer.

## rc6 release integration — 2026-09-17

The agent panel is included in rc6 alongside the recovery, readability and
performance improvements recorded above. The existing published rc5 release
is preserved. The previous main commit's hosted QA passed on Ubuntu 24.04 with
Python 3.11 and 3.14 and Node.js 24.

Automatic observation now re-resolves the exact conversation when the same
Codex process starts or resumes another thread. Temporary loss of the session
file marks earlier observations stale. An explicit thread selection remains
pinned and can update an already-running observer for that same CLI session.
The regression fixture uses a disposable tmux server and a fake CLI opening
real session files; it does not drive Codex's interactive `/new` or `/resume` UI.

This release integration does not repeat the earlier VM authentication/boot
checks or extend their physical hardware coverage.

## Agent history compatibility follow-up — 2026-09-18

Codex CLI 0.154.0 can omit `subagent_history_start_ordinal` for non-forked
children in both legacy and paginated history. The reader now accepts those
sessions while still requiring a boundary for explicitly forked history.
Read-only checks parsed 62 existing local sessions with the omitted field
(60 legacy, two paginated). All 19 backend tests passed; both new missing-field
regressions reproduced the original rejection before the fix.

The complete `python3 tools/check.py` run passed, including 253 Python tests
and disposable tmux checks. The automatic-opening lifecycle fixture now omits
the field on its first child and covers running/completed status, dismissal
and cleanup. The checker was rerun outside the sandbox because its socket
restrictions prevented tmux checks. Validation on the reported stationary
computer remains outstanding; the source change here does not update that
installation.

## Shared Agents and Nym panel styling — 2026-09-18

Both panels use a shared presentation module for semantic colors, title/footer
strips, content spacing, display-cell clipping and 48–60-column sidebar sizing.
Nym reloads palette changes while open and no longer redefines terminal color
slots. Its title and wrapped controls remain fixed while the content scrolls;
short windows retain contextual exit/cancel hints.

The complete checker's Python stage passed 267 tests, followed by the additional
live-palette regression and an installed-launcher import check. Authentication,
JavaScript models, Lua, native Neovim, plugin/QML validation and palette/template
consistency passed. The new disposable tmux resize test initially sampled a
partial redraw; its readiness checks now wait for complete frames. The corrected
fixture covers 48-column resizing, scrolling with fixed headings/controls,
settings and service actions using fake backends.

Release checks in a disposable Git checkout included the new shared module and
verified deterministic archives, payload hashes, extracted installation,
unchanged repeat/sync/check and restoration. No live VPN connection, account or
desktop configuration was changed. The sample-data layout preview is not
physical-display validation; visual review on the stationary computer remains
separate from these checks.

The follow-up layout prefers 60-column sidebars, with a 48-column fallback when
needed to preserve the main pane. Nym reflows service, startup, mode and gateway
fields as groups, retaining long values on aligned continuation lines. Agent
cards show a stable brief objective from an owned readable assignment, falling
back to the readable task name when the assignment is unavailable. A bounded
read of the current child session confirmed encrypted assignment bodies on the
reference installation; no decryption or generated summarization is involved.
Fixtures cover inherited-history exclusion, task reassignment, completion,
configuration-message filtering and narrow/Unicode layouts.

The full checker passed 281 Python tests and all integration checks for this
refinement. Review then tightened assignment recipient matching to use the
database agent path when session metadata omits it; its three additional
regressions cover missing, unknown and stale identity metadata. All 94 agent
tests, including the disposable tmux lifecycle tests, passed after that fix.

## Monitor Night Light compatibility — 2026-09-18

The monitor panel previously tried to access a first-party service that Omarchy
withholds from monitor clones, making its Night Light button silently do nothing.
It now uses the public Night Light enable/disable IPC and reads actual status
through the CLI. Explicit commands also handle a daytime schedule reporting
6000 K, which the generic toggle otherwise changes to another daylight value.

The native offscreen regression exercises production panel logic and process
handlers with a restricted shell facade and fake commands. Popup geometry is
stubbed because offscreen Quickshell has no PanelWindow backend. This checks
state transitions and command handling, not physical mouse targeting/rendering.
A separate live command check enabled 4000 K from 6000 K, disabled to 6500 K,
and restored 6000 K; brightness gamma and the schedule file were unchanged.
The stationary computer has not been updated or retested in this pass.

## Installer review follow-up — 2026-09-18

Foot configuration handling now accepts an unnamed, explicit or reopened main
section, including a file containing only other sections. Workspace installation
adds its shell command in the correct section and repairs empty shell assignments;
desktop-only installation still preserves a custom shell, and workspace
installation still refuses an unrelated custom shell. Repeated installation
preserves an existing workspace command and leaves other sections' keys alone.

The focused installer suite passed 42 tests, including installation, unchanged
repeat and exact restoration of an original unnamed-main Foot configuration.
Foot's native `--check-config` accepted 12 layout/component combinations and
three repaired empty-shell layouts, all in temporary homes.

Boot transactions now compare the plan with the files being backed up, verify
the ESP backup against live contents, and recheck target/state snapshots before
writing. The journal records attempted writes so an interrupted installation
can recover those paths while preserving edits to untouched paths. Existing
journals without progress metadata retain their previous recovery behavior.

All 35 focused boot tests passed. Temporary-root regressions cover edits during
planning, backup and progress-journal writes; a later-target conflict after an
earlier write; new and legacy interrupted checkpoints; and rebuild-failure
rollback. Successful and failed command-progress journal writes also preserve
external ESP edits without invoking the rebuild. The original overwrite
reproduction now refuses the changed Limine
configuration before writing. No live boot installation or reboot was performed
for these changes.

These are conflict checks, not a shared lock with package managers or other
administrative tools. External writes must still be avoided during boot
operations, especially after rebuild/enrollment starts and full ESP rollback
may be required. See [boot installation and recovery](BOOT.md).

## Before promoting the candidate to a stable release

Use a separate supported Omarchy installation or VM with a recoverable snapshot:

1. Check and install the user components; activate ATLAS and inspect the bar,
   launcher, windows, GTK apps, terminal, Yazi, browser and Spotify terminal UI.
2. Exercise a real lock/unlock and Polkit authorization with password input;
   check fractional scaling and optional fingerprint behavior on suitable hardware.
3. Install boot components, reboot, and inspect Limine, Plymouth disk unlock and
   SDDM where enabled. Confirm the successful boot using the documented command.
4. Change themes, update a kernel, then test boot and user restoration.
5. Exercise removable USB media (including busy files) and application workflows
   such as media playback and browser restart persistence.

The clean VM covers installation, reboot, password authentication, virtual USB
media and recovery logic. It does not validate physical firmware rendering,
GPU variation, fingerprint readers, encrypted Plymouth prompts, real Nym account
connectivity or every optional application version. The archive is suitable for
sharing as **1.0.0-rc6** with those limitations stated.
