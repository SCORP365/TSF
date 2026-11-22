import unittest

from bootstrap.installer_flow import SOURCE_COMMIT
from bootstrap.private_source import _SHA_RE


class InstallerFlowTests(unittest.TestCase):
    def test_source_commit_is_full_immutable_sha(self):
        self.assertRegex(SOURCE_COMMIT, _SHA_RE)


if __name__ == "__main__":
    unittest.main()
