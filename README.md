# appfind

*(Deutsch: [README_de.md](README_de.md))*

Resolve an **Android app name** to its **package ID**, then collect **available versions** across multiple stores — without silently picking the first hit.

One store never knows every name. Names are ambiguous; package IDs are not. So we query several sources, merge by package, and let you pick the candidate.

```text
Name ──► Resolver (F-Droid + Play + APKMirror) ──► candidate list
                                                      │
Package chosen ──► Version collector
                   (F-Droid/Izzy + APKMirror + Aptoide archive + Play current)
```

## Why this exists

- **FOSS apps**: F-Droid / IzzyOnDroid already expose real version history (vercode, hashes, URLs).
- **Proprietary / wide coverage**: Play is best for *finding* packages; APKMirror confirms recent builds.
- **Deep archive**: Aptoide often reaches years further back than APKMirror or APKPure (e.g. WhatsApp down to **2.17.253 / 2017**), with per-version MD5 + pool download path.

This repo is the Phase 1–2 toolkit: **name → package → version map**. Downloading with hash verification is a deliberate next step, not bundled yet.

## Layout

| File | Role |
|------|------|
| `resolver.py` | CLI: search, merge-by-package, ranking, JSON |
| `appfind.py` | Version collector (`--versions`), `--pick` for candidates |
| `fdroid.py` | F-Droid + IzzyOnDroid indexes, local cache, search + history |
| `play.py` | Google Play search (custom HTML parser) + package details |
| `apkmirror.py` | APKMirror HTML search + recent versions (403-tolerant) |
| `aptoide.py` | Aptoide archive adapter: old versions, download path + MD5 |

## Quick start

```bash
# Name → package candidates (source badges, merged by package)
python3 resolver.py "signal"
python3 resolver.py --json "firefox"
python3 resolver.py --no-play "vita"     # drop a source
python3 resolver.py --sync "signal"      # refresh F-Droid indexes

# Package (or name) → version lists
python3 appfind.py org.mozilla.firefox --versions
python3 appfind.py "antennapod" --versions
python3 appfind.py "firefox" --versions --pick 3   # pick candidate rank (default: 1)
python3 appfind.py org.mozilla.firefox --versions --json
```

`--pick` defaults to `1`. Use `--pick 0` for an interactive prompt (not used in JSON mode workflows that stick to the default).

## Source cheat sheet

| Source | Names | Version history | Notes |
|--------|-------|-----------------|-------|
| F-Droid / Izzy | strong for FOSS | **vercode + sha256 + url** | Izzy uses `apt.izzysoft.de/fdroid/repo`; v2 index is short |
| Google Play | best coverage | current only | reference row; no public history API |
| APKMirror | good confirmation | last ~10 | no versionCode in HTML; rate-limits / 403 |
| Aptoide | not used for name resolve | **best deep archive**, download + MD5 | `getMeta?app_id=` cached on disk; relative paths marked `path:` vs `https://` |

F-Droid and APKMirror complement each other: F-Droid for real FOSS history, APKMirror for recent proprietary builds.

## Design notes (adapters)

### Play (`play.py`)
`google-play-scraper`’s `search()` currently returns `appId: None` against live markup. We therefore:

- **Search** with a small HTML parser on `play.google.com/store/search` (`details?id=` links + title/developer/icon).
- **Details** still use the scraper’s working `app(pkg)` via a venv subprocess when present.

### F-Droid (`fdroid.py`)
- Downloads `index-v2.json` (f-droid.org + Izzy), then keeps a compact local `fdroid_index.json` for offline search.
- Full ancient history from classic `index-v1` is **not** in v2; `versions()` only returns what the v2 index still lists.
- Izzy packages get Izzy URLs (not dead `f-droid.org/packages/…` links).

### APKMirror (`apkmirror.py`)
- Package ID comes from the “View on Play Store” link, not the title.
- Token name-filter applies to **name search only** (avoids homepage junk). `by_package()` matches exactly.
- 403s are caught in `exact_by_package()` so Play/F-Droid can still win.
- App pages only expose roughly the newest ~10 releases — no central old-version pagination.

### Aptoide (`aptoide.py`) — the archive hit
- `getMeta?package_name=` → `uname`; `/versions` (`__NEXT_DATA__`) lists versions **including** the storefront current build.
- `getMeta?app_id=` → MD5 + pool path **per version**. Responses persist in `cache/aptoide_meta.json` (24h TTL, atomic write) so large catalogs don’t hammer rate limits.
- Relative `file.path` values are emitted as `path:…`; absolute URLs stay `https://…`.
- Example: WhatsApp → ~20 versions with URL + MD5, back to 2.17.253 (2017).

## Roadmap (intentionally later)

- APKMirror deeper history via per-release / variant pages
- First-class Play “current” row for cross-checking
- Actual downloads with MD5/SHA verification (F-Droid URLs, Aptoide pool, optional apkeep/APKPure)
- **Not planned as a fifth name source:** Uptodown — the JSON store list stays a map, not crawler feed

## License

Unlicense. Do whatever you want with this. No warranty.
Adapters will break when store markup or unofficial APIs change.
