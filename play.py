import html
import json
import re
import subprocess
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
venv = HERE / ".venv" / "bin" / "python"
CODE = (
    "import json,sys;from google_play_scraper import app\n"
    "d=app(sys.argv[1],lang='en',country='us')\n"
    "json.dump({'title':d.get('title'),'developer':(d.get('developer') or ''),'icon':d.get('icon'),"
    "'version':d.get('version')},sys.stdout)"
)


def details(pkg):
    if not venv.exists():
        return []
    try:
        p = subprocess.run([str(venv), "-c", CODE, pkg], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return []
        d = json.loads(p.stdout)
    except Exception:
        return []
    return [{
        "name": d.get("title") or pkg,
        "package": pkg,
        "developer": d.get("developer") or "",
        "icon": d.get("icon") or "",
        "source": "Google Play",
        "url": f"https://play.google.com/store/apps/details?id={pkg}",
        "note": "",
        "score": 100,
    }]

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0"}
S = requests.Session()
S.headers.update(UA)
SEARCH = "https://play.google.com/store/search?q={q}&c=apps&hl=en&gl=us"

# Package IDs from raw HTML / embedded JSON (CSS card classes are unstable)
_PKG = r'([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)'
PKG_FIND_RE = re.compile(
    r'(?:'
    r'/store/apps/details\?id='
    r'|/store/apps/details\\u003[Ff]id\\u003[Dd]'
    r'|\\u0026id\\u003[Dd]'
    r')' + _PKG
)
# Optional: leftover title class if markup still has it near a hit
TITLE_RE = re.compile(r'<div class="vWM94c">([^<]+)</div>')


def search(query, limit=20):
    r = S.get(SEARCH.format(q=requests.utils.quote(query)), timeout=60)
    r.raise_for_status()
    t = r.text
    out, seen = [], set()
    for m in PKG_FIND_RE.finditer(t):
        pkg = m.group(1)
        if pkg in seen:
            continue
        seen.add(pkg)
        seg = t[m.end():m.end() + 2500]
        tm = TITLE_RE.search(seg)
        title = html.unescape(tm.group(1)).strip() if tm else pkg
        sc = 70
        if pkg.casefold() == query.casefold():
            sc = 100
        elif title.casefold() == query.casefold():
            sc = 100
        elif title.casefold().startswith(query.casefold()):
            sc = 95
        elif query.casefold() in title.casefold():
            sc = 85
        out.append({
            "name": title,
            "package": pkg,
            "developer": "",
            "icon": "",
            "source": "Google Play",
            "url": f"https://play.google.com/store/apps/details?id={pkg}",
            "note": "",
            "score": sc,
        })
        if len(out) >= limit:
            break
    return out