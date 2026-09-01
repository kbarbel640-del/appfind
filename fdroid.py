import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent / "cache"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0"}
S = requests.Session()
S.headers.update(UA)

REPOS = {
    "F-Droid": "https://f-droid.org/repo/index-v2.json",
    "IzzyOnDroid": "https://apt.izzysoft.de/fdroid/repo/index-v2.json",
}
TTL = 7 * 24 * 3600


def _pick(d, preferred=("en-US", "en", "de", "en-GB")):
    if not isinstance(d, dict):
        return str(d or "")
    for p in preferred:
        if p in d:
            return d[p]
    if d:
        return next(iter(d.values()))
    return ""


def _fetch(raw_path: Path, url: str) -> dict:
    if raw_path.exists() and time.time() - raw_path.stat().st_mtime < TTL:
        return json.loads(raw_path.read_text())
    r = S.get(url, timeout=180)
    r.raise_for_status()
    raw_path.write_text(r.text)
    return r.json()


def sync(force=False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    compact = {}
    timestamps = {}
    for repo, url in REPOS.items():
        raw = CACHE_DIR / ("index-" + {"F-Droid": "fdroid", "IzzyOnDroid": "izzy"}[repo] + ".json")
        if force or not (CACHE_DIR / ("meta-" + repo + ".json")).exists():
            d = _fetch(raw, url)
            ts = d.get("repo", {}).get("timestamp", "")
            for pkg, entry in d.get("packages", {}).items():
                m = entry.get("metadata", {})
                names = {_pick(m.get("name", {})).casefold()}
                names |= {v.casefold() for v in m.get("name", {}).values() if isinstance(v, str)}
                summaries = {v.casefold() for v in m.get("summary", {}).values() if isinstance(v, str)} if isinstance(m.get("summary"), dict) else {str(m.get("summary", "")).casefold()}
                compact[pkg] = {
                    "name": _pick(m.get("name", {})),
                    "names": sorted(names),
                    "summaries": sorted(summaries),
                    "summary": _pick(m.get("summary", {})),
                    "categories": m.get("categories") or [],
                    "license": m.get("license") or "",
                    "antifeatures": sorted((m.get("antiFeatures") or {}).keys()),
                    "repos": [repo],
                }
            timestamps[repo] = ts
            (CACHE_DIR / ("meta-" + repo + ".json")).write_text(json.dumps({"ts": ts, "url": url}))
    merged = {}
    for pkg, rec in compact.items():
        if pkg not in merged:
            merged[pkg] = dict(rec)
        else:
            merged[pkg]["repos"] = sorted(set(merged[pkg]["repos"]) | set(rec["repos"]))
    out = CACHE_DIR / "fdroid_index.json"
    out.write_text(json.dumps(merged, ensure_ascii=False))
    return merged


def load():
    out = CACHE_DIR / "fdroid_index.json"
    if not out.exists():
        return sync()
    return json.loads(out.read_text())


def _score(rec, q, qtoks):
    names = [n for n in rec["names"] if n]
    if q in names:
        return 100
    if any(q in n for n in names):
        return 90
    if any(qt == n for n in names for qt in qtoks):
        return 80
    if any(qt in n for n in names for qt in qtoks):
        return 65
    if any(q in s for s in rec["summaries"]):
        return 40
    if any(qt in s for s in rec["summaries"] for qt in qtoks):
        return 25
    return 0


def search(query, limit=20):
    idx = load()
    q = query.casefold().strip()
    qtoks = [t for t in re.split(r"\W+", q) if t]
    hits = []
    for pkg, rec in idx.items():
        sc = _score(rec, q, qtoks)
        if sc > 0:
            hits.append((sc, pkg, rec))
    hits.sort(key=lambda x: -x[0])
    out = []
    for sc, pkg, rec in hits[:limit]:
        out.append({
            "name": rec["name"],
            "package": pkg,
            "developer": "",
            "icon": "",
            "source": "+".join(rec["repos"]),
            "url": _url_for(pkg, rec),
            "note": _note_for(rec),
            "score": sc,
        })
    return out


def _url_for(pkg, rec):
    if rec.get("repos") == ["IzzyOnDroid"]:
        return f"https://apt.izzysoft.de/fdroid/index/apk/{pkg}"
    return f"https://f-droid.org/packages/{pkg}/"


def _note_for(rec):
    note = "FOSS"
    if rec.get("license"):
        note += f" · {rec['license']}"
    if rec.get("antifeatures"):
        note += " · " + ",".join(rec["antifeatures"])
    return note


def lookup(pkg):
    rec = load().get(pkg)
    if not rec:
        return []
    return [{
        "name": rec["name"],
        "package": pkg,
        "developer": "",
        "icon": "",
        "source": "+".join(rec["repos"]),
        "url": _url_for(pkg, rec),
        "note": _note_for(rec),
        "score": 100,
    }]


def versions(pkg):
    rows = []
    for repo, fn in (("F-Droid", "index-fdroid.json"), ("IzzyOnDroid", "index-izzy.json")):
        raw = CACHE_DIR / fn
        if not raw.exists():
            continue
        d = json.loads(raw.read_text())
        entry = d.get("packages", {}).get(pkg)
        if not entry:
            continue
        for ent in entry.get("versions", {}).values():
            man = ent.get("manifest", {})
            fobj = ent.get("file", {}) or {}
            fname = fobj.get("name", "")
            if repo == "IzzyOnDroid":
                base = "https://apt.izzysoft.de/fdroid/repo"
            else:
                base = "https://f-droid.org/repo"
            rows.append({
                "version": man.get("versionName", ""),
                "vercode": man.get("versionCode"),
                "date": datetime.fromtimestamp(ent.get("added", 0) / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                "size": fobj.get("size", 0),
                "url": base + fname,
                "sha256": fobj.get("sha256", "") or "",
                "source": repo,
            })
    rows.sort(key=lambda r: (r["vercode"] or -1), reverse=True)
    return rows