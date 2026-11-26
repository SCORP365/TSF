#!/usr/bin/env bash
# Compatibility entry point: the first run installs only the standalone manager.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "Запустите от root: sudo bash install.sh" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Требуется Python 3." >&2; exit 1; }
TMP="$(mktemp /var/tmp/tsf-connect-manager-bootstrap.XXXXXX)"
trap 'rm -f -- "$TMP"' EXIT
python3 - "$TMP" <<'PY'
import pathlib, sys, urllib.request
url = "https://raw.githubusercontent.com/SCORP365/TSF/main/install-manager.sh"
request = urllib.request.Request(url, headers={"User-Agent": "TSF-Connect-Bootstrap"})
with urllib.request.urlopen(request, timeout=30) as response:
    content = response.read(1024 * 1024 + 1)
if len(content) > 1024 * 1024 or not content.startswith(b"#!/usr/bin/env bash"):
    raise SystemExit("Некорректный ответ bootstrap-сервера.")
pathlib.Path(sys.argv[1]).write_bytes(content)
PY
bash "$TMP" "$@"
