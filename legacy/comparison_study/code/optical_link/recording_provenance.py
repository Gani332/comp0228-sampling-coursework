"""Verify an original capture or its published, lossless silent derivative.

Frozen study manifests retain original container hashes. The release index maps
those identities to the new file hashes; removing audio changes the container,
but the separately recorded verification proves video packets/timing unchanged.
"""
import hashlib
import json
from pathlib import Path


def verify_recording(data_root, source, original_sha256):
    """Return both capture identity and actual input hash, or fail closed."""
    data_root = Path(data_root).resolve()
    source = Path(source).resolve()
    relative = 'data/' + source.relative_to(data_root).as_posix()
    with source.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'capture_sha256': original_sha256,
              'input_container_sha256': actual,
              'input_representation': 'original'}
    if actual == original_sha256:
        return result
    manifest = json.loads((data_root/'recordings_manifest.json').read_text())
    matches = [v for group in manifest['groups'] for v in group['recordings']
               if v['path'] == relative]
    if len(matches) != 1:
        raise ValueError('No unique published recording mapping: ' + relative)
    entry = matches[0]
    if (entry.get('original_sha256') != original_sha256 or entry['sha256'] != actual
            or entry['bytes'] != source.stat().st_size
            or entry.get('representation') != 'silent-video-copy'):
        raise ValueError('Recording does not match its capture/derivative hashes: ' + relative)
    verification = json.loads((data_root/'audio_removal_verification.json').read_text())
    proofs = [p for p in verification['recordings'] if p['path'] == relative]
    if len(proofs) != 1:
        raise ValueError('No unique video-preservation verification: ' + relative)
    proof = proofs[0]
    if (proof['sha256'] != actual or proof['original_sha256'] != original_sha256
            or proof['audio_streams_after'] != 0
            or proof['video_packets_identical'] is not True
            or proof['timestamps_identical'] is not True
            or proof['codec_parameters_identical'] is not True):
        raise ValueError('Video-preservation verification differs: ' + relative)
    result['input_representation'] = 'silent-video-copy'
    return result
