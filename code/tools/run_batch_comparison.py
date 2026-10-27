"""Run the existing comparison CLI for every recording in the receiver manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter

import run_recording_comparison


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT/'data/analysis/receiver_layers_2026-10-24/manifest.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('physical', 'modeled', 'both'), default='both')
    parser.add_argument('--seed', type=int, default=20261027)
    parser.add_argument('--trials', type=int, default=200)
    parser.add_argument('--random-payload', action='store_true')
    args = parser.parse_args(argv)
    if args.trials < 1 or args.seed < 0:
        parser.error('Require positive trials and a nonnegative seed.')

    started = perf_counter()
    recordings = json.loads(MANIFEST.read_text())
    names = [re.sub(r'[^A-Za-z0-9_-]+', '_', v['id']).strip('_') or 'recording'
             for v in recordings]
    failures = []
    for index, (video, folder) in enumerate(zip(recordings, names), start=1):
        recording = video['id']
        if names.count(folder) > 1:
            folder += '_'+hashlib.sha256(recording.encode()).hexdigest()[:8]
        output = ROOT/'data/comparison/batch_results'/folder
        command = ['--recording', recording, '--output', str(output),
                   '--mode', args.mode, '--seed', str(args.seed), '--trials', str(args.trials)]
        if args.random_payload:
            command.append('--random-payload')
        print(f'\n[{index}/{len(recordings)}] Comparing {recording} → {output}', flush=True)
        try:
            # All decoding, scoring and output creation stay in the single-run CLI.
            run_recording_comparison.main(command)
        except SystemExit as exc:
            if exc.code not in (None, 0):
                failures.append(recording)
                print(f'Comparison failed for {recording}; continuing with the next recording.', flush=True)

    print(f'Total batch runtime: {perf_counter()-started:.2f} seconds', flush=True)
    if failures:
        parser.exit(1, 'Failed recordings: '+', '.join(failures)+'\n')
    print(f'Batch complete: {len(recordings)} recordings saved under {ROOT/"data/comparison/batch_results"}', flush=True)


if __name__ == '__main__':
    main()
