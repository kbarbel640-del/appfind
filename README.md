# App-Version-Sammler / Name→Package-Resolver

Entwicklungsverlauf des Werkzeugs, das zu einem **App-Namen** das **Paket** auflöst und daraus **alle verfugbaren Versionen** sammelt – über eine Resolver-Kette mehrerer Quellen.

## Ziel

Ein einzelner Store kennt nicht alle Namen. Der **Name** ist mehrdeutig, das **Package** ist eindeutig. Deshalb: mehrere Quellen, Kandidatenliste, Merge nach Package – nie still den ersten Treffer nehmen.

```text
Name ──► Resolver (F-Droid + Play + APKMirror) ──► Kandidatenliste
                                                       │
Package gewaehlt ──► Versionssammler (F-Droid/Izzy + APKMirror + Play-Referenz)
```

## Aufbau

| Datei | Zweck |
|-------|-------|
| `resolver.py` | CLI + Merge nach Package, Ranking, JSON-Ausgabe |
| `fdroid.py`   | F-Droid-Index (f-droid.org + IzzyOnDroid), lokaler Cache, Suche + Versionshistorie |
| `play.py`     | Google-Play-Suche (eigener HTML-Parser) + Package-Details (Scraper in venv) |
| `apkmirror.py`| APKMirror-HTML-Suche + Versionsliste (Namensfilter, 403-tolerant) |
| `aptoide.py`  | Aptoide-Adapter: Versionshistorie bis in sehr alte Stände, Download-URL + MD5 je Version |
| `appfind.py`  | Versionssammler (`--versions`), `--pick` zur Kandidatenwahl |

## Dateien haben sich im Verlauf entwickelt – Punktuelle Einblicke

### `play.py` – warum kein fertiger Scraper?
`google-play-scraper` ist im venv installiert, aber dessen `search()` liefert seit kurzem `appId: None` (Parser laeuft gegen das aktuelle Play-Markup ins Leere). Deshalb:
- **Suche**: eigener HTML-Parser auf `https://play.google.com/store/search?q=…&c=apps` – parst `details?id=`-Links, dazu Title/Developer/Icon.
- **Details** (Packagelookup): nutzt doch den Scraper, aber dessen `app(pkg)`-Funktion (die funktioniert), via `subprocess` gegen `/usr/lib/.../.venv`.

### `fdroid.py` – Indexv-2 & lokaler Cache
- `index-v2.json` (58 MB f-droid.org + 14 MB Izzy) wird einmalig geladen und als kompaktes `fdroid_index.json` (~4 MB) gecacht – offline nach erstem Sync.
- Merkfeld: Die vollstaendige Althistorie (`index-v1`) steht offiziell nicht im v2-Index; `versions()` liest pro Package die vorhandenen Eintraege (F-Droid fuehrt nur wenige recente).
- Pakete aus Izzy bekommen die Izzy-URL, nicht `f-droid.org/packages/…` (tote URL vermieden).

### `apkmirror.py` – ADAPTER-GRENZE
- Suche: `?action=apk_search` → `<div class="appRow">`-Bloecke → Landingpage. Package stammt vom „View on Play Store"-Link (`details?id=`), nicht aus dem Titel.
- **Namensfilter** nur bei der Namenssuche: matcht Tokens im sichtbaren Namen, sonst schleppt er die APKMirror-Startseite (YouTube, CapCut, Google Play Store) hinterher. `by_package()` schaltet den Filter aus und matcht exakt.
- **403/Bot-Block**: APKMirror drosselt (z.B. `s=com.whatsapp` → 403 nach mehreren Anfragen). `resolver.exact_by_package()` faengt das und faellt still auf Play/F-Droid zurueck.
- **Versionsübersicht zeigt nur die ~10 neuesten** – APKMirror hat auf der App-Seite keine zentrale Pagination fuer alte Versionen.

### `aptoide.py` – der eigentliche Archiv-Treffer
- `getMeta?package_name=<pkg>` loest `uname` auf; die `/versions`-Seite (`__NEXT_DATA__`) listet die Versionen **inkl. aktueller** (`vercode == cur_vc` bleibt in der Liste).
- **`getMeta?app_id=<id>` liefert fuer JEDE Version md5 + Pool-Download-Path** – Antworten werden nach `app_id` gecacht (sonst N Extra-Requests / Rate-Limits). Relative `file.path`-Werte werden als `path:…` markiert, volle URLs bleiben `https://…`.
- adapter in `appfind.py`: WhatsApp → 20 Versionen mit Download-URL + MD5 (bis 2.17.253 / 2017).

