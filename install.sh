#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == http://* || "${1:-}" == https://* ]]; then
  url="$1"
  name="$(basename "${url%.git}")"
  git clone "$url"
  ROOT="$(cd "$name" && pwd)"
  cd "$ROOT"
else
  cd "$ROOT"
fi

python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

echo
echo "Done. First F-Droid index sync runs on the first resolver.py call (not during install)."
echo
echo "Usage:"
echo "  source .venv/bin/activate"
echo "  python3 resolver.py \"signal\""
echo "  python3 appfind.py com.whatsapp --versions"
