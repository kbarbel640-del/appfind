"""Aptoide-Versionsadapter.

Kern (bereits aus aptoide_get.py verifiziert):
  getMeta?package_name=<pkg>            -> uname, aktuelle Version (md5/path)
  GET https://<uname>.en.aptoide.com/versions
      -> __NEXT_DATA__.props.pageProps.versions (inkl. aktuelle)
  getMeta?app_id=<vers-id>              -> md5sum + Pool-Download-Path fuer GENAU diese Version
                                           (Antworten nach app_id gecacht, Datei + RAM)
"""
import json
import re
import time
from pathlib import Path

import requests

API = "https://ws75.aptoide.com/api/7/app/getMeta"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0"}
S = requests.Session()
S.headers.update(UA)

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_FILE = CACHE_DIR / "aptoide_meta.json"
META_TTL = 24 * 3600

# getMeta?app_id= – RAM + cache/aptoide_meta.json (Key = str(app_id))
_META_BY_APP_ID = {}
_META_TS = {}


def _file_url(path):
    """Voll-URL lassen; relative Pool-Pfade als path: markieren (kein fertiger Download-Link)."""
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return f"path:{path}"


def _load_meta_cache():
    if not CACHE_FILE.exists():
        return
    try:
        raw = json.loads(CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return
    now = time.time()
    if not isinstance(raw, dict):
        return
    for k, entry in raw.items():
        if not isinstance(entry, dict) or "data" not in entry:
            continue
        ts = entry.get("ts", 0)
        if now - ts > META_TTL:
            continue
        _META_BY_APP_ID[str(k)] = entry["data"]
        _META_TS[str(k)] = ts


def _save_meta_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        k: {"ts": _META_TS[k], "data": _META_BY_APP_ID[k]}
        for k in _META_BY_APP_ID
        if k in _META_TS
    }
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False))
    tmp.replace(CACHE_FILE)


def _cache_get(app_id):
    k = str(app_id)
    if k not in _META_BY_APP_ID:
        return None
    if time.time() - _META_TS.get(k, 0) > META_TTL:
        _META_BY_APP_ID.pop(k, None)
        _META_TS.pop(k, None)
        return None
    return _META_BY_APP_ID[k]


def _cache_put(app_id, data, persist=False):
    k = str(app_id)
    _META_BY_APP_ID[k] = data
    _META_TS[k] = time.time()
    if persist:
        _save_meta_cache()


_load_meta_cache()


def get_meta(**params):
    app_id = params.get("app_id")
    if app_id is not None:
        hit = _cache_get(app_id)
        if hit is not None:
            return hit
    r = S.get(API, params=params, timeout=30)
    r.raise_for_status()
    d = r.json()
    if d.get("info", {}).get("status") != "OK":
        raise RuntimeError(f"getMeta {list(params)} -> {d.get('info', {}).get('status')}")
    data = d["data"]
    rid = data.get("id")
    if app_id is not None:
        _cache_put(app_id, data, persist=False)
        if rid is not None and str(rid) != str(app_id):
            _cache_put(rid, data, persist=False)
        _save_meta_cache()
    elif rid is not None:
        _cache_put(rid, data, persist=False)
    return data


def lookup(pkg):
    data = get_meta(package_name=pkg)
    f = data["file"]
    uname = data.get("uname", "")
    return {
        "package": pkg,
        "name": data.get("name", ""),
        "uname": uname,
        "current_version": f.get("vername"),
        "current_vercode": f.get("vercode"),
        "url": f"https://{uname}.en.aptoide.com/" if uname else "",
    }


def versions(pkg, resolve_dl=True):
    """Liste aller Aptoide-Versionen (inkl. aktueller). Download-URL je Version via getMeta?app_id."""
    data = get_meta(package_name=pkg)
    uname = data["uname"]
    cur_file = data["file"]
    cur_vc = cur_file.get("vercode")
    url = f"https://{uname}.en.aptoide.com/versions"
    html = S.get(url, timeout=30).text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError(f"kein __NEXT_DATA__ unter {url}")
    pp = json.loads(m.group(1))["props"]["pageProps"]
    rows = []
    for v in pp.get("versions", []):
        row = {
            "version": v.get("vername", ""),
            "vercode": v.get("vercode"),
            "date": (v.get("date") or "")[:10],
            "size": v.get("size", 0),
            "Aptoide_id": v.get("id"),
            "url": "",
            "md5": "",
            "source": "Aptoide",
        }
        if resolve_dl and row["Aptoide_id"]:
            try:
                # aktuelle Version: Meta aus package_name-Call wiederverwenden
                if row["vercode"] == cur_vc:
                    row["md5"] = cur_file.get("md5sum", "")
                    row["url"] = _file_url(cur_file.get("path", ""))
                else:
                    meta = get_meta(app_id=row["Aptoide_id"])
                    row["md5"] = meta["file"].get("md5sum", "")
                    row["url"] = _file_url(meta["file"].get("path", ""))
            except RuntimeError:
                pass
        rows.append(row)
    rows.sort(key=lambda r: r["vercode"] or -1, reverse=True)
    return rows
