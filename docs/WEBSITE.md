# ATLAS showcase website

The repository README uses GitHub-supported Markdown and HTML. `index.html`
contains the full interactive showcase: the ATLAS palette, wallpaper selector,
playback controls, and expandable reference sections.

The website is published from the separate public `xrefor/atlas-showcase`
repository. The public theme source and installation guides live in
`xrefor/omarchy-atlas-theme`. The Pages address is:

https://xrefor.github.io/atlas-showcase/

## Build and preview

From the repository root:

```bash
python3 tools/build_site.py
python3 -m http.server 8000 --directory dist/site --bind 127.0.0.1
```

Open `http://127.0.0.1:8000`. The builder validates asset paths and anchors,
then copies only the page and the local files it references into `dist/site`.
The repository source, backups, and unrelated files are not in the Pages artifact.
Documentation links point to their rendered Markdown on GitHub.

## Publishing

The public showcase repository uses **GitHub Actions** as its Pages source.
Its `Publish ATLAS showcase` workflow publishes changes from `main`.
The theme source repository does not have a Pages deployment workflow.

After editing this repository's `index.html` or showcase media, build the site
and copy the resulting static files to the adjacent public checkout:

```bash
python3 tools/build_site.py
cp -a dist/site/. ../atlas-showcase/
```

Review and commit the changes in the public checkout before pushing. Preserve
its workflow, builder, README, and license. Copy only the generated `dist/site`
contents; never copy the theme repository or its Git history into that checkout.

The public page links directly to the theme source and technical guides. Keep
its release version and installation instructions aligned with the theme README.

## Media

The overview GIF and MP4 share the same 20-second edit. The Python scene uses
the installed **9 pt** IBM Plex Mono configuration, with its normal fallback font.
Do not increase the font size for showcase recordings. See
[capture provenance](media/README.md) for the sequence and source details.

The local working preview outside this repository is not a deployment input.
Edit `index.html` for the website and `README.md` for the repository landing page.
