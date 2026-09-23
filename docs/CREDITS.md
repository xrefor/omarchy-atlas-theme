# Credits and artwork provenance

- Original ATLAS palette, angular wordmark, wallpapers, layout and integration
  work: ATLAS contributors. The project developed from the user's Blackburn
  customization; the original copyright notice remains in `LICENSE`.
- [Omarchy](https://github.com/omacom/omarchy): desktop conventions, configuration
  baseline, Plymouth/SDDM layout and Quickshell plugin sources. Its MIT notice is
  retained in `LICENSES/Omarchy-MIT.txt`. Cloned plugin manifests retain their
  source identities.
- [mount.yazi](https://github.com/yazi-rs/plugins/tree/main/mount.yazi): adapted
  removable-drive menu, based on commit
  `4dc7f1b6458c2578f4494f10d468c68c1082214f`. MIT notice retained in
  `LICENSES/mount.yazi-MIT.txt`. The adaptation uses UDisks/Polkit and adds checks
  for internal devices, mounted siblings, busy unmounts and optical media.
- [Aether](https://github.com/bjarneo/aether.nvim): editor theme dependency
  referenced by configuration; its implementation is not bundled.
- [NymVPN](https://nym.com/): the decentralized VPN developed by
  [Nym Technologies SA](https://nym.com/trust-center) in Switzerland. ATLAS
  supplies the optional terminal panel; Nym's VPN software and network are
  separate from the theme.
- IBM Plex, Nerd Fonts, Yaru, Omarchy applications and security tools are external
  dependencies and remain under their respective licenses.

## Artwork

`assets/atlas.svg` is the original angular ATLAS wordmark, composed of vector
paths. `assets/wallpaper.svg` places that wordmark on the carbon background.
The bundled Plymouth/SDDM/desktop marks use this artwork, replacing older local
logo assets whose provenance was not documented. Password entry and padlock
assets are generated from the bundled original SVG sources. The remaining
small boot UI assets derive from the Omarchy MIT theme baseline.

Ember Seam, ATLAS Vault, Thermal Horizon and Cinder Array were generated for the
earlier theme with the image generation tool. Their historical generation prompts
are preserved in [wallpaper notes](WALLPAPER.md) and
[collection notes](WALLPAPER-COLLECTION.md), with ATLAS filenames. Umbra Core,
Ember Causeway and Obsidian Fold were first generated with the built-in image
generation tool on September 15, 2026; that historical generation is recorded in
[wallpaper additions](WALLPAPER-ADDITIONS-2026-09-15.md).

On September 18, 2026, those seven wallpapers were rerendered with AI image
generation and resized for the current 3440 × 1440 distribution. The repository
does not record the exact rerender prompts or generator-output hashes, so the
historical prompts and hashes are not presented as provenance for the current
pixels. The known rerender dimensions and processing are recorded in the
[showcase media notes](media/README.md). No game media, personal photographs or
unrelated stock wallpapers are included.

`docs/SOURCE-INVENTORY.json` records selected original source assets and hashes
from before the rerender; the four affected wallpaper entries it contains are
labelled with that historical scope. It is neither a hash inventory of the
current wallpaper bytes nor a dump of home configuration. Current distribution
files are covered by the release SHA256SUMS.
