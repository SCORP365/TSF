import base64
import json
import unittest
from unittest.mock import patch

from bootstrap.installer_flow import _fetch_private_text_file
from bootstrap.private_source import SourceDownloadError


class Response:
    def __init__(self, payload, url="https://api.github.com/test"):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self.payload

    def geturl(self):
        return self.url


class InstallerFlowTests(unittest.TestCase):
    def test_decodes_contents_api_file(self):
        original = b'{"repository":"SCORP365/TSF-Connect"}'
        payload = json.dumps({
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(original).decode(),
        }).encode()
        with patch("bootstrap.installer_flow.urllib.request.urlopen", return_value=Response(payload)):
            self.assertEqual(
                _fetch_private_text_file("fake-token-for-test-only", "manifest.json"),
                original,
            )

    def test_rejects_non_file_content(self):
        payload = json.dumps({"type": "dir", "encoding": "base64", "content": ""}).encode()
        with patch("bootstrap.installer_flow.urllib.request.urlopen", return_value=Response(payload)):
            with self.assertRaises(SourceDownloadError):
                _fetch_private_text_file("fake-token-for-test-only", "manifest.json")

    def test_rejects_http_redirect_to_non_https(self):
        payload = json.dumps({
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(b"data").decode(),
        }).encode()
        with patch(
            "bootstrap.installer_flow.urllib.request.urlopen",
            return_value=Response(payload, "http://attacker.invalid/file"),
        ):
            with self.assertRaises(SourceDownloadError):
                _fetch_private_text_file("fake-token-for-test-only", "manifest.json")


if __name__ == "__main__":
    unittest.main()
