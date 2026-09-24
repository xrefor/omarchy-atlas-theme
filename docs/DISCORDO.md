# Discordo customization

The `apps` component merges the ATLAS presentation into Discordo's normal
`~/.config/discordo/config.toml`. The source is
`components/apps/templates/discordo.toml` and is regenerated from the active
Omarchy palette by `atlas-theme sync`.

The overlay owns `[theme.*]`, sidebar width/markers/indents, channel-type icons,
timestamp/date formats and attachment-link presentation. Editor, keybindings,
notifications, authentication, account state and other settings are retained.
Existing file permissions are preserved; a newly created config is private
(`0600`). ATLAS restoration recovers the configuration that preceded installation.

ATLAS also ships the source-level presentation customization used for its
Discordo build:

- `components/apps/discordo/atlas.patch` contains the code and focused Go tests;
- `components/apps/discordo/BASE_COMMIT` pins the reviewed upstream revision;
- `components/apps/discordo/README.md` documents its scope and build procedure;
- `LICENSES/Discordo-GPL-3.0.txt` carries the applicable upstream license.

The patch cleans decorative navigation labels without changing the underlying
Discord names or IDs, preserves original names for search, applies the ATLAS
selection and message hierarchy, shortens displayed automatic links without
changing their destinations, and presents attachments as clickable filenames.
It does not modify Discord API requests, authentication, token storage,
notifications or account/server data. Displayed labels may be less descriptive
than their original Discord names; confirm the selected channel context before
sending sensitive material.

Discordo remains an external optional application. ATLAS does not ship or
automatically replace a Discordo executable, and it never ships tokens or other
account data. Install Discordo separately, then install the ATLAS `apps`
component or sync an installation after this integration has been installed:

```sh
python3 install.py install --components apps
# Later active-palette changes are applied with:
atlas-theme sync
```

The palette overlay works with an ordinary compatible Discordo release. The
optional source patch applies specifically to upstream commit
`e87645a180accc64f6bcc332d19080f90f0ac39f`; apply and test it from a clean
checkout using the commands in
[`components/apps/discordo/README.md`](../components/apps/discordo/README.md).
After installing the `apps` component, that material is also copied to
`~/.local/share/atlas/components/apps/discordo/`.

Future Discordo releases may change their source or configuration schema. Rebase
and review the patch before applying it to another revision. Replacing a custom
build with an upstream executable removes the source-level presentation changes;
the palette overlay remains separate. Discordo's upstream Terms-of-Service
warning also applies to custom builds.
