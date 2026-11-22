#!/usr/bin/env bash
# Exercise offline signing with a disposable CI-only Ed25519 key pair.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

openssl genpkey -algorithm ED25519 -out "$TMP/private.pem"
chmod 0600 "$TMP/private.pem"
openssl pkey -in "$TMP/private.pem" -pubout -out "$TMP/public.pem"
FINGERPRINT="$(tr -d '\r' < "$TMP/public.pem" | sha256sum | cut -d' ' -f1)"

# Substitute only the pinned fingerprint in a disposable test copy. The
# production helper remains pinned to the real offline release public key.
sed "s/32dec00fc5c068ee7b2df2c07786c2698139c178b1b1c452a76d22d70066b9bf/$FINGERPRINT/" \
  "$ROOT/bootstrap/sign-manifest.sh" > "$TMP/sign-manifest.sh"
chmod 0700 "$TMP/sign-manifest.sh"

mkdir -p "$TMP/source"
printf 'test-only source\n' > "$TMP/source/README.txt"
tar -czf "$TMP/source.tar.gz" -C "$TMP" source
COMMIT=0123456789abcdef0123456789abcdef01234567

bash "$TMP/sign-manifest.sh" "$TMP/source.tar.gz" "$COMMIT" test.0.1 \
  "$TMP/private.pem" "$TMP/public.pem" "$TMP/output"

openssl pkeyutl -verify -pubin -inkey "$TMP/public.pem" -rawin \
  -in "$TMP/output/manifest.json" -sigfile "$TMP/output/manifest.sig" >/dev/null
python3 - "$TMP/output/manifest.json" "$TMP/source.tar.gz" "$COMMIT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
archive = Path(sys.argv[2]).read_bytes()
assert manifest["repository"] == "SCORP365/TSF-Connect"
assert manifest["commit"] == sys.argv[3]
assert manifest["archive_sha256"] == hashlib.sha256(archive).hexdigest()
assert manifest["release_version"] == "test.0.1"
PY

openssl genpkey -algorithm ED25519 -out "$TMP/wrong-private.pem"
chmod 0600 "$TMP/wrong-private.pem"
if bash "$TMP/sign-manifest.sh" "$TMP/source.tar.gz" "$COMMIT" test.0.1 \
  "$TMP/wrong-private.pem" "$TMP/public.pem" "$TMP/wrong-output" >/dev/null 2>&1; then
  echo "FAIL: signer accepted a private key that does not match the pinned public key." >&2
  exit 1
fi

ln -s "$TMP" "$TMP/symlink-output"
if bash "$TMP/sign-manifest.sh" "$TMP/source.tar.gz" "$COMMIT" test.0.1 \
  "$TMP/private.pem" "$TMP/public.pem" "$TMP/symlink-output" >/dev/null 2>&1; then
  echo "FAIL: signer accepted a symlink as its output directory." >&2
  exit 1
fi

echo "OK: offline signer checks the pinned key pair and verifies signed manifest/archive digest."
