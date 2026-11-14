"""Checks for the optional video-restoration boundary, without network access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('get_recordings', Path(__file__).resolve().parents[1] / 'tools/get_recordings.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecordingDownloadTests(unittest.TestCase):
    def fixture(self, directory, name='data/videos/clip.mov', payload=b'original recording', expected_hash=None):
        archive = directory / 'videos.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as z:
            z.writestr(name, payload)
        import hashlib
        item = {'path': name, 'bytes': len(payload), 'sha256': expected_hash or hashlib.sha256(payload).hexdigest()}
        return archive, {'bytes': archive.stat().st_size, 'sha256': MODULE.digest(archive), 'recordings': [item]}

    def test_restore_exact_bytes_and_skip_existing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'project'
            archive, group = self.fixture(Path(d))
            self.assertEqual(MODULE.restore_archive(root, archive, group), 1)
            self.assertEqual((root/'data/videos/clip.mov').read_bytes(), b'original recording')
            self.assertEqual(MODULE.restore_archive(root, archive, group), 0)

    def test_corrupt_archive_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as d:
            archive, group = self.fixture(Path(d))
            archive.write_bytes(archive.read_bytes() + b'changed')
            with self.assertRaises(ValueError): MODULE.restore_archive(Path(d)/'project', archive, group)
            self.assertFalse((Path(d)/'project').exists())

    def test_wrong_video_hash_leaves_no_published_file(self):
        with tempfile.TemporaryDirectory() as d:
            archive, group = self.fixture(Path(d), expected_hash='0'*64)
            root = Path(d)/'project'
            with self.assertRaises(ValueError): MODULE.restore_archive(root, archive, group)
            self.assertFalse((root/'data/videos/clip.mov').exists())
            self.assertFalse(list(root.rglob('.restore-*')))

    def test_existing_different_video_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'project'
            target = root/'data/videos/clip.mov'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'user recording')
            archive, group = self.fixture(Path(d))
            with self.assertRaises(ValueError): MODULE.restore_archive(root, archive, group)
            self.assertEqual(target.read_bytes(), b'user recording')

    def test_traversal_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            archive, group = self.fixture(Path(d), name='data/../../escape.mov')
            with self.assertRaises(ValueError): MODULE.restore_archive(Path(d)/'project', archive, group)
            self.assertFalse((Path(d)/'escape.mov').exists())

    def test_symlink_parent_cannot_escape_data_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'project'
            (root/'data').mkdir(parents=True)
            outside = Path(d)/'outside'; outside.mkdir()
            (root/'data/videos').symlink_to(outside, target_is_directory=True)
            archive, group = self.fixture(Path(d))
            with self.assertRaises(ValueError): MODULE.restore_archive(root, archive, group)
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
