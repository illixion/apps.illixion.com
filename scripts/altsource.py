#!/usr/bin/env python3
"""Keep the apps.illixion.com AltStore / SideStore source in step with each app's releases.

    altsource.py sync [slug] [--dry-run]  add each app's newest GitHub release to catalog.json,
                                          then regenerate the site
    altsource.py site                     regenerate both sources and the install page

There are two sources: source.json for iPhone and iPad (AltStore or SideStore) and
source-visionos.json for Apple Vision Pro (SideStore's visionOS port). A source format has no
per-platform downloads, so each platform gets its own file.

Each app's own CI builds the iPhone/iPad IPA and attaches it to every release under one fixed
name (catalog.json: release.asset). This repo hosts no binaries: a version's downloadURL is
that asset under its release's tag, which never changes, so the size and SHA-256 recorded
here stay true. releases/latest/download/<asset> is the moving link for people, not for the
source.

catalog.json is the one hand-edited file. Everything under Website/ that is not an icon or
screenshot is generated from it.
"""
import argparse, hashlib, html, io, json, os, plistlib, re, subprocess, sys, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "catalog.json")
SITE = os.path.join(ROOT, "Website")


def load():
    with open(CATALOG) as f:
        return json.load(f)


def save(cat):
    with open(CATALOG, "w") as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)
        f.write("\n")


def app_for(cat, slug):
    for a in cat["apps"]:
        if a["slug"] == slug:
            return a
    sys.exit(f"no app '{slug}' in catalog.json")


# ---------------------------------------------------------------- sync

def newest_release(repo, asset):
    """The newest published release of repo that carries asset, and that asset."""
    out = subprocess.run(["gh", "api", f"repos/{repo}/releases?per_page=30"],
                         check=True, capture_output=True, text=True).stdout
    for rel in json.loads(out):
        if rel["draft"] or rel["prerelease"]:
            continue
        for a in rel["assets"]:
            if a["name"] == asset:
                return rel, a
    return None, None


def inspect_ipa(data):
    """Info.plist of the IPA's app, and any extension or Watch app bundles it embeds."""
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    plists = [n for n in names if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n)]
    if len(plists) != 1:
        sys.exit(f"expected one app in the IPA, found {len(plists)}")
    info = plistlib.loads(z.read(plists[0]))
    embedded = sorted({m.group(1) for n in names
                       if (m := re.match(r"Payload/[^/]+\.app/(PlugIns|Watch|Extensions)/", n))})
    return info, embedded


# An app has one track per source: its iPhone/iPad build (bundle id, versions and privacy at the
# top level of the catalog entry) and, optionally, a visionOS build under "visionos" with its own.
PLATFORMS = {"ios": "iPhone/iPad", "visionos": "visionOS"}


def tracks(app):
    yield "ios", app["release"]["asset"], app
    if "visionos" in app:
        yield "visionos", app["visionos"]["asset"], app["visionos"]


def check_platform(platform, info):
    """Why the IPA can't go in this platform's source, or None."""
    sdk = info.get("DTPlatformName", "")
    family = set(info.get("UIDeviceFamily", []))
    if platform == "visionos":
        return None if sdk == "xros" else f"not a visionOS build (DTPlatformName {sdk!r})"
    if sdk == "xros" or (family and not {1, 2} & family):
        return f"not an iPhone or iPad build (DTPlatformName {sdk!r}, UIDeviceFamily {sorted(family)})"
    return None


def sync_track(app, platform, asset_name, track, dry):
    name = f"{app['slug']} ({PLATFORMS[platform]})"
    repo = app["release"]["repo"]
    rel, asset = newest_release(repo, asset_name)
    if not rel:
        print(f"{name}: no release of {repo} has {asset_name} yet")
        return False
    url = asset["browser_download_url"]
    if any(v["downloadURL"] == url for v in track["versions"]):
        print(f"{name}: up to date ({rel['tag_name']})")
        return False

    print(f"{name}: downloading {url}", flush=True)
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    sha = hashlib.sha256(data).hexdigest()
    if asset.get("digest") and asset["digest"] != f"sha256:{sha}":
        sys.exit(f"{name}: download does not match GitHub's digest {asset['digest']}")
    info, embedded = inspect_ipa(data)
    if info["CFBundleIdentifier"] != track["bundleIdentifier"]:
        sys.exit(f"{name}: IPA is {info['CFBundleIdentifier']}, catalog says {track['bundleIdentifier']}")
    if embedded:
        sys.exit(f"{name}: IPA embeds {embedded}; the sources ship extension-free builds")
    if why := check_platform(platform, info):
        sys.exit(f"{name}: IPA is {why}")
    version, build_no = info["CFBundleShortVersionString"], info["CFBundleVersion"]
    # AltStore and SideStore offer an update only when the build grows.
    if track["versions"] and int(build_no) <= int(track["versions"][0]["buildVersion"]):
        sys.exit(f"{name}: build {build_no} of {rel['tag_name']} is not newer than "
                 f"{track['versions'][0]['buildVersion']}")

    entry = {
        "version": version, "buildVersion": build_no,
        "date": rel["published_at"],
        "localizedDescription": f"Built from {rel['tag_name']}. What changed: {rel['html_url']}",
        "downloadURL": url, "size": len(data), "sha256": sha,
        "minOSVersion": info.get("MinimumOSVersion", ""),
    }
    print(f"{name}: {version} ({build_no}) from {rel['tag_name']}, {len(data) / 1e6:.1f} MB")
    if dry:
        return False
    track["privacy"] = {k: v for k, v in sorted(info.items()) if k.endswith("UsageDescription")}
    track["versions"].insert(0, entry)
    return True


