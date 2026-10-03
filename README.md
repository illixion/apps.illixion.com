# apps.illixion.com

The AltStore / SideStore source for Illixion's iPhone and iPad apps, and the static page that
introduces it. Cloudflare Pages serves `Website/` as-is; IPAs live in this repo's GitHub releases.

`catalog.json` is the only file edited by hand. `Website/source.json` and `Website/index.html` are
generated from it. One source file serves both AltStore and SideStore.

## Shipping a build

```sh
scripts/altsource.py build convolution          # unsigned archive -> dist/convolution-<ver>-<build>.ipa
scripts/altsource.py release convolution --notes "What changed"   # --dry-run to preview
git add -A && git commit                        # then push; Pages redeploys
```

`build` pins the bundle id to the one in the catalog and refuses an IPA that embeds extensions or a
Watch app, because each one costs a free Apple ID another App ID. Bump the app's build number first;
`release` rejects a version already in the catalog.

## Deploy

```sh
npx wrangler pages deploy Website --project-name=apps-illixion
```

Then add `apps.illixion.com` under the project's Custom domains. No build command.

## Adding an app

Add an entry to `catalog.json` (bundle id, icon under `Website/icons/`, `build.project` relative to
`$HOME`, `build.scheme`), then build and release it. Keep a Mac or Apple TV build out of this source:
AltStore only installs iPhone and iPad apps.
