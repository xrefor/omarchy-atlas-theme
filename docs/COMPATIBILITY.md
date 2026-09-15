# Compatibility

The reference workstation uses these installed Arch package versions:

| Package | Version |
| --- | --- |
| omarchy | 4.0.3-1 |
| hyprland | 0.56.2-2 |
| quickshell | 0.3.1-1 |
| limine | 12.8.0-1 |
| plymouth | 26.134.222-2 |
| sddm | 0.21.0-7 |
| yazi | 26.9.1-2 |
| tmux | 3.7_c-1 |
| spotify-player | 0.24.1-1 |
| python | 3.14.7-1 |

The installed Omarchy source version file reports `4.0.0.alpha`; the package
manager reports `4.0.3-1`. This bundle records both rather than treating that
source marker as a reliable release constraint. Capability checks are used by
the installer. Other combinations need validation, especially shell plugins
which use Omarchy's internal Quickshell components.

Omarchy installations using the older Waybar/Hyprlock/config-file architecture
are not supported by the complete bundle. The root semantic palette and artwork
may still be usable through their normal theme mechanism.

Fonts, fractional scaling, display names, GPU settings, keyboard layout,
lid handling, authentication policy, and idle timeouts are recipient-owned.
No monitor layout, disk UUID, boot command line, private account configuration,
Wi-Fi settings or browser profile directory is copied from the author.

The desktop component installs reviewed terminal preference files (font, padding,
cursor and key encoding), with originals backed up. The apps component adds
tmux/Yazi shortcuts and merges supported native app configuration. It refuses
an existing unrelated Foot shell command. The shell component preserves bar
placement/widgets and refuses other enabled authentication clones.

Palette switching is separate from uninstalling layout/font integrations.
Restoring the bundle recovers its file baseline; Omarchy manages its own current
theme state, application activation and desktop settings through theme selection.

## References

- [Omarchy source and manual](https://github.com/omacom/omarchy)
- [Limine configuration reference](https://github.com/limine-bootloader/limine/blob/trunk/CONFIG.md)
- [Yazi mount plugin](https://github.com/yazi-rs/plugins/tree/main/mount.yazi)

References were consulted during packaging. The installed source and the
versions above are the tested integration baseline, rather than an assumption
that future upstream changes are compatible.