def sync(slug, dry):
    cat = load()
    apps = [app_for(cat, slug)] if slug else cat["apps"]
    changed = [f"{a['slug']} ({PLATFORMS[p]})" for a in apps for p, asset, t in tracks(a)
               if sync_track(a, p, asset, t, dry)]
    if changed:
        save(cat)
        write_site(cat, SITE)
        print("updated:", ", ".join(changed))


# ---------------------------------------------------------------- site

SOURCE_FILES = {"ios": "source.json", "visionos": "source-visionos.json"}


def source_meta(cat, platform):
    """The source's own fields; the visionOS source overrides the shared ones it names."""
    s = dict(cat["source"])
    s.update(s.pop("visionos", {}) if platform == "visionos" else {})
    s.pop("visionos", None)
    return s


def source_json(cat, platform="ios"):
    s = source_meta(cat, platform)
    base = s["website"].rstrip("/")
    apps = []
    for a in cat["apps"]:
        t = a if platform == "ios" else a.get("visionos")
        if not t or not t["versions"]:
            continue
        latest = t["versions"][0]
        d = {
            "name": a["name"], "bundleIdentifier": t["bundleIdentifier"],
            "developerName": s["developerName"], "subtitle": a["subtitle"],
            "localizedDescription": t.get("localizedDescription", a["localizedDescription"]),
            "iconURL": f"{base}/{a['icon']}", "tintColor": a["tintColor"],
            "versions": t["versions"],
            "appPermissions": {"entitlements": [], "privacy": t.get("privacy", {})},
            # Older clients read the newest version from the app itself.
            "version": latest["version"], "versionDate": latest["date"],
            "versionDescription": latest["localizedDescription"],
            "downloadURL": latest["downloadURL"], "size": latest["size"],
        }
        shots = t.get("screenshots", a.get("screenshots") if platform == "ios" else None)
        if shots:
            d["screenshotURLs"] = [f"{base}/{p}" for p in shots]
        apps.append(d)
    return {
        "name": s["name"], "identifier": s["identifier"], "subtitle": s["subtitle"],
        "description": s["description"], "iconURL": f"{base}/{s['icon']}",
        "website": base, "tintColor": s["tintColor"],
        "featuredApps": [a["bundleIdentifier"] for a in apps],
        "apps": apps, "news": cat.get("news", []),
    }


def esc(x):
    return html.escape(x, quote=True)


def app_html(a):
    v = a["versions"][0]
    detail = f"Version {v['version']}, iOS {v['minOSVersion']} or later, {v['size'] / 1_000_000:.1f} MB"
    gh = a["links"].get("github")
    src = f' <a href="{esc(gh)}">Source</a>' if gh else ""
    return f"""      <li>
        <img src="{esc(a['icon'])}" width="48" height="48" alt="">
        <div>
          <h3>{esc(a['name'])}</h3>
          <p>{esc(a['subtitle'])}</p>
          <p class="muted">{esc(detail)}.{src}</p>
        </div>
      </li>"""


def page(cat):
    s = cat["source"]
    base = s["website"].rstrip("/")
    released = [a for a in cat["apps"] if a["versions"]]
    apps = "\n".join(app_html(a) for a in released) or \
        '      <li class="muted">No builds are published yet.</li>'
    vision = [a["name"] for a in cat["apps"] if a.get("visionos", {}).get("versions")]
    vision_apps = (" and ".join([", ".join(vision[:-1]), vision[-1]]) if len(vision) > 1 else
                   (vision[0] if vision else "none are published yet"))
    t = open(os.path.join(ROOT, "scripts", "index.template.html")).read()
    for k, val in {"SOURCE_URL": f"{base}/{SOURCE_FILES['ios']}",
                   "VISION_SOURCE_URL": f"{base}/{SOURCE_FILES['visionos']}",
                   "VISION_APPS": esc(vision_apps), "TITLE": esc(s["name"]),
                   "TAGLINE": esc(s["tagline"]), "ABOUT": esc(s["about"]), "APPS": apps}.items():
        t = t.replace("{{" + k + "}}", val)
    return t


def write_site(cat, site):
    os.makedirs(site, exist_ok=True)
    for platform, filename in SOURCE_FILES.items():
        with open(os.path.join(site, filename), "w") as f:
            json.dump(source_json(cat, platform), f, indent=2, ensure_ascii=False)
            f.write("\n")
    with open(os.path.join(site, "index.html"), "w") as f:
        f.write(page(cat))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    y = sub.add_parser("sync")
    y.add_argument("slug", nargs="?")
    y.add_argument("--dry-run", action="store_true")
    sub.add_parser("site")
    a = p.parse_args()
    if a.cmd == "sync":
        sync(a.slug, a.dry_run)
    else:
        write_site(load(), SITE)


if __name__ == "__main__":
    main()
