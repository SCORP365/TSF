"""Verify the signed release manifest before private source extraction."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from bootstrap.private_source import SourceDownloadError

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_REPOSITORY = "SCORP365/TSF-Connect"


def verify_signed_manifest(
    manifest_bytes: bytes,
    signature: bytes,
    public_key_path: Path,
) -> dict:
    """Verify Ed25519 signature over exact manifest bytes, then validate fields.

    The public key is a trust anchor and must be pinned in the bootstrap release.
    The private signing key must never be stored in either GitHub repository or VPS.
    """
    openssl = shutil.which("openssl")
    if not openssl:
        raise SourceDownloadError("OpenSSL is required for release signature verification.")
    public_key_path = Path(public_key_path)
    if not public_key_path.is_file() or public_key_path.is_symlink():
        raise SourceDownloadError("The pinned release verification key is missing.")

    with tempfile.TemporaryDirectory(prefix="tsf-manifest-") as tmp:
        tmp_path = Path(tmp)
        manifest_file = tmp_path / "manifest.json"
        signature_file = tmp_path / "manifest.sig"
        manifest_file.write_bytes(manifest_bytes)
        signature_file.write_bytes(signature)
        for path in (manifest_file, signature_file):
            path.chmod(0o600)

        result = subprocess.run(
            [
                openssl, "pkeyutl", "-verify", "-pubin",
                "-inkey", str(public_key_path),
                "-rawin", "-in", str(manifest_file),
                "-sigfile", str(signature_file),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        if result.returncode != 0:
            raise SourceDownloadError("Release signature verification failed.")

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SourceDownloadError("The signed release manifest is not valid JSON.") from None

    if not isinstance(manifest, dict):
        raise SourceDownloadError("The signed release manifest has an invalid structure.")

    repository = manifest.get("repository")
    commit = manifest.get("commit")
    archive_sha256 = manifest.get("archive_sha256")
    release_version = manifest.get("release_version")

    if repository != EXPECTED_REPOSITORY:
        raise SourceDownloadError("The signed manifest identifies an unexpected repository.")
    if not isinstance(commit, str) or not _SHA_RE.fullmatch(commit):
        raise SourceDownloadError("The signed manifest does not contain a full commit SHA.")
    if not isinstance(archive_sha256, str) or not _HEX_RE.fullmatch(archive_sha256):
        raise SourceDownloadError("The signed manifest contains an invalid archive digest.")
    if (
        not isinstance(release_version, str)
        or not release_version
        or len(release_version) > 64
        or any(ord(ch) < 32 for ch in release_version)
    ):
        raise SourceDownloadError("The signed manifest contains an invalid release version.")

    return {
        "repository": repository,
        "commit": commit,
        "archive_sha256": archive_sha256,
        "release_version": release_version,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
