import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from bootstrap.private_source import (
    SourceDownloadError,
    extract_verified_archive,
    verify_archive_digest,
)


def make_archive(name="repo-root/README.md", content=b"safe test source"):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class PrivateSourceTests(unittest.TestCase):
    def test_digest_matches(self):
        archive = make_archive()
        verify_archive_digest(archive, hashlib.sha256(archive).hexdigest())

    def test_digest_mismatch_rejected(self):
        with self.assertRaises(SourceDownloadError):
            verify_archive_digest(make_archive(), "0" * 64)

    def test_extraction_requires_verified_manifest(self):
        archive = make_archive()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            with self.assertRaises(SourceDownloadError):
                extract_verified_archive(
                    archive, destination,
                    expected_sha256=hashlib.sha256(archive).hexdigest(),
                    manifest_is_verified=False,
                )
            self.assertFalse(destination.exists())

    def test_safe_regular_file_extracted(self):
        archive = make_archive()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            extract_verified_archive(
                archive, destination,
                expected_sha256=hashlib.sha256(archive).hexdigest(),
                manifest_is_verified=True,
            )
            self.assertEqual(
                (destination / "README.md").read_bytes(),
                b"safe test source",
            )

    def test_parent_traversal_rejected(self):
        archive = make_archive("repo-root/../../outside.txt")
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            with self.assertRaises(SourceDownloadError):
                extract_verified_archive(
                    archive, destination,
                    expected_sha256=hashlib.sha256(archive).hexdigest(),
                    manifest_is_verified=True,
                )
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