## CLI

```bash
# Resolver: Name -> Kandidaten (Quellen als Badges, nach Package gemerged)
python3 resolver.py "signal"
python3 resolver.py --json "firefox"
python3 resolver.py --no-play "vita"        # Quelle ausschliessen
python3 resolver.py --sync "signal"         # F-Droid-Indizes neu laden

# Versionssammler
python3 appfind.py org.mozilla.firefox --versions
python3 appfind.py "antennapod" --versions  # Name -> automatisch Paket
python3 appfind.py "firefox" --versions --pick 3   # Kandidat waehlen (statt stillem First-Hit)
python3 appfind.py <pkg> --versions --json
```

## Bekannte Quellen-Eigenschaften

| Quelle | Namen | Versionshistorie | Hinweis |
|--------|-------|------------------|---------|
| F-Droid / Izzy | gut | **voll, vercode+sha256+url** (Izzy: `apt.izzysoft.de/fdroid/repo`) | nur FOSS; v2-Index kurz gehalten |
| Google Play | beste Abdeckung | nur aktuelle Version | Detailzeile als Referenz; keine Historie |
| APKMirror | gut als Bestaetigung | nur letzte ~10, 403-drosselbar | VersionCode fehlt im HTML |
| Aptoide | – (kein Namensresolver) | **beste Althistorie**, Download+MD5 je Version | `getMeta?app_id=` (gecacht); `path:` vs. `https://`; bis 2017+ zurueck |

F-Droid und APKMirror ergaenzen sich: F-Droid liefert die echte vercode+size-Historie fuer FOSS, APKMirror die letzten Stufen fuer (auch proprietäre) Apps.

## Verlauf in Stichpunkten

1. **Start**: gplaycli / playstoreapi / googleplay-api als Quelle verworfen (BadAuthentication, Token-Service down). Google Play bleibt fuer Historie endgueltig blockiert.
2. **apkeep + APKPure**: funktionsfaehiger Downloadalter APKs ohne Login (Versionsliste `-l` + gezielter Download `@Version`). Grosse Apps (WhatsApp 118 MB) verifiziert. Aber APKPure deckt nicht die gesamte Historie ab (WhatsApp erst ab 2.25.4; alte 2.16.x fehlt).
3. **Aptoide**: Versionsliste im `__NEXT_DATA__` der `/versions`-Seite. Durchbruch: `getMeta?app_id=<id>` liefert fuer **jede** alte Version md5 + Pool-Download-URL. Skript `aptoide_get.py` verifiziert (bis runter zu 2.2.5 von ~2018).
4. **Resolver-Idee**: Ein einzelner Store kennt nicht alle Namen. `resolver.py` baut die Kette F-Droid + Play + APKMirror, merge nach Package, Quellen als Badges, Forks/Alt-Packages als eigene Zeilen.
5. **Fixes nach Testlauf**: Izzy-URL korrigiert, Namens-Dedup vor Append, Fehler-Objekte nicht als Fake-Hits.
6. **Versionssammler** `appfind.py`: Adapter fuer APKMirror (letzte ~10) + F-Droid/Izzy (Historie inkl. vercode, sha256, url); Play als Store-Referenzzeile. Package-Lookup (`exact_by_package`) fuer direkte Paket-Anfragen.
7. **Regression & Robustheit**: APKMirror-Namensfilter zurueck (nur Namenssuche), Izzy-File-Base-URL korrigiert, `--pick` statt stilles First-Hit, `exact_by_package` faengt 403 von APKMirror.
8. **Aptoide-Adapter** `aptoide.py`: der eigentliche Archiv-Treffer – Versionshistorie bis in alte Stände inkl. Download-URL + MD5, in `appfind.py` integriert (WhatsApp → 19 Versionen, bis 2.17.253 von 2017).

## Noch offen / moegliche Erweiterungen

- **APKMirror-Althistorie**: ueber einzelne Release-Seiten/Varianten-Slugs statt App-Übersicht.
- **Play-Referenz** (aktuelle Version) als `current`-Zeile nutzbar fuer Abgleich.
- Downloads selbst uebernehmen: F-Droid-Direkt-URL (md5/sha256-Pruefung) bzw. apkeep (APKPure)/Aptoide-Pool-Pfad.