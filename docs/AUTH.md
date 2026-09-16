# ATLAS authentication and shell plugins

The bundle ships four Omarchy shell clones under `components/desktop/plugins`:

- `atlas.lock` keeps Omarchy's session-lock and PAM implementation and adds the ATLAS password tile, caps-lock feedback, and embedded Matrix rain.
- `atlas.polkit` keeps Quickshell's native Polkit agent and changes only its presentation and user feedback.
- `atlas.idle` derives from Omarchy's idle service and hands the first configured idle event directly to `omarchy-system-lock`, where `atlas.lock` renders Matrix rain inside the secure lock surface.
- `atlas.monitor` derives from the stock monitor panel and adds the Night Light row. It uses Omarchy's normal monitor, display-text-size, brightness, and OSD commands.

Each manifest retains `omarchy.clonedFrom`, so Omarchy grants only the capabilities of the corresponding built-in plugin. The original Omarchy portions are distributed under the MIT license in `LICENSES/Omarchy-MIT.txt`.

## Security boundary

This bundle does not install or modify PAM policy, fingerprint enrollment, Polkit policy, sudo configuration, or authentication helpers. In particular, it deliberately excludes the workstation's file-based `askpass` IPC bridge and all password result/done files. Privileged terminal commands keep using their normal terminal password prompt or Polkit path.

`atlas.lock` references the supported PAM services that Omarchy itself installs:

- `/etc/pam.d/omarchy-lock-password`
- `/etc/pam.d/omarchy-lock-fingerprint` when fingerprint unlock is configured

`atlas.polkit` reads `/etc/pam.d/polkit-1` only to decide whether to show a fingerprint hint. Quickshell's `PolkitAgent` owns the authorization conversation.

The local `~/.local/bin/omarchy-brightness-display` hardware fallback is also excluded. `atlas.monitor` calls the stock command name, so supported DDC or backlight hardware works as Omarchy intends; machines without supported brightness control simply omit that row. Night Light still works through `omarchy.nightlight`.

## Compatibility preflight

Before enabling these plugins, the installer should verify all of the following and stop without changing `shell.json` if any required check fails:

1. Omarchy is version 4.0.4 or a tested compatible release, and Quickshell is at least 0.3.1.
2. `omarchy plugin validate` accepts every `atlas.*` plugin directory.
3. `/etc/pam.d/omarchy-lock-password` is readable and non-empty. The fingerprint PAM file and `fprintd-list` are optional.
4. The commands `bash`, `hyprctl`, `omarchy-shell`, `omarchy-system-lock`, `omarchy-system-wake`, `omarchy-hyprland-session-locked`, `omarchy-hw-laptop-closed`, `omarchy-launch-screensaver`, `omarchy-monitor-state`, `omarchy-display-text-size`, `omarchy-hyprland-monitor-scaling`, and `omarchy-brightness-display` resolve.
5. The separate terminal Matrix script additionally requires `ttfx`, `jq`, `pgrep`, `pkill`, `stty`, and `tty`. The native Matrix lock presentation does not require `ttfx` or `jq`.
6. The theme installer has copied `components/desktop/branding/screensaver.txt` to `~/.config/omarchy/branding/screensaver.txt`. If it is absent, Matrix rain still runs but has no ATLAS mark to resolve into.
7. No other third-party clone of `omarchy.lock`, `omarchy.polkit`, `omarchy.idle`, or `omarchy.monitor` is enabled. Enabling two authentication clones can create competing lock or Polkit services.

The idle integration intentionally changes timing: the secure lock starts at the earlier of `idle.screensaver` and `idle.lock`. The Matrix animation is the screensaver and runs inside the session-lock surface. A key or meaningful pointer movement reveals the password tile; after 20 seconds without input, Matrix rain resumes.

## `shell.json` integration

Prefer `omarchy plugin enable` after the plugin folders are installed because it applies Omarchy's clone bookkeeping. For a deterministic installer, merge the following changes while preserving the user's unrelated bar entries and settings:

```bash
omarchy plugin enable atlas.monitor
omarchy plugin enable atlas.lock
omarchy plugin enable atlas.polkit
omarchy plugin enable atlas.idle
```

Run these only after all four folders have passed validation. The first command replaces the existing monitor entry in place; the service commands disable their respective built-ins through clone bookkeeping.

1. Replace the existing `omarchy.monitor` bar entry with `{ "id": "atlas.monitor" }` in the same section and position.
2. Add `{ "id": "atlas.lock" }`, `{ "id": "atlas.polkit" }`, and `{ "id": "atlas.idle" }` to `plugins` exactly once.
3. Add `omarchy.lock`, `omarchy.polkit`, and `omarchy.idle` to `disabledPlugins` exactly once.
4. Add `atlas.lock`, `atlas.polkit`, and `atlas.idle` to `cloneSourceRestores` exactly once. This lets Omarchy restore the built-ins if a clone is later disabled or removed.
The resulting relevant shape is:

```json
{
  "idle": {
    "screensaver": 600,
    "lock": 600
  },
  "bar": {
    "layout": {
      "right": [
        { "id": "atlas.monitor" }
      ]
    }
  },
  "plugins": [
    { "id": "atlas.lock" },
    { "id": "atlas.polkit" },
    { "id": "atlas.idle" }
  ],
  "disabledPlugins": [
    "omarchy.lock",
    "omarchy.polkit",
    "omarchy.idle"
  ],
  "cloneSourceRestores": [
    "atlas.lock",
    "atlas.polkit",
    "atlas.idle"
  ]
}
```

The abbreviated `right` array above illustrates replacement only; an installer must retain every other right-side widget. It should write the merged JSON atomically. Live lock, shell restart, and authentication tests belong to the post-install verification phase and must not run while packaging.
