"""Download the exact private GitHub archive that the TSF bootstrap will verify."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from bootstrap.device_flow import DeviceFlowError, authorize
from bootstrap.private_source import SourceDownloadError, download_pinned_archive

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a private TSF-Connect source archive by immutable commit SHA using GitHub Device Flow."
    )
    parser.add_argument("commit", help="full lowercase 40-character commit SHA")
    parser.add_argument("output", type=Path, help="new archive file path; existing files are never overwritten")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not isinstance(args.commit, str) or not _SHA_RE.fullmatch(args.commit):
        print("ERROR: commit must be a full lowercase 40-character SHA.", file=sys.stderr)
        return 2

    output = args.output.expanduser()
    if output.exists() or output.is_symlink():
        print("ERROR: output path already exists; refusing to overwrite it.", file=sys.stderr)
        return 2
    if not output.parent.is_dir():
        print("ERROR: output parent directory does not exist.", file=sys.stderr)
        return 2

    token = None
    try:
        token = authorize()
        archive = download_pinned_archive(token, args.commit)
        token = None
        digest = hashlib.sha256(archive).hexdigest()

        try:
            with output.open("xb") as stream:
                stream.write(archive)
                stream.flush()
        except OSError:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        try:
            output.chmod(0o600)
        except OSError:
            output.unlink(missing_ok=True)
            raise

        print(f"Archive saved: {output}")
        print(f"Commit: {args.commit}")
        print(f"Size: {len(archive)} bytes")
        print(f"SHA-256: {digest}")
        print("The short-lived GitHub token was not saved.")
        return 0
    except (DeviceFlowError, SourceDownloadError, OSError) as exc:
        token = None
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
