"""Windows single-screen transmission CLI and shared batch entry point."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from optical_link.protocol import CODECS
from optical_link.screen_capture_packet import (DEFAULT_OUTPUT, prepare, batch_plan, duration,
                                                positive, bit_duration, new_session)
from optical_link.screen_transmitter import run_session


def main(batch=False, argv=None):
    parser = argparse.ArgumentParser(description='Screen transmitter. Calibration waits for SPACE. Host completion does not prove reception.')
    parser.add_argument('--message',required=True)
    if not batch:
        parser.add_argument('--codec',required=True,choices=CODECS)
        parser.add_argument('--interleaving',choices=['off','on'],default='off')
    parser.add_argument('--sequence',type=int,default=1,help='First sequence ID (batch reserves ten).')
    parser.add_argument('--bit-ms',type=int,default=200)
    parser.add_argument('--countdown-seconds',type=float,default=5)
    parser.add_argument('--gap-seconds',type=float,default=8)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--session-label')
    parser.add_argument('--fullscreen',action='store_true')
    parser.add_argument('--monitor',type=int,default=0)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args(argv)
    try:
        bit_duration(args.bit_ms)
        positive(args.countdown_seconds)
        positive(args.gap_seconds)
        if args.monitor < 0:
            raise ValueError('Monitor must be nonnegative.')
        if args.output.exists() and not args.output.is_dir():
            raise ValueError('Output must be a directory.')
        plan = batch_plan(args.message,args.bit_ms,args.sequence) if batch else [prepare(args.message,args.codec,args.sequence,args.interleaving=='on',args.bit_ms)]
        estimate = duration(plan,args.gap_seconds,args.countdown_seconds)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f'Output root: {args.output.resolve()} | bit-ms: {args.bit_ms}')
    for i,p in enumerate(plan,1):
        print(f'{i:02d} seq={p.packet.sequence} {p.packet.codec} interleaving={p.depth!=1} depth={p.depth} bits={len(p.wire_bits)}')
    print(estimate)
    print('Set Mac --timeout-after-first-seconds to at least',estimate['recommended_timeout_after_first_seconds'])
    if args.dry_run:
        return 0
    folder = new_session(args.output,'transmitter',args.message)
    print('Session:',folder)
    result = run_session(plan,folder,args.gap_seconds,args.countdown_seconds,args.session_label,
                         fullscreen=args.fullscreen,monitor=args.monitor)
    return 0 if result['status']=='completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
