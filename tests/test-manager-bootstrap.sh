#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
bash -n "$ROOT/install.sh"
bash -n "$ROOT/install-manager.sh"
TMP="$(mktemp --suffix=.py)"
trap 'rm -f "$TMP"' EXIT
awk "/^python3 - .*<<'PY'$/ { if (seen++) exit; active=1; next } active && /^PY$/ { exit } active { print }" "$ROOT/install-manager.sh" > "$TMP"
python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))' "$TMP"
echo "OK: manager bootstrap shell and embedded Python syntax."
