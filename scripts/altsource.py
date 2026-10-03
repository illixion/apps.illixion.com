#!/usr/bin/env python3
"""Build, release and publish the apps.illixion.com AltStore / SideStore source.

    altsource.py build <slug>            archive the app unsigned, package dist/<file>.ipa
    altsource.py release <slug> [--notes TEXT] [--dry-run]
                                         upload the built IPA to a GitHub release on this repo,
                                         record it in catalog.json, regenerate the site
    altsource.py site                    regenerate Website/source.json and Website/index.html

catalog.json is the one hand-edited file. Everything under Website/ that is not an icon or
screenshot is generated from it.
"""
import argparse, datetime, hashlib, html, json, os, plistlib, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "catalog.json")
DIST = os.path.join(ROOT, "dist")
SITE = os.path.join(ROOT, "Website")
HOME = os.path.expanduser("~")


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


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


# ---------------------------------------------------------------- build

def build(slug):
    cat = load()
    app = app_for(cat, slug)
    b = app["build"]
    work = os.path.join(DIST, "work", slug)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    archive = os.path.join(work, "a.xcarchive")
    cmd = ["xcodebuild", "-project", os.path.join(HOME, b["project"]), "-scheme", b["scheme"],
           "-configuration", "Release", "-destination", "generic/platform=iOS",
           "-archivePath", archive, "archive",
           "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", "CODE_SIGN_IDENTITY="]
    # A local, gitignored signing override can rename the bundle id on the author's machine;
    # pin it so the IPA always carries the id the catalog advertises.
    cmd.append(f"PRODUCT_BUNDLE_IDENTIFIER={app['bundleIdentifier']}")
    with open(os.path.join(work, "log.txt"), "w") as log:
        print(f"archiving {slug} (log: {work}/log.txt)", flush=True)
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        sys.exit(f"xcodebuild failed ({r.returncode}); see {work}/log.txt")

    apps = os.path.join(archive, "Products", "Applications")
    bundle = [d for d in os.listdir(apps) if d.endswith(".app")][0]
    src = os.path.join(apps, bundle)
    if b.get("stripWatch"):
        shutil.rmtree(os.path.join(src, "Watch"), ignore_errors=True)
    with open(os.path.join(src, "Info.plist"), "rb") as f:
        info = plistlib.load(f)
    if info["CFBundleIdentifier"] != app["bundleIdentifier"]:
        sys.exit(f"bundle id is {info['CFBundleIdentifier']}, catalog says {app['bundleIdentifier']}")
    extras = [p for p in ("PlugIns", "Watch", "Extensions") if os.path.isdir(os.path.join(src, p))]
    version, build_no = info["CFBundleShortVersionString"], info["CFBundleVersion"]
    name = f"{slug}-{version}-{build_no}.ipa"

    payload = os.path.join(work, "Payload")
    os.makedirs(payload)
    shutil.copytree(src, os.path.join(payload, bundle), symlinks=True)
    out = os.path.join(DIST, name)
    if os.path.exists(out):
        os.remove(out)
    run(["zip", "-qry", out, "Payload"], cwd=work)

    side = {
        "slug": slug, "file": name, "version": version, "buildVersion": build_no,
        "minOSVersion": info.get("MinimumOSVersion", ""),
        "size": os.path.getsize(out),
        "sha256": hashlib.sha256(open(out, "rb").read()).hexdigest(),
        "privacy": {k: v for k, v in sorted(info.items()) if k.endswith("UsageDescription")},
        "embeddedBundles": extras,
    }
    with open(os.path.join(DIST, f"{slug}.json"), "w") as f:
        json.dump(side, f, indent=2)
    print(json.dumps(side, indent=2))


# ---------------------------------------------------------------- release

