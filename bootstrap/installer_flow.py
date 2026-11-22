"""Retrieve the pinned private TSF Connect source through GitHub Device Flow."""
from __future__ import annotations

from pathlib import Path

from bootstrap.device_flow import authorize
from bootstrap.private_source import (
    SourceDownloadError,
    archive_sha256,
    download_pinned_archive,
    extract_source_archive,
)

# Update this value only after the matching private-repository commit has passed CI.
SOURCE_COMMIT = "8e85f31b8d42fd6b75e73176bee512c12087b1a1"


def retrieve_source(work_dir: Path) -> tuple[Path, str]:
    """Authorize, download the exact pinned commit, and safely extract it."""
    token = authorize()
    try:
        archive = download_pinned_archive(token, SOURCE_COMMIT)
    finally:
        token = None

    digest = archive_sha256(archive)
    destination = Path(work_dir) / f"source-{SOURCE_COMMIT[:12]}"
    source = extract_source_archive(archive, destination)
    return source, digest
