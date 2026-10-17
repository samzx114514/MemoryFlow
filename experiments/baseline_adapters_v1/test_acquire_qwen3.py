import hashlib
from pathlib import Path
import tempfile
import unittest

from acquire_qwen3 import verify_file


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'fixture'
        self.path.write_bytes(b'abc')

    def test_sha256_identity(self):
        row = dict(bytes=3, sha256=hashlib.sha256(b'abc').hexdigest())
        self.assertTrue(verify_file(self.path, row)['official_identity_match'])

    def test_git_blob_identity(self):
        row = dict(bytes=3, git_blob=hashlib.sha1(b'blob 3\0abc').hexdigest())
        self.assertTrue(verify_file(self.path, row)['official_identity_match'])

    def test_wrong_size_rejected(self):
        with self.assertRaises(ValueError):
            verify_file(self.path, dict(bytes=4, sha256='unused'))

    def test_wrong_hash_rejected(self):
        with self.assertRaises(ValueError):
            verify_file(self.path, dict(bytes=3, sha256='0'*64))


if __name__ == '__main__':
    unittest.main()
