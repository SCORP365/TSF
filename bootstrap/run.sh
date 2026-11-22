#!/usr/bin/env bash
# Public TSF Connect bootstrap launcher. Run only from a reviewed, pinned checkout.
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || {
  echo "Запустите от root: sudo bash bootstrap/run.sh" >&2
  exit 1
}
command -v apt-get >/dev/null 2>&1 || {
  echo "Требуется Ubuntu/Debian с apt-get." >&2
  exit 1
}
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates python3 qrencode

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"
exec python3 -m bootstrap.cli "$@"
