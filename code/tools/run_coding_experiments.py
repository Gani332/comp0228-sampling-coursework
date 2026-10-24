"""Run a new local synthetic coding study; does not operate hardware."""
import argparse
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--trials', type=int, default=2000)
    args = p.parse_args()
    sys.path.insert(0, str(args.root.resolve()))
    from optical_link.coding_experiments import DEFAULT_CONFIG, run_study
    config = dict(DEFAULT_CONFIG, trials_per_condition=args.trials)
    results = run_study(args.root, args.output, config)
    print(f'Saved {len(results)} conditions to {args.output}; synthetic results only.')


if __name__ == '__main__':
    main()
