import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import apkmirror
import fdroid
import play

SOURCE_PRIO = {"Google Play": 0, "F-Droid": 1, "IzzyOnDroid": 1, "APKMirror": 2}


def merge_by_package(hits):
    merged = {}
    for h in hits:
        pkg = h["package"]
        m = merged.get(pkg)
        if m is None:
            merged[pkg] = {
                "package": pkg,
                "names": [],
                "sources": [],
                "developer": "",
                "icon": "",
                "url": "",
                "urls": [],
                "notes": [],
                "max_score": 0,
            }
            m = merged[pkg]
        m["names"].append((SOURCE_PRIO.get(h["source"], 9), h["name"]))
        for s in h["source"].split("+"):
            if s not in m["sources"]:
                m["sources"].append(s)
        if h.get("url") and h["url"] not in m["urls"]:
            m["urls"].append(h["url"])
        if not m["developer"] and h.get("developer"):
            m["developer"] = h["developer"]
        if not m["icon"] and h.get("icon"):
            m["icon"] = h["icon"]
        if not m["url"] and h.get("url"):
            m["url"] = h["url"]
        if h.get("note") and h["note"] not in m["notes"]:
            m["notes"].append(h["note"])
        m["max_score"] = max(m["max_score"], h.get("score", 0))
    cands = []
    for m in merged.values():
        m["sources"].sort(key=lambda s: SOURCE_PRIO.get(s, 9))
        names = sorted(m["names"], key=lambda t: t[0])
        seen = set()
        names = [(p, n) for p, n in names if not (n in seen or seen.add(n))]
        m["primary"] = names[0][1]
        m["names"] = [n for _, n in names]
        cands.append(m)
    cands.sort(key=lambda c: (-c["max_score"], c["package"]))
    return cands


def resolve(query, sources=("fdroid", "play", "apkmirror")):
    jobs = {
        "fdroid": lambda: fdroid.search(query),
        "play": lambda: play.search(query),
        "apkmirror": lambda: apkmirror.search(query),
    }
    hits = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {name: ex.submit(job) for name, job in jobs.items() if name in sources}
        for fut in futs.values():
            try:
                hits.extend(fut.result())
            except Exception as e:
                hits.append({"error": str(e)})
    errors = [h for h in hits if "error" in h]
    hits = [h for h in hits if "error" not in h]
    return merge_by_package(hits), errors


def exact_by_package(pkg, sources=("fdroid", "play", "apkmirror")):
    hits = []
    errors = []
    if "fdroid" in sources:
        try:
            hits.extend(fdroid.lookup(pkg))
        except Exception as e:
            errors.append(str(e))
    if "play" in sources:
        try:
            hits.extend(play.details(pkg))
        except Exception as e:
            errors.append(str(e))
    if "apkmirror" in sources:
        try:
            hits.extend(apkmirror.by_package(pkg))
        except Exception as e:
            errors.append(str(e))
    return merge_by_package(hits), errors


def render(cands, query, errors=None):
    lines = [f"? {query}"]
    for i, c in enumerate(cands, 1):
        badges = "[" + "][".join(c["sources"]) + "]"
        extra = []
        if c["developer"]:
            extra.append(c["developer"])
        extra += c["notes"]
        lines.append(f"{i}. {c['primary'].ljust(30)} {c['package'].ljust(32)} {badges}")
        if c["url"]:
            lines.append(f"   {c['url']}")
        if extra:
            lines.append("   " + " · ".join(extra))
    if errors:
        for e in errors:
            lines.append(f"[ERROR] {e}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Name -> Package Resolver (F-Droid/Play/APKMirror)")
    ap.add_argument("query", nargs="+", help="app name, e.g. signal")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fdroid", action="store_true")
    ap.add_argument("--no-play", action="store_true")
    ap.add_argument("--no-apkmirror", action="store_true")
    ap.add_argument("--sync", action="store_true", help="force re-download F-Droid indexes")
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    if a.sync:
        fdroid.sync(force=True)
    q = " ".join(a.query)
    sources = tuple(
        s for s in ("fdroid", "play", "apkmirror")
        if not (s == "fdroid" and a.no_fdroid)
        and not (s == "play" and a.no_play)
        and not (s == "apkmirror" and a.no_apkmirror)
    )
    cands, errors = resolve(q, sources)
    cands = cands[: a.limit]
    if a.json:
        payload = {
            "query": q,
            "errors": errors,
            "candidates": [
                {"rank": i + 1, **c} for i, c in enumerate(cands)
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render(cands, q, errors))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)