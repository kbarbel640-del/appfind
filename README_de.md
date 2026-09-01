# appfind

*(English: [README.md](README.md))*

Zu einem **Android-App-Namen** das **Package** auflösen und danach **verfügbare Versionen** über mehrere Stores sammeln — ohne still den ersten Treffer zu nehmen.

Ein einzelner Store kennt nicht alle Namen. Der **Name** ist mehrdeutig, das **Package** ist eindeutig. Deshalb: mehrere Quellen, Kandidatenliste, Merge nach Package, Auswahl durch dich.

```text
Name ──► Resolver (F-Droid + Play + APKMirror) ──► Kandidatenliste
                                                      │
Package gewählt ──► Versionssammler
                   (F-Droid/Izzy + APKMirror + Aptoide-Archiv + Play-aktuell)
```

## Wozu das?

- **FOSS**: F-Droid / IzzyOnDroid liefern echte Versionshistorie (vercode, Hashes, URLs).
- **Breite Abdeckung**: Play ist stark beim *Finden* von Packages; APKMirror bestätigt aktuelle Builds.
- **Tiefes Archiv**: Aptoide reicht oft Jahre weiter zurück als APKMirror oder APKPure (z. B. WhatsApp bis **2.17.253 / 2017**), inkl. MD5 + Pool-Download-Pfad je Version.

Dieses Repo ist Phase 1–2: **Name → Package → Versionskarte**. Eingebaute Downloads (`--get`) sind **nicht geplant** — Versionslinks und Hashes reichen; APKs holst du woanders.

## Install

```bash
git clone https://github.com/kbarbel640-del/appfind.git
cd appfind
bash install.sh
source .venv/bin/activate
```

`install.sh` legt `.venv` an und installiert `requirements.txt`. Der erste F-Droid-Index-Sync läuft beim ersten `resolver.py`-Aufruf, nicht im Installer. Schon im Clone? Einfach `bash install.sh` (Git-URL als `$1` nur, wenn das Skript für dich klonen soll).

## Aufbau

| Datei | Zweck |
|-------|-------|
| `resolver.py` | CLI: Suche, Merge nach Package, Ranking, JSON |
| `appfind.py` | Versionssammler (`--versions`), `--pick` zur Kandidatenwahl |
| `fdroid.py` | F-Droid + IzzyOnDroid-Index, lokaler Cache, Suche + Historie |
| `play.py` | Google-Play-Suche (eigener HTML-Parser) + Package-Details |
| `apkmirror.py` | APKMirror-HTML-Suche + aktuelle Versionen (403-tolerant) |
| `aptoide.py` | Aptoide-Archiv-Adapter: alte Stände, Download-Pfad + MD5 |

## Schnellstart

```bash
# Name → Package-Kandidaten (Quellen als Badges, nach Package gemerged)
python3 resolver.py "signal"
python3 resolver.py --json "firefox"
python3 resolver.py --no-play "vita"     # Quelle ausschließen
python3 resolver.py --sync "signal"      # F-Droid-Indizes neu laden

# Package (oder Name) → Versionslisten
python3 appfind.py org.mozilla.firefox --versions
python3 appfind.py "antennapod" --versions
python3 appfind.py "firefox" --versions --pick 3   # Kandidat wählen (Default: 1)
python3 appfind.py org.mozilla.firefox --versions --json
```

`--pick` defaultet auf `1`. Mit `--pick 0` gibt es eine interaktive Abfrage (JSON-Workflows bleiben typischerweise beim Default).

## Quellen auf einen Blick

| Quelle | Namen | Versionshistorie | Hinweis |
|--------|-------|------------------|---------|
| F-Droid / Izzy | stark bei FOSS | **vercode + sha256 + url** | Izzy: `apt.izzysoft.de/fdroid/repo`; v2-Index kurz gehalten |
| Google Play | beste Abdeckung | nur aktuell | Referenzzeile; keine öffentliche Historie |
| APKMirror | gute Bestätigung | letzte ~10 | kein VersionCode im HTML; Rate-Limits / 403 |
| Aptoide | kein Namensresolver | **bestes Tiefenarchiv**, Download + MD5 | `getMeta?app_id=` auf Disk gecacht; relative Pfade als `path:` vs. `https://` |

F-Droid und APKMirror ergänzen sich: F-Droid für echte FOSS-Historie, APKMirror für aktuelle proprietäre Builds.

## Adapter-Notizen

### Play (`play.py`)
`google-play-scraper`’s `search()` liefert gegen aktuelles Markup oft `appId: None`. Deshalb:

- **Suche** zieht Package-IDs aus dem Roh-HTML (`details?id=` / escaped); Title fällt auf den Package-Namen zurück, wenn nichts Stabiles da ist.
- **Details** weiter über die funktionierende `app(pkg)`-API des Scrapers (venv-Subprocess, falls vorhanden).

### F-Droid (`fdroid.py`)
- Lädt `index-v2.json` (f-droid.org + Izzy), hält danach ein kompaktes `fdroid_index.json` für Offline-Suche.
- Die volle Althistorie aus klassischem `index-v1` steckt **nicht** in v2; `versions()` gibt nur, was der v2-Index noch führt.
- Izzy-Pakete bekommen Izzy-URLs (keine toten `f-droid.org/packages/…`-Links).

### APKMirror (`apkmirror.py`)
- Package kommt vom „View on Play Store“-Link, nicht aus dem Titel.
- Token-Namensfilter nur bei **Namenssuche** (sonst Homepage-Müll). `by_package()` matcht exakt.
- HTTP wird im Prozess gedrosselt (≥1.8s); 403 einmal Retry, danach kann `exact_by_package()` auf Play/F-Droid fallen.
- App-Seiten zeigen grob die neuesten ~10 Releases — keine zentrale Pagination für Altes.

### Aptoide (`aptoide.py`) — der Archiv-Treffer
- `getMeta?package_name=` → `uname`; `/versions` (`__NEXT_DATA__`) listet Versionen **inkl.** aktuellem Stand.
- `getMeta?app_id=` → MD5 + Pool-Pfad **pro Version**. Antworten liegen in `cache/aptoide_meta.json` (TTL 24h, atomar geschrieben), damit große Kataloge keine Rate-Limits sprengen.
- Relative `file.path`-Werte erscheinen als `path:…`; absolute URLs bleiben `https://…`.
- Beispiel: WhatsApp → ~20 Versionen mit URL + MD5, zurück bis 2.17.253 (2017).

## Roadmap (bewusst später)

- APKMirror-Althistorie über einzelne Release-/Varianten-Seiten
- Play „aktuell“ als eigene Abgleichszeile
- **Nicht geplant:** eingebauter APK-Download / `--get` — Links (+ Hashes, wo vorhanden) reichen
- **Nicht geplant als fünfte Namensquelle:** Uptodown — die JSON-Storeliste bleibt Landkarte, kein Crawler-Futter

## License

Unlicense. Mach damit, was du willst. Keine Garantie.
Adapter brechen, wenn Store-Markup oder inoffizielle APIs sich ändern.

---
**🤖 Grok-approved.** *(Danke, [xAI](https://x.ai)!)*
