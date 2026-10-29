"""Prepare sidecar-timed screen capture features without changing raw inputs."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))
from optical_link.screen_recording_comparison import prepare_recording


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True,help='Receiver session directory.')
    p.add_argument('--transmitter',type=Path,required=True,help='Matching Windows session directory or manifest.json; never guessed automatically.')
    p.add_argument('--recording-id',required=True)
    p.add_argument('--reference-roi',nargs=4,type=int,action='append',metavar=('X','Y','W','H'),help='Repeat for two independent regions; otherwise select interactively.')
    args=p.parse_args(argv)
    try:
        result=prepare_recording(ROOT,args.capture,args.transmitter,args.recording_id,args.reference_roi)
    except (ValueError,OSError,KeyError) as exc:
        p.exit(2,f'Preparation error: {exc}\n')
    print('Prepared:',result)
    print(f'Run: python code/tools/run_recording_comparison.py --recording {args.recording_id} --mode physical')


if __name__=='__main__': main()
