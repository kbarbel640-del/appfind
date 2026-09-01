import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import apkmirror
import fdroid
import resolver
import aptoide

CACHE = Path(__file__).resolve().parent / "cache" / "apkmirror"
API_TTL = 6 * 3600
HERE = Path(__file__).resolve().parent


def _html(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "_", url.lower()).strip("_") + ".html"
    raw = CACHE / key
    if raw.exists() and time.time() - raw.stat().st_mtime < API_TTL:
        return raw.read_text()
    r = apkmirror._get(url)
    raw.write_text(r.text)
    return r.text


def slug_version(link):
    seg = re.sub(r"-release/?$", "", link.rstrip("/").rsplit("/", 1)[-1])
    toks = seg.split("-")
    i = len(toks)
    while i > 0 and toks[i - 1].isdigit():
        i -= 1
    nums = toks[i:]
    if not nums:
        return seg, (0,)
    return ".".join(nums), tuple(int(x) for x in nums)


def apkmirror_versions(base_path):
    url = "https://www.apkmirror.com" + base_path.rstrip("/") + "/"
    base = base_path.rstrip("/")
    html = _html(url)
    seen, rows = set(), {}
    for m in re.finditer(r'href="(/apk/[^"#?]+?/)"', html):
        link = m.group(1).rstrip("/")
        if not link.endswith("-release"):
            continue
        if not link.startswith(base + "/"):
            continue
        if link in seen:
            continue
        seen.add(link)
        ver, keys = slug_version(link)
        if not rows.get(ver):
            rows[ver] = {
                "version": ver,
                "date": "",
                "size": 0,
                "url": "https://www.apkmirror.com" + link + "/",
                "source": "APKMirror",
                "_keys": keys,
            }
    out = sorted(rows.values(), key=lambda r: r["_keys"], reverse=True)
    for r in out:
        r.pop("_keys", None)
    return out


def play_current(pkg):
    code = (
        "import json,sys;from google_play_scraper import app\n"
        "d=app(sys.argv[1],lang='en',country='us')\n"
        "json.dump({'title':d.get('title'),'version':d.get('version'),"
        "'updated':d.get('updated'),'icon':d.get('icon')},sys.stdout)"
    )
    venv = HERE / ".venv" / "bin" / "python"
    if not venv.exists():
        return None
    try:
        p = subprocess.run(
            [str(venv), "-c", code, pkg], capture_output=True, text=True, timeout=60
        )
        if p.returncode != 0:
            return None
        d = json.loads(p.stdout)
        d["package"] = pkg
        d["url"] = f"https://play.google.com/store/apps/details?id={pkg}"
        return d
    except Exception:
        return None


def is_package(s):
    return bool(re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.]*\.[a-zA-Z0-9_.]+$", s))


def gather(pkg):
    cands, _ = resolver.exact_by_package(pkg)
    c = next((x for x in cands if x["package"] == pkg), cands[0] if cands else None)
    urls = (c.get("urls") or []) if c else []
    fdv = fdroid.versions(pkg)
    am = []
    am_url = next((u for u in urls if "apkmirror.com" in u), None)
    if am_url:
        base = re.sub(r"^https?://www\.apkmirror\.com", "", am_url).rstrip("/") + "/"
        am = apkmirror_versions(base)
    pc = play_current(pkg)
    ap_versions = []
    try:
        ap_versions = aptoide.versions(pkg, resolve_dl=True)
    except Exception:
        pass
    return {
        "package": pkg,
        "name": c.get("primary") if c else pkg,
        "badges": [s for s in (c.get("sources") or [])] if c else [],
        "fdroid": fdv,
        "apkmirror": am,
        "aptoide": ap_versions,
        "play": pc,
    }


def render(g):
    out = [f"? {g['package']}  {g['name']}  ({'/'.join(g['badges'])})"]
    if g["play"]:
        out.append(f"Play [aktuell]: {g['play']['version'] or '?'} · "
                   f"{datetime.fromtimestamp(g['play']['updated'], tz=timezone.utc).strftime('%Y-%m-%d') if g['play']['updated'] else '?'} · "
                   f"{g['play']['url']}")
    else:
        out.append("Play: n/a")
    for name_field, rows in (("F-Droid/Izzy", g["fdroid"]), ("APKMirror", g["apkmirror"]), ("Aptoide", g["aptoide"])):
        if not rows:
            out.append(f"{name_field}: -")
            continue
        out.append(f"\n{name_field} ({len(rows)} Versionen):")
        for r in rows:
            size = f"{r['size']/1e6:.1f} MB" if r.get("size") else ""
            out.append(f"  {r['version'].ljust(16)} vc={str(r['vercode']).ljust(10) if r.get('vercode') else '-'.ljust(10)}"
                       f" {r.get('date','').ljust(10)} {size.ljust(9)} [{r['source']}] {r.get('url','')}")
    return "\n".join(out)


def _interactive_pick(candidates):
    while True:
        try:
            s = input(f"Kandidat waehlen (1-{len(candidates)}): ").strip()
            if not s:
                return candidates[0]["package"]
            i = int(s)
            if 1 <= i <= len(candidates):
                return candidates[i - 1]["package"]
        except (ValueError, EOFError):
            return candidates[0]["package"]
        print("ungueltig")


def main():
    ap = argparse.ArgumentParser(description="Finde und liste App-Versionen (F-Droid/Izzy, APKMirror, Play)")
    ap.add_argument("query", help="Package-Name (z.B. org.mozilla.firefox) oder App-Name")
    ap.add_argument("--versions", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-play", action="store_true")
    ap.add_argument("--pick", type=int, default=1, help="Kandidat waehlen (1=Rank 1, interaktiv wenn 0 lenken)")
    ap.add_argument("--limit", type=int, default=200)
    a = ap.parse_args()

    pkg, candidates = a.query, None
    if not is_package(a.query):
        candidates, _ = resolver.resolve(a.query)
        if not candidates:
            print("keine Treffer")
            sys.exit(1)
        pkg = candidates[0]["package"]
        if candidates:
            print("Kandidaten:")
            print(resolver.render(candidates, a.query) + "\n")
            if a.pick == 0:
                pkg = _interactive_pick(candidates)
            else:
                pick = max(0, min(a.pick, len(candidates)) - 1)
                pkg = candidates[pick]["package"]
    g = gather(pkg)
    if a.limit:
        g["fdroid"] = g["fdroid"][: a.limit]
        g["apkmirror"] = g["apkmirror"][: a.limit]
        g["aptoide"] = g["aptoide"][: a.limit]
    if a.no_play:
        g["play"] = None
    if a.json:
        print(json.dumps(g, ensure_ascii=False, indent=2))
    else:
        print(render(g))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)