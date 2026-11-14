"""Verify a saved controlled simulation and add PNG/SVG graphs."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'code'))
from optical_link.coding_experiments import load_verified
from optical_link.controlled_plots import plot_study

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    args = parser.parse_args()
    _, _, checks = load_verified(ROOT/'code', args.study)
    print('Verified:', checks)
    for name in plot_study(args.study):
        print(args.study/name)
