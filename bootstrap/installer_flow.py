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
SOURCE_COMMIT = "84efc7c27a4679b2a3095a151d474ee40244ac15"


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
