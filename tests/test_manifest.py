import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bootstrap.manifest import verify_signed_manifest
from bootstrap.private_source import SourceDownloadError


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "repository": "SCORP365/TSF-Connect",
            "commit": "a" * 40,
            "archive_sha256": "b" * 64,
            "release_version": "0.1.0",
        }
        self.raw = json.dumps(self.payload, separators=(",", ":")).encode()

    def test_valid_signature_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "public.pem"
            key.write_text("test public key")
            with patch("bootstrap.manifest.shutil.which", return_value="/usr/bin/openssl"), \
                 patch("bootstrap.manifest.subprocess.run", return_value=SimpleNamespace(returncode=0)):
                result = verify_signed_manifest(self.raw, b"signature", key)
        self.assertEqual(result["commit"], "a" * 40)
        self.assertEqual(result["archive_sha256"], "b" * 64)

    def test_bad_signature_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "public.pem"
            key.write_text("test public key")
            with patch("bootstrap.manifest.shutil.which", return_value="/usr/bin/openssl"), \
                 patch("bootstrap.manifest.subprocess.run", return_value=SimpleNamespace(returncode=1)):
                with self.assertRaises(SourceDownloadError):
                    verify_signed_manifest(self.raw, b"bad-signature", key)

    def test_wrong_repository_rejected_after_signature(self):
        payload = dict(self.payload, repository="attacker/other")
        raw = json.dumps(payload, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "public.pem"
            key.write_text("test public key")
            with patch("bootstrap.manifest.shutil.which", return_value="/usr/bin/openssl"), \
                 patch("bootstrap.manifest.subprocess.run", return_value=SimpleNamespace(returncode=0)):
                with self.assertRaises(SourceDownloadError):
                    verify_signed_manifest(raw, b"signature", key)


if __name__ == "__main__":
    unittest.main()
