"""Provenance checks must reject wrong, altered or unverified derivatives."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from optical_link.recording_provenance import verify_recording


class RecordingProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'data'
        self.root.mkdir()
        self.source = self.root/'recording.mov'
        self.source.write_bytes(b'verified silent container')
        self.original = hashlib.sha256(b'original container').hexdigest()
        self.actual = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.entry = {'path': 'data/recording.mov', 'original_sha256': self.original,
                      'sha256': self.actual, 'bytes': self.source.stat().st_size,
                      'representation': 'silent-video-copy'}
        self.proof = {**self.entry, 'audio_streams_after': 0,
                      'video_packets_identical': True, 'timestamps_identical': True,
                      'codec_parameters_identical': True}
        self.save()

    def save(self):
        (self.root/'recordings_manifest.json').write_text(json.dumps(
            {'groups': [{'recordings': [self.entry]}]}))
        (self.root/'audio_removal_verification.json').write_text(json.dumps(
            {'recordings': [self.proof]}))

    def test_original_does_not_require_derivative_mapping(self):
        self.source.write_bytes(b'original container')
        (self.root/'recordings_manifest.json').unlink()
        result = verify_recording(self.root, self.source, self.original)
        self.assertEqual(result['input_representation'], 'original')
        self.assertEqual(result['input_container_sha256'], self.original)

    def test_silent_derivative_keeps_both_hashes(self):
        result = verify_recording(self.root, self.source, self.original)
        self.assertEqual(result['input_representation'], 'silent-video-copy')
        self.assertEqual(result['capture_sha256'], self.original)
        self.assertEqual(result['input_container_sha256'], self.actual)

    def test_changed_file_is_rejected(self):
        self.source.write_bytes(b'tampered silent container')
        with self.assertRaises(ValueError):
            verify_recording(self.root, self.source, self.original)

    def test_wrong_capture_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_recording(self.root, self.source, '0'*64)

    def test_wrong_path_is_rejected(self):
        wrong = self.root/'different.mov'
        wrong.write_bytes(self.source.read_bytes())
        with self.assertRaises(ValueError):
            verify_recording(self.root, wrong, self.original)

    def test_unverified_timing_is_rejected(self):
        self.proof['timestamps_identical'] = False
        self.save()
        with self.assertRaises(ValueError):
            verify_recording(self.root, self.source, self.original)


if __name__ == '__main__':
    unittest.main()
