#!/usr/bin/env bash
# TSF Connect - offline release manifest signing
set -Eeuo pipefail
umask 077

EXPECTED_PUBLIC_KEY_SHA256=32dec00fc5c068ee7b2df2c07786c2698139c178b1b1c452a76d22d70066b9bf

usage() {
  echo "Usage: $0 <archive.tar.gz> <full-commit-sha> <release-version> <private-ed25519-key> <pinned-public-key> <output-dir>" >&2
  exit 2
}

[[ $# -eq 6 ]] || usage
ARCHIVE="$1"
COMMIT="$2"
VERSION="$3"
PRIVATE_KEY="$4"
PUBLIC_KEY="$5"
OUTPUT_DIR="$6"

[[ -f "$ARCHIVE" && ! -L "$ARCHIVE" ]] || { echo "Archive must be a regular file." >&2; exit 1; }
[[ -f "$PRIVATE_KEY" && ! -L "$PRIVATE_KEY" ]] || { echo "Private signing key must be a regular file." >&2; exit 1; }
[[ -f "$PUBLIC_KEY" && ! -L "$PUBLIC_KEY" ]] || { echo "Pinned public key must be a regular file." >&2; exit 1; }
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit must be a full lowercase 40-character SHA." >&2; exit 1; }
[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$ ]] || { echo "Invalid release version." >&2; exit 1; }
for command in openssl sha256sum python3 stat id find install mktemp cmp tr; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

KEY_MODE="$(stat -c '%a' "$PRIVATE_KEY")"
(( (8#$KEY_MODE & 077) == 0 )) || { echo "Private key permissions must be 0600 or stricter." >&2; exit 1; }
KEY_OWNER="$(stat -c '%u' "$PRIVATE_KEY")"
[[ "$KEY_OWNER" == "$(id -u)" ]] || { echo "Private key must be owned by the current signing user." >&2; exit 1; }

TMP="$(mktemp -d)"
OUTPUT_CREATED=0
cleanup() {
  status=$?
  rm -rf -- "$TMP"
  if (( status != 0 && OUTPUT_CREATED )); then rm -rf -- "$OUTPUT_DIR"; fi
  exit "$status"
}
trap cleanup EXIT
DERIVED_PUBLIC="$TMP/derived-public.pem"
PUBLIC_DER="$TMP/public.der"
DERIVED_DER="$TMP/derived-public.der"
MANIFEST_TMP="$TMP/manifest.json"
SIGNATURE_TMP="$TMP/manifest.sig"

# Normalize CRLF only for fingerprinting; PEM parsing remains OpenSSL's job.
PUBLIC_FINGERPRINT="$(tr -d '\r' < "$PUBLIC_KEY" | sha256sum | cut -d' ' -f1)"
[[ "$PUBLIC_FINGERPRINT" == "$EXPECTED_PUBLIC_KEY_SHA256" ]] || {
  echo "The supplied public key does not match the pinned TSF release key." >&2
  exit 1
}
openssl pkey -in "$PRIVATE_KEY" -pubout -out "$DERIVED_PUBLIC"
openssl pkey -pubin -in "$PUBLIC_KEY" -outform DER -out "$PUBLIC_DER"
openssl pkey -pubin -in "$DERIVED_PUBLIC" -outform DER -out "$DERIVED_DER"
cmp -s "$PUBLIC_DER" "$DERIVED_DER" || {
  echo "The private key does not match the pinned TSF public key." >&2
  exit 1
}

[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || {
  echo "Output directory must not already exist." >&2
  exit 1
}
mkdir -p "$(dirname "$OUTPUT_DIR")"
mkdir -m 700 "$OUTPUT_DIR"
OUTPUT_CREATED=1

ARCHIVE_SHA256="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
[[ "$ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "Could not calculate archive digest." >&2; exit 1; }

python3 - "$COMMIT" "$VERSION" "$ARCHIVE_SHA256" > "$MANIFEST_TMP" <<'PY'
import json
import sys

commit, version, archive_sha256 = sys.argv[1:]
manifest = {
    "repository": "SCORP365/TSF-Connect",
    "commit": commit,
    "archive_sha256": archive_sha256,
    "release_version": version,
}
sys.stdout.write(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
PY

openssl pkeyutl -sign -inkey "$PRIVATE_KEY" -rawin \
  -in "$MANIFEST_TMP" -out "$SIGNATURE_TMP"
openssl pkeyutl -verify -pubin -inkey "$PUBLIC_KEY" -rawin \
  -in "$MANIFEST_TMP" -sigfile "$SIGNATURE_TMP" >/dev/null

install -m 600 "$MANIFEST_TMP" "$OUTPUT_DIR/manifest.json"
install -m 600 "$SIGNATURE_TMP" "$OUTPUT_DIR/manifest.sig"
echo "Signed manifest created:"
echo "  $OUTPUT_DIR/manifest.json"
echo "  $OUTPUT_DIR/manifest.sig"
echo "Archive SHA-256: $ARCHIVE_SHA256"
echo "Public key fingerprint: $PUBLIC_FINGERPRINT"
echo "Keep the private key offline. Publish only manifest.json and manifest.sig."
OUTPUT_CREATED=0
