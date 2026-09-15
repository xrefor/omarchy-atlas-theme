# Wifite reference skin

`theme.py` is the presentation-only adapter tested with kimocoder wifite2
2.9.9-beta classic mode. It changes colors, banner, interface menu, and scan
refresh layout. It does not select targets or alter attack operations.

It is source material, not an installed component. Wifite normally runs with
root privileges; executing a mutable file from a user's home through `sudo`
would cross that boundary unsafely. A downstream package must install the
adapter, its entrypoint, and the `atlas_cli` dependency as root-owned files;
pin a compatible Wifite build; set `ATLAS_THEME_HOME` to the unprivileged
user's home; then import `theme` and call `apply()` before importing Wifite's
`main`.

Wifite's internal Python classes are not a stable plugin API. Re-test this
adapter when upgrading Wifite.
