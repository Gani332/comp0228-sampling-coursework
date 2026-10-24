"""Reproduce the selected pilot's metrics without using sent data to decode.

Default: use recorded brightness traces. --from-video additionally verifies
movie hashes and re-extracts the measurements using each recorded ROI.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT.parent/'data'
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from optical_link.protocol import GUARD_BITS, PREAMBLE, HEADER_BITS, to_bits
from optical_link.receiver import decode_trace
from optical_link.video import extract_trace


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-video',action='store_true')
    args=parser.parse_args()
    dataset=DATA/'recordings/pilot_2026-10-24/manifest.json'
    manifest=json.loads(dataset.read_text())
    reference={r['trial_id']:r for r in json.loads((DATA/'analysis/pilot_2026-10-24/summary.json').read_text())}
    for trial in manifest['trials']:
        trace=DATA/trial['trace']
        if sha(trace)!=trial['trace_sha256']:
            raise ValueError(f"Trace hash differs: {trial['trial_id']}")
        if args.from_video:
            movie=DATA/trial['video']
            if sha(movie)!=trial['video_sha256']:
                raise ValueError(f"Movie hash differs: {trial['trial_id']}")
            t,y,_=extract_trace(movie,tuple(trial['roi_xywh']))
            stored=np.loadtxt(trace,delimiter=',',skiprows=1)
            np.testing.assert_allclose(t,stored[:,0],atol=1e-6,rtol=0)
            # Different decoder builds can yield small pixel differences. Report
            # them explicitly; final bit/CRC reproduction is checked separately.
            print(trial['trial_id'],'mean absolute trace difference:',float(np.mean(abs(y-stored[:,1]))))
        else:
            t,y=np.loadtxt(trace,delimiter=',',skiprows=1).T
        # Decoding gets no known message or transmitter log.
        received=decode_trace(t,y,bit_ms=trial['bit_ms'])
        # Evaluation begins only after independent decoding.
        tx=json.loads((DATA/trial['transmitter_log']).read_text())
        if (received['codec'],received['sequence']) != (tx['codec'],tx['sequence']):
            raise ValueError('Decoded packet identity does not match the selected log.')
        sent=np.array([int(b) for b in tx['transmitted_bits']],dtype=np.uint8)
        body=sent[GUARD_BITS+len(PREAMBLE)+HEADER_BITS:-GUARD_BITS]
        payload=bytes.fromhex(tx['payload_hex'])
        if len(body)!=len(received['body_bits']) or len(payload)!=len(received['payload']):
            raise ValueError('Received and logged lengths differ; cannot compute aligned BER.')
        measured={'body_channel_bit_errors':int(np.count_nonzero(body!=received['body_bits'])),
                  'payload_bit_errors':int(np.count_nonzero(to_bits(payload)!=to_bits(received['payload']))),
                  'crc_ok':bool(received['crc_ok']),
                  'exact_payload_match':received['payload']==payload,
                  'received_text':received['text']}
        expected=reference[trial['trial_id']]
        for key,value in measured.items():
            if value!=expected[key]:
                raise AssertionError(f"{trial['trial_id']}: {key} changed: {value!r} vs {expected[key]!r}")
        print(f"{trial['trial_id']}: {received['text']!r}; "
              f"payload errors {measured['payload_bit_errors']}/{len(payload)*8}; CRC {received['crc_ok']}")
    print('All six selected pilot outcomes reproduced.')


if __name__=='__main__':
    main()
