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
    parser.add_argument('--recording', default='G02', help='Manifest ID or exact unique known movie basename (default G02).')
    parser.add_argument('--mode', choices=('physical', 'modeled', 'both'), default='both')
    parser.add_argument('--output', type=Path, help='Output base, relative to repository root; a new UTC run directory is always created.')
    parser.add_argument('--seed', type=int, default=20261027)
    parser.add_argument('--trials', type=int, default=200)
    parser.add_argument('--random-payload', action='store_true', help='Separately labelled random-byte robustness mode with recorded payload length.')
    args = parser.parse_args(argv)
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
