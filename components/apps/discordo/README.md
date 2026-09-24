# ATLAS Discordo source customization

`atlas.patch` contains the optional source-level presentation changes used by
the ATLAS Discordo build. It applies to upstream Discordo commit
`e87645a180accc64f6bcc332d19080f90f0ac39f`, recorded in `BASE_COMMIT`.

The patch is kept beside the palette overlay instead of shipping a fork or
binary. It changes local rendering only:

- navigation labels omit decorative emoji and symbol clusters while original
  Discord names, IDs and searchable text remain unchanged;
- sidebar, picker, mentions, composer, message headers, replies, embeds and
  selected rows use the ATLAS presentation hierarchy;
- attachments retain their clickable destination while displaying filenames;
- long automatic web links receive compact labels without changing targets;
- focused Go tests cover label identity, search, link targets, selection,
  wrapping, reply previews, attachment labels and message spacing.

The patch does not change Discord API requests, authentication, token storage,
notifications or account/server data. The presentation overlay in
`components/apps/templates/discordo.toml` remains independently usable with an
unmodified compatible Discordo release.

## Apply and build

Use a clean checkout and the Go version required by the pinned Discordo source:

```sh
git clone https://github.com/ayn2op/discordo.git
cd discordo
git checkout e87645a180accc64f6bcc332d19080f90f0ac39f
git apply --check /path/to/omarchy-atlas-theme/components/apps/discordo/atlas.patch
git apply /path/to/omarchy-atlas-theme/components/apps/discordo/atlas.patch
go mod verify
go test ./internal/ui/... ./internal/config/... ./internal/markdown/...
go build -trimpath \
  -ldflags='-s -w -X github.com/ayn2op/discordo/cmd.localVersion=v0.0.0-20260912213006-e87645a180ac+atlas.2' \
  -o discordo-atlas .
```

After an ATLAS `apps` installation, the same patch and metadata are available
under `~/.local/share/atlas/components/apps/discordo/`. Building does not require
or read an existing Discordo configuration or account token. ATLAS does not
replace an installed executable automatically.

Discordo warns that automated user accounts or self-bots violate Discord's
Terms of Service. Review upstream's current guidance before using the client.

This patch is a derivative of GPL-3.0-licensed Discordo source and is distributed
under GPL-3.0; see `LICENSES/Discordo-GPL-3.0.txt`. The rest of ATLAS retains its
existing licensing.
