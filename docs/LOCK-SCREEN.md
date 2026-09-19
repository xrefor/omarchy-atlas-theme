# Lock-screen styles

The optional `shell` component includes two appearances for the same Omarchy
session-lock service:

- **Classic**: the existing Matrix screensaver, blurred wallpaper and framed
  password field. This remains the default for new installations.
- **Terminal**: a centered ATLAS logo, a borderless 9 pt IBM Plex Mono prompt,
  a grey `>` blinking every 1.2 seconds, asterisk masking and a thin orange
  caret. It opens directly to password input. The mouse pointer stays hidden,
  and mouse movement, buttons and scrolling do not interact with the prompt.

Choose **ATLAS → Lock screen → Terminal / Classic**, or run:

```sh
atlas-lock-style terminal
atlas-lock-style classic
atlas-lock-style toggle
atlas-lock-style current
```

The preference lives in `~/.config/atlas/lock-style`. Changes made through the
command use the installation journal, survive reinstall/update, and restore
the original preference when ATLAS is removed. A missing preference selects
Classic. If the screen is already locked, a style change applies to the next
lock; it does not replace a live password field.

Both styles share the existing password and fingerprint PAM flows, input
masking, failure feedback, Caps Lock hint and session-lock ownership. ATLAS
does not install or alter PAM policy. See [AUTH.md](AUTH.md).

Omarchy keeps lock services loaded during plugin rescans. After installing or
upgrading the plugin, restart the shell while **unlocked** with
`omarchy restart shell`, or log out and back in. Ordinary style changes then
apply without a restart.

The rc5 automated checks cover preference preservation, restoration, invalid
and modified preference handling, QML loading and both visual styles. See
[VALIDATION.md](VALIDATION.md) for live authentication and hardware limits.
