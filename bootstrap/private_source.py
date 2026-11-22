"""Authenticated retrieval of a pinned private TSF-Connect source archive."""
from __future__ import annotations

import hashlib
import io
import re
import shutil
import tarfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

OWNER = "SCORP365"
REPOSITORY = "TSF-Connect"
API_ROOT = "https://api.github.com"
USER_AGENT = "TSF-Connect-Bootstrap/0.2"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class SourceDownloadError(RuntimeError):
    """Safe, user-displayable source retrieval error."""


def _github_request(url: str, token: str, accept: str) -> bytes:
    if not url.startswith(API_ROOT + "/"):
        raise SourceDownloadError("Refusing a non-GitHub API URL.")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if not response.geturl().startswith("https://"):
                raise SourceDownloadError("GitHub returned an insecure download redirect.")
            data = response.read(128 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise SourceDownloadError(
                "Private repository access failed. Check GitHub App installation and repository permissions."
            ) from None
        raise SourceDownloadError(f"GitHub download failed with HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError):
        raise SourceDownloadError("Cannot download private source from GitHub.") from None

    if len(data) > 128 * 1024 * 1024:
        raise SourceDownloadError("The source archive exceeds the 128 MiB safety limit.")
    return data


def download_pinned_archive(token: str, commit_sha: str) -> bytes:
    """Download an archive for an immutable 40-character commit SHA."""
    if not isinstance(token, str) or len(token) < 20 or "\n" in token or "\r" in token:
        raise SourceDownloadError("Invalid GitHub access token.")
    if not isinstance(commit_sha, str) or not _SHA_RE.fullmatch(commit_sha):
        raise SourceDownloadError("A full immutable commit SHA is required.")
    url = f"{API_ROOT}/repos/{OWNER}/{REPOSITORY}/tarball/{commit_sha}"
    return _github_request(url, token, "application/vnd.github+json")


def archive_sha256(archive: bytes) -> str:
    """Return the SHA-256 digest for logging and release records."""
    return hashlib.sha256(archive).hexdigest()


def extract_source_archive(archive: bytes, destination: Path) -> Path:
    """Safely extract regular files/directories from a pinned GitHub archive."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise SourceDownloadError("Extraction destination must not already exist.")
    destination.mkdir(mode=0o700, parents=True)
    root = destination.resolve(strict=True)

    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            members = bundle.getmembers()
            if not members or len(members) > 20000:
                raise SourceDownloadError("The source archive has an invalid file count.")
            top_levels = set()
            safe_members = []
            total_unpacked = 0
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or not path.parts or any(p in ("", ".", "..") for p in path.parts):
                    raise SourceDownloadError("The archive contains an unsafe path.")
                top_levels.add(path.parts[0])
                if not (member.isdir() or member.isfile()):
                    raise SourceDownloadError("The archive contains a link or special file.")
                if member.size < 0 or member.size > 64 * 1024 * 1024:
                    raise SourceDownloadError("The archive contains an oversized file.")
                total_unpacked += member.size
                if total_unpacked > 256 * 1024 * 1024:
                    raise SourceDownloadError("The unpacked source exceeds the 256 MiB safety limit.")
                safe_members.append((member, path))
            if len(top_levels) != 1:
                raise SourceDownloadError("The archive layout is unexpected.")

            for member, path in safe_members:
                relative = PurePosixPath(*path.parts[1:])
                if not relative.parts:
                    continue
                target = root.joinpath(*relative.parts)
                resolved_parent = target.parent.resolve()
                if resolved_parent != root and root not in resolved_parent.parents:
                    raise SourceDownloadError("The archive path escapes the extraction directory.")
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise SourceDownloadError("Could not read an archive file.")
                with source, target.open("xb") as output:
                    output.write(source.read(member.size))
                target.chmod(0o600)
        return destination
    except tarfile.TarError:
        shutil.rmtree(destination, ignore_errors=True)
        raise SourceDownloadError("The downloaded source archive is damaged or invalid.") from None
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