def release(slug, notes, dry):
    cat = load()
    app = app_for(cat, slug)
    with open(os.path.join(DIST, f"{slug}.json")) as f:
        side = json.load(f)
    if side["embeddedBundles"]:
        sys.exit(f"{slug}: IPA still embeds {side['embeddedBundles']}; the source ships extension-free builds")
    tag = f"{slug}-{side['version']}-{side['buildVersion']}"
    repo = cat["source"]["repo"]
    url = f"https://github.com/{repo}/releases/download/{tag}/{side['file']}"
    if any(v["buildVersion"] == side["buildVersion"] and v["version"] == side["version"] for v in app["versions"]):
        sys.exit(f"{tag} is already in catalog.json; bump the app's build number")
    entry = {
        "version": side["version"], "buildVersion": side["buildVersion"],
        "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "localizedDescription": notes or f"{app['name']} {side['version']}",
        "downloadURL": url, "size": side["size"], "sha256": side["sha256"],
        "minOSVersion": side["minOSVersion"],
    }
    app["privacy"] = side["privacy"]
    app["versions"].insert(0, entry)
    if dry:
        print("dry run; would release", tag, "->", url)
        with tempfile.TemporaryDirectory() as t:
            write_site(cat, os.path.join(t, "Website"))
            print("generated source.json OK:", len(cat["apps"]), "apps")
        return
    run(["gh", "release", "create", tag, os.path.join(DIST, side["file"]), "--repo", repo,
         "--title", f"{app['name']} {side['version']} ({side['buildVersion']})",
         "--notes", entry["localizedDescription"], "--latest=false"])
    save(cat)
    write_site(cat, SITE)


# ---------------------------------------------------------------- site

def source_json(cat):
    s = cat["source"]
    base = s["website"].rstrip("/")
    apps = []
    for a in cat["apps"]:
        if not a["versions"]:
            continue
        latest = a["versions"][0]
        d = {
            "name": a["name"], "bundleIdentifier": a["bundleIdentifier"],
            "developerName": s["developerName"], "subtitle": a["subtitle"],
            "localizedDescription": a["localizedDescription"],
            "iconURL": f"{base}/{a['icon']}", "tintColor": a["tintColor"],
            "versions": a["versions"],
            "appPermissions": {"entitlements": [], "privacy": a.get("privacy", {})},
            # Older clients read the newest version from the app itself.
            "version": latest["version"], "versionDate": latest["date"],
            "versionDescription": latest["localizedDescription"],
            "downloadURL": latest["downloadURL"], "size": latest["size"],
        }
        if a.get("screenshots"):
            d["screenshotURLs"] = [f"{base}/{p}" for p in a["screenshots"]]
        apps.append(d)
    return {
        "name": s["name"], "identifier": s["identifier"], "subtitle": s["subtitle"],
        "description": s["description"], "iconURL": f"{base}/{s['icon']}",
        "website": base, "tintColor": s["tintColor"],
        "featuredApps": [a["bundleIdentifier"] for a in apps],
        "apps": apps, "news": cat.get("news", []),
    }


def page(cat):
    s = cat["source"]
    url = f"{s['website'].rstrip('/')}/source.json"
    cards = []
    for a in cat["apps"]:
        if not a["versions"]:
            continue
        v = a["versions"][0]
        mb = v["size"] / 1_000_000
        link = f'<a href="{html.escape(a["site"])}">Project page</a>' if a.get("site") else ""
        cards.append(f"""      <article class="app" style="--tint: {a['tintColor']}">
        <img src="{html.escape(a['icon'])}" width="72" height="72" alt="">
        <div>
          <h3>{html.escape(a['name'])}</h3>
          <p class="sub">{html.escape(a['subtitle'])}</p>
          <p>{html.escape(a['localizedDescription'])}</p>
          <p class="meta">Version {html.escape(v['version'])} · {mb:.1f} MB · iOS {html.escape(v['minOSVersion'])} or later {('· ' + link) if link else ''}</p>
        </div>
      </article>""")
    t = open(os.path.join(ROOT, "scripts", "index.template.html")).read()
    return (t.replace("{{SOURCE_URL}}", url).replace("{{TITLE}}", html.escape(s["name"]))
             .replace("{{APPS}}", "\n".join(cards)))


def write_site(cat, site):
    os.makedirs(site, exist_ok=True)
    with open(os.path.join(site, "source.json"), "w") as f:
        json.dump(source_json(cat), f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(site, "index.html"), "w") as f:
        f.write(page(cat))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").add_argument("slug")
    r = sub.add_parser("release")
    r.add_argument("slug")
    r.add_argument("--notes")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("site")
    a = p.parse_args()
    if a.cmd == "build":
        build(a.slug)
    elif a.cmd == "release":
        release(a.slug, a.notes, a.dry_run)
    else:
        write_site(load(), SITE)


if __name__ == "__main__":
    main()
