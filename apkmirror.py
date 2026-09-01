import html
import os
import re
import threading
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0"}
S = requests.Session()
S.headers.update(UA)
SEARCH = "https://www.apkmirror.com/?action=apk_search&s={q}"
PKG_RE = re.compile(r"/store/apps/details\?id=([a-zA-Z0-9_.]+)")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
APPROW_RE = re.compile(r'<div class="appRow">(.*?)(?=<div class="appRow">|\Z)', re.S)
APP_LINK_RE = re.compile(r'href="(/apk/[^"]+?/)"')
NAME_RE = re.compile(r'<h5[^>]*class="[^"]*app[^"]*"[^>]*>(.*?)</h5>', re.S)

_LOCK = threading.Lock()
_LAST_TS = 0.0
try:
    _MIN_INTERVAL = float(os.environ.get("APKMIRROR_DELAY_SEC", "1.8"))
except ValueError:
    _MIN_INTERVAL = 1.8


def _get(url):
    """Throttled GET: ≥APKMIRROR_DELAY_SEC (default 1.8) between Mirror requests; one 20s retry on 403."""
    global _LAST_TS
    with _LOCK:
        wait = _MIN_INTERVAL - (time.time() - _LAST_TS)
        if wait > 0:
            time.sleep(wait)
        r = S.get(url, timeout=60)
        _LAST_TS = time.time()
        if r.status_code == 403:
            time.sleep(20)
            r = S.get(url, timeout=60)
            _LAST_TS = time.time()
        r.raise_for_status()
        return r


def _page(url):
    return _get(url).text


def _clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def search(query, limit=3):
    return _search_landings(query, limit)


def by_package(pkg):
    return _search_landings(pkg, limit=10, want_pkg=pkg)



def _search_landings(query, limit=10, want_pkg=None):
    qtoks = [t for t in re.split(r"\W+", query.casefold()) if t]
    t = _page(SEARCH.format(q=requests.utils.quote(query)))
    apps = {}
    for blk in APPROW_RE.findall(t):
        nm = NAME_RE.search(blk)
        ln = APP_LINK_RE.search(blk)
        if not ln:
            continue
        name = _clean(nm.group(1)) if nm else ""
        if want_pkg is None and qtoks and not any(t in name.casefold() for t in qtoks):
            continue
        base = ln.group(1)
        if "-release" in base:
            base = base.rsplit("/", 2)[0]
        if not base.endswith("/"):
            base += "/"
        apps.setdefault(base, name)
    out = []
    for base, name in apps.items():
        try:
            app = _page("https://www.apkmirror.com" + base)
        except requests.RequestException:
            continue
        mp = PKG_RE.search(app)
        if not mp:
            mi = re.search(r"og:image[^>]*/_([a-zA-Z0-9_.]+)\.png", app)
            mp = mi
        if not mp:
            continue
        pkg = mp.group(1)
        if not re.match(r"^[a-zA-Z0-9_.]+$", pkg):
            continue
        if want_pkg and pkg != want_pkg:
            continue
        mt = TITLE_RE.search(app)
        full = _clean(mt.group(1)) if mt else name
        for suf in (" APKs for Android", " APK for Android", " - APKMirror"):
            full = full.replace(suf, "")
        label = re.sub(r"^Download ", "", full).strip() or name
        out.append({
            "name": label,
            "package": pkg,
            "developer": "",
            "icon": "",
            "source": "APKMirror",
            "url": "https://www.apkmirror.com" + base,
            "note": "",
            "score": 100 if want_pkg else 55,
        })
        if len(out) >= limit:
            break
    return out
