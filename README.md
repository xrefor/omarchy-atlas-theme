<p align="center">
  <img src="assets/atlas.svg" alt="ATLAS" width="260">
</p>

# ATLAS for Omarchy

**One palette. From boot to desktop.**

Carbon surfaces. Warm ivory text. Signal orange.

ATLAS brings a shared visual language to your whole setup: boot and login,
windows and lock screen, terminals and everyday applications. Square edges,
fine borders, and just enough orange to show what matters.

**[Explore ATLAS ↗](https://xrefor.github.io/atlas-showcase/)** · [Install](#install) · [Screenshots](#screenshots) · [Reference](#reference)

[![Ember Seam: dark architectural walls with a narrow seam of orange light](backgrounds/atlas-ember-seam.png)](https://xrefor.github.io/atlas-showcase/#wallpapers)

*Ember Seam — one of eight included backgrounds.*

<details>
<summary>Explore the eight wallpapers</summary>

<table>
<tr>
<td align="center"><a href="backgrounds/atlas-ember-seam.png"><img src="backgrounds/atlas-ember-seam.png" alt="Ember Seam" width="200"></a><br>Ember Seam</td>
<td align="center"><a href="backgrounds/atlas-boot.png"><img src="backgrounds/atlas-boot.png" alt="ATLAS Boot" width="200"></a><br>ATLAS Boot</td>
<td align="center"><a href="backgrounds/atlas-vault.png"><img src="backgrounds/atlas-vault.png" alt="ATLAS Vault" width="200"></a><br>ATLAS Vault</td>
<td align="center"><a href="backgrounds/atlas-thermal-horizon.png"><img src="backgrounds/atlas-thermal-horizon.png" alt="Thermal Horizon" width="200"></a><br>Thermal Horizon</td>
</tr>
<tr>
<td align="center"><a href="backgrounds/atlas-cinder-array.png"><img src="backgrounds/atlas-cinder-array.png" alt="Cinder Array" width="200"></a><br>Cinder Array</td>
<td align="center"><a href="backgrounds/atlas-umbra-core.png"><img src="backgrounds/atlas-umbra-core.png" alt="Umbra Core" width="200"></a><br>Umbra Core</td>
<td align="center"><a href="backgrounds/atlas-ember-causeway.png"><img src="backgrounds/atlas-ember-causeway.png" alt="Ember Causeway" width="200"></a><br>Ember Causeway</td>
<td align="center"><a href="backgrounds/atlas-obsidian-fold.png"><img src="backgrounds/atlas-obsidian-fold.png" alt="Obsidian Fold" width="200"></a><br>Obsidian Fold</td>
</tr>
</table>

[Browse the interactive collection](https://xrefor.github.io/atlas-showcase/#wallpapers).

</details>

## A consistent look, screen to screen

| Boot & login | Desktop & lock screen | Terminal & applications |
| --- | --- | --- |
| ATLAS branding across Limine, Plymouth, and SDDM, installed as an optional component. | Square Hyprland windows, thin orange focus borders, coordinated shell panels, and Matrix rain. | IBM Plex typography, tmux tabs, Starship prompts, Neovim syntax colors, and Yazi previews. |

| Carbon | Surface | Outline | Ivory | Signal |
| --- | --- | --- | --- | --- |
| `#100E0C` | `#1C1814` | `#3A342C` | `#D6CFC4` | `#FF5A12` |

## Screenshots

A quiet desktop, Python in Neovim, and files you can browse visually. The editor
shares the ATLAS palette, with warm syntax colors against carbon surfaces.

[![ATLAS in use: opening a Python script in Neovim, file browsing, and a brief Nym panel](docs/media/atlas-overview.gif)](https://xrefor.github.io/atlas-showcase/#screenshots)

*20 seconds on a real ATLAS desktop: desktop → Python in Neovim → files → Nym → desktop.
Recorded at the normal 9 pt terminal font size.*

[Watch with playback controls](https://xrefor.github.io/atlas-showcase/#screenshots) · [Download the 1080p video](docs/media/atlas-overview.mp4)

| Python, in the shared palette | The same character, at rest |
| --- | --- |
| [![Python script open in Neovim with the ATLAS Aether theme](docs/media/atlas-editor.png)](docs/media/atlas-editor.png) | [![ATLAS Matrix lock screen with warm ivory and orange characters](docs/media/atlas-lock.png)](docs/media/atlas-lock.png) |
| Ivory text, warm syntax colors, and carbon surfaces. | Matrix rain inside the lock surface, captured during Omarchy VM validation. |

<details>
<summary>A closer look: the NymVPN panel · optional integration</summary>

The tmux side panel brings live tunnel status, dVPN / Mixnet mode selection,
and settings into the ATLAS workspace. It requires the Nym daemon and a matching CLI.

[![ATLAS terminal workspace alongside the NymVPN controls](docs/media/atlas-terminal.png)](docs/media/atlas-terminal.png)

Open with **Ctrl+Space**, then **n**. [Panel controls and dependencies](docs/VPN.md).

</details>

## Install

**Version 1.0.0-rc4.** Tested against Omarchy **4.0.4-1**, Hyprland's Lua
configuration, and the Quickshell-based Omarchy shell. See
[compatibility](docs/COMPATIBILITY.md) and [release validation](docs/VALIDATION.md).

Clone the repository and run the one-command installer as your normal user:

```bash
git clone https://github.com/xrefor/omarchy-atlas-theme.git && cd omarchy-atlas-theme && ./install.sh
```

The script checks core dependencies, installs every user component, and activates
ATLAS. In a terminal, it first offers missing optional applications individually
(Yazi, Spotify Player, Lazygit, Lazydocker, Zen, and NymVPN). Each defaults to No;
AUR packages are identified before confirmation. If NymVPN is installed, a
separate prompt offers its missing `nym-vpnc` CLI, matched to the daemon version.
Boot configuration stays separate. Preview
the same operation with `./install.sh --dry-run`. If you downloaded a release
archive, extract it and run `./install.sh` inside the extracted directory.
Dry runs, staged installs and noninteractive runs skip optional package prompts.
To revisit the choices, run `python3 lib/atlas/optional.py`.

Existing enabled clones of the lock, idle, Polkit or monitor plugins conflict
with ATLAS shell styling. The prerequisite check lists all of them with
`omarchy plugin disable <id>` commands. Disable those you want ATLAS to replace
and rerun; their plugin files are preserved. To retain your clones, use
`python3 install.py --components theme,desktop,apps,cli` instead, then activate
with `omarchy theme set atlas`.

Open a new terminal and restart Zen after activation. Log out and back in to
propagate the font environment consistently. See the
[dependency list](docs/DEPENDENCIES.md) if the prerequisite check reports a
missing command. Optional application integrations, including Yazi, become active
when those applications are installed.

The extended shell uses the recipient's existing idle timeouts. Its Matrix
screensaver runs inside the secure lock surface, so it locks at the earlier of
screensaver and lock timeouts. See [authentication and shell](docs/AUTH.md).

<details>
<summary>Boot menu, Plymouth, and SDDM</summary>

The boot component is included in the same archive and installed explicitly:

```bash
sudo python3 install.py boot --dry-run
sudo python3 install.py boot
# After rebooting and checking the boot/login screens:
sudo python3 install.py boot-confirm
```

It backs up the recipient's current EFI partition and changed system files,
adds the ATLAS assets, updates appearance settings, and rebuilds boot images
when required. It preserves disk identifiers, boot entries, kernel parameters,
timeouts, default entry, and authentication policies. A private transaction
backup is retained until `boot-confirm`. Interrupted transactions are handled
with `boot-recover`; see the recovery conditions in the boot guide. It never
copies a boot image from the creator's machine.

Select individual surfaces with `--limine`, `--plymouth`, or `--sddm`.
See [boot installation and recovery](docs/BOOT.md) for supported partition
layouts, enrollment handling, and rollback.

</details>

<details>
<summary>Choose components</summary>

```bash
# Standard desktop colors, artwork and windows only:
python3 install.py --components theme

# Desktop fonts/toolkits/terminals and application workspace:
python3 install.py --components theme,desktop,apps

# Lock screen, Matrix rain, Polkit dialog and display widget:
python3 install.py --components shell

# Core network-command colors:
python3 install.py --components cli

# Optional CLI skins, selected explicitly:
python3 install.py --components cli --cli-groups cli-tcpdump,cli-metasploit,cli-shodan,cli-codex
```

`desktop` and `shell` also install the theme. Components share one installation
record, so later installation adds to the same backup baseline. The full archive
always contains every component regardless of the selected installation.

Omarchy's normal repository theme installer can load the root palette/artwork.
Omarchy restricts executable
theme files from downloaded repositories, so the complete experience uses the
local installer above.

</details>

## Reference

Component coverage, everyday controls, palette management, and recovery.

<details>
<summary>Included</summary>

| Surface | ATLAS treatment |
| --- | --- |
| Limine | ATLAS branding, carbon background, matching terminal colors |
| Plymouth | Original angular ATLAS wordmark, refined lock/password tile, progress line |
| SDDM | Matching logo, carbon login surface and warm password controls |
| Hyprland | Square windows, 1px focus borders, no shadows; desktop component adds 87% window opacity |
| Omarchy shell | Thin neutral outlines, orange focus, opaque panels; existing bar widgets and positions retained |
| Lock / authentication | Matrix rain, ATLAS tile and native Omarchy PAM/Polkit backend |
| Wallpapers | ATLAS Boot, ATLAS Vault, Ember Seam, Thermal Horizon, Cinder Array, Umbra Core, Ember Causeway, Obsidian Fold |
| Fonts / GTK | IBM Plex Mono and Sans, GTK3/GTK4 colors, Yaru orange icons |
| Terminals | Foot, Ghostty, Kitty and Alacritty preferences; palette generated by Omarchy |
| Neovim | ATLAS Aether theme, matching syntax palette and Python highlighting |
| NymVPN panel | Live ATLAS tunnel dashboard, dVPN/Mixnet mode and settings menus; optional Nym installation |
| tmux / Starship | Persistent ATLAS header, tabs, full directory path and compact Git status |
| Yazi | Native colors, file markers, bounded image previews and removable-drive menu |
| Zen | Browser chrome and browser-owned internal pages; native profile discovery |
| Spotify terminal player | Selection, playback, lyrics, border and progress colors |
| btop / LazyGit / Lazydocker | Native palette and panel styling |
| Bash / eza / ls / fzf / jq | Coordinated listing, search and data colors |
| Network tools / Metasploit / Shodan | Optional presentation wrappers and native console prompt |
| Codex | Native ATLAS syntax theme asset; select through the client's theme controls |
| Other Omarchy apps | Standard Omarchy generation from the shared palette, including Chromium, Obsidian and supported AI clients |

The proprietary graphical Spotify client, website content, and application
binaries are not modified. Wifite's visual adapter is included as reference
source, with its version and installation boundary documented; no machine-bound
root launcher is distributed. See [CLI coverage](docs/CLI.md).

</details>

<details>
<summary>Everyday terminal shortcuts</summary>

| Shortcut | Action |
| --- | --- |
| Super+Shift+F | Yazi |
| Super+Shift+Alt+M | Spotify terminal player |
| Ctrl+Space, then F | Files tab |
| Ctrl+Space, then M | Monitoring pane on wide terminals, tab on narrow terminals |
| Ctrl+Space, then S | Music tab |
| Ctrl+Space, then N | NymVPN panel (requires Nym daemon and matching CLI) |
| Ctrl+Space, then I | Directory summary |
| Alt+1 / Alt+2 / … | Switch terminal tabs |
| Ctrl+B | Alternative tmux prefix |

Press the prefix, release it, then press the lowercase letter. In Yazi, **Enter**
enters directories and opens files with their normal application; **Right** / **l**
also enters directories. **M** or
**g m** opens Drives. The drive menu uses UDisks/Polkit for mount and eject actions.

See [VPN panel controls and dependencies](docs/VPN.md).

</details>

<details>
<summary>One palette</summary>

The palette lives in `~/.config/omarchy/themes/atlas/colors.toml` after installation.
Apply changes with `omarchy theme set atlas`. The application hook reads the
active resolved Omarchy palette, so it also follows other themes.

```bash
atlas-theme sync          # regenerate managed application colors
atlas-theme check         # report drift; exit nonzero if regeneration is needed
atlas-theme doctor --all  # check dependencies
```

Templates live in `components/apps/templates/` and `components/desktop/themed/`.
The installed runtime is self-contained in `~/.local/share/atlas/`; the extracted
archive can be removed after installation. Manual edits to managed files stop
updates/removal until reconciled, rather than being silently overwritten.

</details>

<details>
<summary>ATLAS settings</summary>

Open **Omarchy → ATLAS**, or run `atlas-settings`. The menu includes the native
wallpaper picker, window opacity (80%, **87% default**, 95%, 100%), component
status, local diagnostics, shortcuts, and a preview before restoring saved files.
Fullscreen and application-specific opacity exceptions retain their existing
rules. The terminal font stays at **9 pt**.

Neovim's explorer, picker, completion, command dialogs, help overlays and normal
status line share the active palette's accent. Syntax, Git changes, diagnostics,
and editing modes retain their semantic colors, including after theme switches.

Settings use the installer's existing backup journal. Later manual edits block
changes until reconciled. See [settings and diagnostics](docs/SETTINGS.md).

</details>

<details>
<summary>Remove</summary>

Select a different Omarchy theme before restoring user files:

```bash
omarchy theme set "Tokyo Night"
atlas-theme restore --dry-run
atlas-theme restore
```

User originals and installed snapshots are recorded privately under
`~/.local/state/atlas-bundle/`. Original file modes and symlinks are restored;
files introduced by the bundle are removed. This directory is local state and
must never be included in a shared archive. An interrupted user installation
can be rolled back with `atlas-theme recover` or `python3 install.py recover`.

For boot removal, use the extracted bundle:

```bash
sudo python3 install.py boot-restore --dry-run
sudo python3 install.py boot-restore
```

Boot removal rebuilds the current installed kernel with the restored appearance.
It does not downgrade to the boot image saved during the original installation.

</details>

<details>
<summary>Development and sharing</summary>

```bash
python3 tools/check.py
python3 tools/build.py
```

The build writes `dist/atlas-1.0.0-rc4.tar.gz` and a SHA-256 sidecar. The archive
contains a per-file hash manifest, source, artwork, component installers, tests,
licenses and documentation. It excludes caches, backups, account profiles,
application logs, screenshots of personal content and hardware configuration.

See [release validation](docs/VALIDATION.md), [credits](docs/CREDITS.md), and
[renaming/migration](docs/MIGRATION.md). MIT license applies to project source;
upstream notices are retained in `LICENSES/`.

ATLAS is the new name for the earlier Blackburn customization.

</details>

---

**ATLAS / Carbon. Ivory. Signal.** · [Credits](docs/CREDITS.md) · [License](LICENSE) · [Explore ATLAS](https://xrefor.github.io/atlas-showcase/)
