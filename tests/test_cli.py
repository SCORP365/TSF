import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bootstrap import cli


class BootstrapCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / "stage"
        self.stage.mkdir(mode=0o700)
        self.stage.chmod(0o700)
        self.source = self.root / "source"
        self.source.mkdir(mode=0o700)
        self.key = self.root / "public.pem"
        self.key.write_text("test-only-public-key", encoding="utf-8")

    def _patch_common(self):
        return (
            patch.object(cli, "STAGING_ROOT", self.stage),
            patch.object(cli, "PUBLIC_KEY", self.key),
            patch.object(cli.os, "geteuid", side_effect=[0, self.stage.stat().st_uid]),
            patch.object(cli, "retrieve_verified_source", return_value=self.source),
        )

    def test_retrieve_only_never_runs_installer(self):
        patches = self._patch_common()
        with patches[0], patches[1], patches[2], patches[3], patch.object(cli.subprocess, "run") as run:
            self.assertEqual(cli.main(["--retrieve-only"]), 0)
            run.assert_not_called()

    def test_default_mode_fails_closed_when_installer_missing(self):
        patches = self._patch_common()
        with patches[0], patches[1], patches[2], patches[3], patch.object(cli.subprocess, "run") as run:
            self.assertEqual(cli.main([]), 1)
            run.assert_not_called()

    def test_default_mode_runs_only_verified_installer(self):
        installer = self.source / "installer" / "install.sh"
        installer.parent.mkdir()
        installer.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        patches = self._patch_common()
        with patches[0], patches[1], patches[2], patches[3], patch.object(
            cli.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()
        ) as run:
            self.assertEqual(cli.main([]), 0)
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["bash", str(installer)])
            self.assertEqual(kwargs["cwd"], self.source)
            self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
            self.assertEqual(kwargs["env"]["TSF_BOOTSTRAP_SOURCE"], str(self.source))


if __name__ == "__main__":
    unittest.main()
