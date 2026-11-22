import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from bootstrap.private_source import (
    SourceDownloadError,
    archive_sha256,
    extract_source_archive,
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
    def test_archive_digest(self):
        archive = make_archive()
        self.assertEqual(archive_sha256(archive), hashlib.sha256(archive).hexdigest())

    def test_safe_regular_file_extracted(self):
        archive = make_archive()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            extract_source_archive(archive, destination)
            self.assertEqual((destination / "README.md").read_bytes(), b"safe test source")

    def test_parent_traversal_rejected(self):
        archive = make_archive("repo-root/../../outside.txt")
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            with self.assertRaises(SourceDownloadError):
                extract_source_archive(archive, destination)
            self.assertFalse(destination.exists())

    def test_malformed_archive_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            with self.assertRaises(SourceDownloadError):
                extract_source_archive(b"not a tar archive", destination)
            self.assertFalse(destination.exists())

    def test_links_rejected(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("repo-root/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source"
            with self.assertRaises(SourceDownloadError):
                extract_source_archive(buffer.getvalue(), destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
