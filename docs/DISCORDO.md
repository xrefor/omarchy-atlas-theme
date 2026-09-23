# Discordo theme

The `apps` component merges the ATLAS visual palette into Discordo's normal
`~/.config/discordo/config.toml`. The source is
`components/apps/templates/discordo.toml` and is regenerated from the active
Omarchy palette by `atlas-theme sync`.

The overlay owns only `[theme.*]` tables. It does not change Discordo behavior,
keybindings, sidebar layout, notifications, account state or authentication.
Existing non-theme settings are retained, and ATLAS restoration recovers the
configuration that preceded installation.

Discordo remains an external optional application. ATLAS does not install or
ship a Discordo executable, wrapper, fork, patch, token or other account data.
Install Discordo separately, then install the ATLAS `apps` component or sync an
installation after this integration has been installed:

```sh
python3 install.py install --components apps
# Later active-palette changes are applied with:
atlas-theme sync
```

The theme schema was checked against upstream Discordo commit
`de2f2c94f0fc128730a90d88f3c3a7fb3b67dc92`. Future Discordo releases may alter
their configuration schema; ATLAS treats Discordo as optional and does not
replace its application code.
