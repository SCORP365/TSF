"""Non-executing end-to-end bootstrap retrieval flow."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bootstrap.device_flow import authorize
from bootstrap.manifest import verify_signed_manifest
from bootstrap.private_source import (
    SourceDownloadError,
    download_pinned_archive,
    extract_verified_archive,
)

OWNER = "SCORP365"
REPOSITORY = "TSF-Connect"
MANIFEST_REF = "release-manifests"
API_ROOT = "https://api.github.com"
USER_AGENT = "TSF-Connect-Bootstrap/0.1"


def _fetch_private_text_file(token: str, path: str) -> bytes:
    encoded_path = urllib.parse.quote(path, safe="/")
    query = urllib.parse.urlencode({"ref": MANIFEST_REF})
    url = f"{API_ROOT}/repos/{OWNER}/{REPOSITORY}/contents/{encoded_path}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if not response.geturl().startswith("https://"):
                raise SourceDownloadError("GitHub returned an insecure metadata redirect.")
            payload = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise SourceDownloadError(f"Could not retrieve signed release metadata (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError):
        raise SourceDownloadError("Cannot retrieve signed release metadata from GitHub.") from None

    if len(payload) > 2 * 1024 * 1024:
        raise SourceDownloadError("Signed release metadata is unexpectedly large.")
    try:
        item = json.loads(payload.decode("utf-8"))
        if item.get("type") != "file" or item.get("encoding") != "base64":
            raise ValueError
        return base64.b64decode(item["content"], validate=True)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise SourceDownloadError("GitHub returned invalid signed release metadata.") from None


def retrieve_verified_source(work_dir: Path, public_key_path: Path) -> Path:
    """Authorize, verify metadata and archive, then extract; never execute."""
    token = authorize()
    try:
        manifest_bytes = _fetch_private_text_file(token, "manifest.json")
        signature = _fetch_private_text_file(token, "manifest.sig")
        manifest = verify_signed_manifest(manifest_bytes, signature, public_key_path)
        archive = download_pinned_archive(token, manifest["commit"])
    finally:
        # Drop the local reference as soon as the authenticated requests finish.
        token = None

    destination = Path(work_dir) / f"source-{manifest['commit'][:12]}"
    return extract_verified_archive(
        archive,
        destination,
        expected_sha256=manifest["archive_sha256"],
        manifest_is_verified=True,
    )
