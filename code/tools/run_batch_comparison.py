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
    parser.add_argument('--source', choices=('historical', 'screen', 'all'), default='historical', help='Screen scans data/screen/prepared; raw captures must be prepared first.')
    parser.add_argument('--output', type=Path, help='Output root; each recording gets its own folder and unique run.')
    parser.add_argument('--mode', choices=('physical', 'modeled', 'both'), default='both')
    parser.add_argument('--simulation', choices=('controlled','residual'), default='controlled', help='Original controlled study (once per batch), or later per-recording residual replay.')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--trials', type=int)
    parser.add_argument('--random-payload', action='store_true')
    args = parser.parse_args(argv)
    if args.seed is None:
        args.seed = 20261024 if args.simulation == 'controlled' else 20261027
    if args.trials is None:
        args.trials = 2000 if args.simulation == 'controlled' else 200
    if args.random_payload and args.simulation == 'controlled' and args.mode != 'physical':
        parser.error('Controlled simulation already uses original random nine-byte payloads; --random-payload is residual-only.')
    if args.trials < 1 or args.seed < 0:
        parser.error('Require positive trials and a nonnegative seed.')

    started = perf_counter()
    recordings = json.loads(MANIFEST.read_text()) if args.source in ('historical','all') else []
    if args.source in ('screen','all'):
        recordings += [dict(id=json.loads(p.read_text())['id'], screen_path=str(p))
                       for p in sorted((ROOT/'data/screen/prepared').glob('*/recording.json'))]
    if not recordings and not (args.simulation == 'controlled' and args.mode == 'modeled'):
        parser.error('No prepared recordings found. Run prepare_screen_recording.py first.')
    names = [re.sub(r'[^A-Za-z0-9_-]+', '_', v['id']).strip('_') or 'recording'
             for v in recordings]
    failures = []
    physical_only = args.simulation == 'controlled' and args.mode in ('both','modeled')
    selected = [] if physical_only and args.mode == 'modeled' else recordings
    for index, (video, folder) in enumerate(zip(selected, names), start=1):
        recording = video.get('screen_path',video['id'])
        if names.count(folder) > 1:
            folder += '_'+hashlib.sha256(recording.encode()).hexdigest()[:8]
        base = args.output if args.output else ROOT/('data/screen/batch_results' if 'screen_path' in video else 'data/comparison/batch_results')
        output = base/folder
        command = ['--recording', recording, '--output', str(output),
                   '--mode', 'physical' if physical_only else args.mode, '--simulation', args.simulation, '--seed', str(args.seed), '--trials', str(args.trials)]
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

    if physical_only:
        from optical_link.controlled_comparison import run_controlled
        from optical_link.screen_capture_packet import identifier
        base = args.output if args.output else ROOT/('data/screen/batch_results' if args.source == 'screen' else 'data/comparison/batch_results')
        simulation_output = ROOT/base/'controlled_simulation'/identifier()
        run_controlled(ROOT,simulation_output,seed=args.seed,trials=args.trials)
        print('Shared controlled simulation saved:',simulation_output,flush=True)

    print(f'Total batch runtime: {perf_counter()-started:.2f} seconds', flush=True)
    if failures:
        parser.exit(1, 'Failed recordings: '+', '.join(failures)+'\n')
    print(f'Batch complete: {len(recordings)} recordings. Output paths printed above.', flush=True)


if __name__ == '__main__':
    main()
