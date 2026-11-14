"""Mac camera recorder; no payload decoder and no codec override."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from optical_link.screen_capture_packet import DEFAULT_OUTPUT, positive, bit_duration


def main(argv=None):
    parser = argparse.ArgumentParser(description='Continuous camera capture. No automatic timeout before first CRC-valid header. Timer starts at detection completion, not estimated optical start. Storage grows while waiting; Q/Escape stops, M manually arms.')
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--bit-ms',type=int,default=200)
    parser.add_argument('--timeout-after-first-seconds',type=float,default=1800)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--session-label')
    parser.add_argument('--camera-backend',choices=['auto','avfoundation','any'],default='auto')
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--height',type=int,default=720)
    parser.add_argument('--fps',type=float,default=30)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args(argv)
    try:
        bit_duration(args.bit_ms)
        positive(args.timeout_after_first_seconds)
        positive(args.fps)
        if args.camera<0 or args.width<=0 or args.height<=0:
            raise ValueError('Camera index and dimensions invalid.')
        if args.output.exists() and not args.output.is_dir():
            raise ValueError('Output must be a directory.')
    except (ValueError,OSError) as exc:
        parser.error(str(exc))
    print(f'Output: {args.output.resolve()} | camera {args.camera} | bit-ms {args.bit_ms} | post-detection budget {args.timeout_after_first_seconds}s')
    print('Match Windows recommended timeout; 1800 seconds may be insufficient for a full maximum-length batch.')
    if not args.dry_run:
        from optical_link.camera_recorder import run_camera
        folder = run_camera(args)
        metadata = json.loads(next(folder.glob('*_capture.json')).read_text(encoding='utf-8'))
        return 0 if metadata['status'] in ('stopped','cancelled') else 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
