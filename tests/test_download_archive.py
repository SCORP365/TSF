import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bootstrap import download_archive


class DownloadArchiveTests(unittest.TestCase):
    def test_downloads_exact_archive_and_writes_digest(self):
        archive = b"exact github archive bytes"
        commit = "0123456789abcdef0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "TSF-Connect.tar.gz"
            with patch.object(download_archive, "authorize", return_value="short-lived-token"), \
                 patch.object(download_archive, "download_pinned_archive", return_value=archive) as download, \
                 patch("builtins.print") as printed:
                self.assertEqual(download_archive.main([commit, str(output)]), 0)
            download.assert_called_once_with("short-lived-token", commit)
            self.assertEqual(output.read_bytes(), archive)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            rendered = " ".join(str(call.args) for call in printed.call_args_list)
            self.assertIn(hashlib.sha256(archive).hexdigest(), rendered)

    def test_rejects_invalid_commit_before_authorization(self):
        with patch.object(download_archive, "authorize") as authorize:
            self.assertEqual(download_archive.main(["not-a-sha", "archive.tar.gz"]), 2)
        authorize.assert_not_called()

    def test_refuses_to_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "archive.tar.gz"
            output.write_bytes(b"keep")
            with patch.object(download_archive, "authorize") as authorize:
                self.assertEqual(
                    download_archive.main([
                        "0123456789abcdef0123456789abcdef01234567", str(output)
                    ]),
                    2,
                )
            authorize.assert_not_called()
            self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
