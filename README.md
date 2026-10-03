# apps.illixion.com

The AltStore / SideStore source for Illixion's iPhone and iPad apps, and a one-page installer for
it. What each app does lives on [illixion.com](https://illixion.com/#apps) and in each app's repo. Cloudflare Pages serves `Website/` as-is; IPAs live in this repo's GitHub releases.

`catalog.json` is the only file edited by hand. `Website/source.json` and `Website/index.html` are
generated from it. One source file serves both AltStore and SideStore.

## Shipping a build

```sh
scripts/altsource.py build convolution          # unsigned archive -> dist/convolution-<ver>-<build>.ipa
scripts/altsource.py release convolution --notes "What changed"   # --dry-run to preview
git add -A && git commit && git push            # Pages redeploys
```

`build` pins the bundle id to the one in the catalog and refuses an IPA that embeds extensions or a
Watch app, because each one costs a free Apple ID another App ID. Bump the app's build number first;
`release` rejects a version already in the catalog.

## Deploy

Cloudflare Pages builds from this repo on every push to `main`: no build command, output
directory `Website`, custom domain `apps.illixion.com`. A release is therefore `release` plus a
commit and push; the IPA itself is already on GitHub by then.

## Adding an app

Add an entry to `catalog.json` (bundle id, icon under `Website/icons/`, `build.project` relative to
`$HOME`, `build.scheme`), then build and release it. Keep a Mac or Apple TV build out of this source:
AltStore only installs iPhone and iPad apps.
