"""Hardware-free recording comparison. Physical evidence and modeled grid export separately."""
import argparse
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'code'))
from optical_link.comparison_runner import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording', default='G02', help='Historical manifest ID, prepared screen ID, or prepared recording.json path (default G02).')
    parser.add_argument('--mode', choices=('physical', 'modeled', 'both'), default='both')
    parser.add_argument('--output', type=Path, help='Output base, relative to repository root; a new UTC run directory is always created.')
    parser.add_argument('--simulation', choices=('controlled','residual'), default='controlled', help='controlled: original report noise models; residual: later recording-calibrated replay. Applies to modeled/both.')
    parser.add_argument('--seed', type=int, help='Default: controlled 20261024; residual 20261027.')
    parser.add_argument('--trials', type=int, help='Trials per condition; default controlled 2000, residual 200.')
    parser.add_argument('--random-payload', action='store_true', help='Separately labelled random-byte robustness mode with recorded payload length.')
    args = parser.parse_args(argv)
    if args.seed is None:
        args.seed = 20261024 if args.simulation == 'controlled' else 20261027
    if args.trials is None:
        args.trials = 2000 if args.simulation == 'controlled' else 200
    started = perf_counter()
    try:
        out = run(ROOT, **vars(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Input/run error: {exc}\n')
    finally:
        print(f'Recording comparison runtime: {perf_counter()-started:.2f} seconds', flush=True)
    print('Saved:', out)


if __name__ == '__main__':
    main()
