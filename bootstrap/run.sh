#!/usr/bin/env bash
# Public TSF Connect bootstrap launcher. Run only from a reviewed, pinned checkout.
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PUBLIC_KEY="$ROOT_DIR/bootstrap/keys/tsf-release-ed25519-public.pem"
EXPECTED_FINGERPRINT=32dec00fc5c068ee7b2df2c07786c2698139c178b1b1c452a76d22d70066b9bf

[[ $EUID -eq 0 ]] || {
  echo "Запустите от root: sudo bash bootstrap/run.sh" >&2
  exit 1
}
[[ -f "$PUBLIC_KEY" && ! -L "$PUBLIC_KEY" ]] || {
  echo "Не найден закреплённый публичный ключ TSF Connect." >&2
  exit 1
}
ACTUAL_FINGERPRINT="$(sha256sum "$PUBLIC_KEY" | cut -d' ' -f1)"
[[ "$ACTUAL_FINGERPRINT" == "$EXPECTED_FINGERPRINT" ]] || {
  echo "Fingerprint публичного ключа не совпадает с закреплённым значением." >&2
  exit 1
}

command -v apt-get >/dev/null 2>&1 || {
  echo "Требуется Ubuntu/Debian с apt-get." >&2
  exit 1
}
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates openssl python3 qrencode

cd "$ROOT_DIR"
exec python3 -m bootstrap.cli "$@"
