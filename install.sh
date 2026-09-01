#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == http://* || "${1:-}" == https://* ]]; then
  url="$1"
  name="$(basename "${url%.git}")"
  if [[ -d "$name" ]]; then
    ROOT="$(cd "$name" && pwd)"
  else
    git clone "$url"
    ROOT="$(cd "$name" && pwd)"
  fi
  cd "$ROOT"
else
  cd "$ROOT"
fi

command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
python3 -m venv --help >/dev/null 2>&1 || { echo "python3-venv missing (Debian: apt install python3-venv)"; exit 1; }

python3 -m venv --clear .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

echo
echo "Done. First F-Droid index sync runs on the first resolver.py call (not during install)."
echo
echo "Usage:"
echo "  source .venv/bin/activate"
echo "  python3 resolver.py \"signal\""
echo "  python3 appfind.py com.whatsapp --versions"
