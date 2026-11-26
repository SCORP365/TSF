#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
bash -n "$ROOT/install.sh"
bash -n "$ROOT/install-manager.sh"
TMP="$(mktemp --suffix=.py)"
trap 'rm -f "$TMP"' EXIT
awk "/^python3 - .*<<'PY'$/ { if (seen++) exit; active=1; next } active && /^PY$/ { exit } active { print }" "$ROOT/install-manager.sh" > "$TMP"
python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))' "$TMP"
grep -Fq 'contents/manager/manager.py?ref=' "$ROOT/install-manager.sh"
grep -Fq 'STATE=/var/lib/tsf-connect-manager' "$ROOT/install-manager.sh"
grep -Fq 'chmod 0600 "$STATE/github-token"' "$ROOT/install-manager.sh"
grep -Fq 'os.chmod(state_tmp, 0o600)' "$ROOT/install-manager.sh"
grep -Fq 'state_path = TOKEN_PATH.with_name("state.json")' "$ROOT/install-manager.sh"
grep -Fq 'latest_commit": commit_sha' "$ROOT/install-manager.sh"
grep -Fq 'contents/manager/manager.py?ref={commit_sha}' "$ROOT/install-manager.sh"
if grep -E '/git/(trees|blobs)/' "$ROOT/install-manager.sh"; then
  echo "FAIL: first-run bootstrap must not download the full source tree." >&2
  exit 1
fi
echo "OK: manager bootstrap shell and embedded Python syntax."
