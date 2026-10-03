# apps.illixion.com

The AltStore / SideStore source for Illixion's iPhone and iPad apps, and a one-page installer for
it. What each app does lives on [illixion.com](https://illixion.com/#apps) and in each app's repo. Cloudflare Pages serves `Website/` as-is. This repo holds no IPAs: each app's own CI attaches them to
that app's GitHub releases, and the source points there.

`catalog.json` is the only file edited by hand. `Website/source.json` and `Website/index.html` are
generated from it. One source file serves both AltStore and SideStore.

## Shipping a build

Each app's CI (`.github/workflows/build.yml` in its repo) archives the iPhone/iPad app unsigned on
every push to `main`, checks that it embeds no extension or Watch app (each one costs a free Apple ID
another App ID), and attaches it to the release under one fixed name, such as
`Longwave-iOS-unsigned.ipa`. Its build number is the commit count, so it grows with every release and
AltStore offers the update. Then, here:

```sh
scripts/altsource.py sync --dry-run      # what each app's newest release would add
scripts/altsource.py sync                # record it in catalog.json, regenerate Website/
git add -A && git commit && git push     # Pages redeploys
```

`sync` downloads each new IPA once to read its version, size and SHA-256, and refuses one with the
wrong bundle id, an embedded extension, no iPhone or iPad support, or a build number that isn't
higher than the last. A version's `downloadURL` is the asset under its release tag, which never
changes. `https://github.com/<repo>/releases/latest/download/<asset>` always serves the newest build,
which is the link to give people, but the source can't use it: its recorded size and hash would stop
matching at the next release.

## Deploy

Cloudflare builds from this repo on every push to `main`. `wrangler.jsonc` serves `Website/` as
static assets (no Worker script, no build command; the deploy command is `npx wrangler deploy`),
with `apps.illixion.com` as the custom domain. A release is therefore `sync` plus a commit and
push; the IPA itself is already on GitHub by then.

## Adding an app

Add an iPhone/iPad archive and a fixed-name IPA to the app's own release workflow (copy Worldcast's,
the smallest). Then add an entry to `catalog.json`: bundle id, icon under `Website/icons/`, and
`release.repo` / `release.asset`. Keep a Mac or Apple TV build out of this source: AltStore only
installs iPhone and iPad apps.
