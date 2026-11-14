"""Mac display adapter for the campaign; run graphics in a standalone process.

Display-call timestamps are host observations, not measured photon transitions.
"""
import argparse
import json
from pathlib import Path
import signal
import time
from .physical_campaign import DATA, run_session, save
from .screen_transmitter import PygameRenderer


class ScreenTransmitter:
    def __init__(self, port='mac-screen', *, renderer_factory=PygameRenderer,
                 clock=time.perf_counter, sleep=time.sleep):
        self.renderer_factory = renderer_factory
        self.clock, self.sleep = clock, sleep
        self.renderer = None
        self.bit = 0
        self.caption = 'Start phone recording; SPACE to begin; ESC to cancel'

    def __enter__(self):
        self.renderer = self.renderer_factory(fullscreen=False, monitor=0)
        try:
            self.renderer.show(1, self.caption)
            while not self.renderer.events():
                self.sleep(.01)
            return self
        except BaseException:
            self.renderer.close()
            self.renderer = None
            raise

    def __exit__(self, *exc):
        if self.renderer:
            self.renderer.close()
            self.renderer = None

    def display(self, state):
        text = state['text'].replace('LCD', 'PATCH')
        # Short captions fit the existing 1000px renderer; full state is in cue logs.
        if state['state'] == 'active':
            text = 'BLOCK PATCH NOW' if 'BLOCK LCD' in state['text'] else 'UNCOVER LAMP BEAM NOW'
        elif state['state'] == 'clear':
            text = 'PATCH CLEAR / LAMP COVERED - keep filming'
        elif state['state'] == 'ready' and 'next action' in text:
            text = 'GET READY - ' + text.split('next action')[-1]
        elif state['state'] == 'gap':
            text = 'Keep filming; patch clear / lamp covered - next packet in ' + text.split('next packet in ')[-1].split(';')[0]
        self.caption = text.replace('—', '-')
        if self.renderer:
            self.renderer.show(self.bit, self.caption)

    def light(self, white):
        self.bit = int(white)
        self.renderer.show(self.bit, self.caption)

    def wait_until(self, deadline, progress=None, origin=None):
        while self.clock() < deadline:
            self.renderer.events()
            if progress is not None:
                progress(self.clock()-origin)
            self.sleep(min(.005, max(0, deadline-self.clock())))
        self.renderer.events()

    def pause(self, seconds):
        self.wait_until(self.clock()+seconds)

    def transmit(self, packet, bit_ms=200, log_path=None, on_progress=None):
        if not isinstance(bit_ms, int) or not 200 <= bit_ms <= 1000:
            raise ValueError('Bit duration must be an integer from 200 to 1000 ms.')
        period = bit_ms/1000
        bits = ''.join(map(str, packet.bits))
        record = dict(transport='mac_screen', identity='pygame display', bit_ms=bit_ms,
                      payload_hex=packet.payload.hex(), codec=packet.codec, sequence=packet.sequence,
                      transmitted_bits=bits, scheduled_channel_seconds=len(bits)*period,
                      status='started', host_started_unix=time.time(), slots=[], rendering=self.renderer.settings,
                      timing_note='Host display request/completion times; not optical photon times. '
                                  'START_ack cue fields mean host packet epoch for this transport. '
                                  'A 0.2 s black lead preserves the schedule cue offset.')
        path = Path(log_path) if log_path else None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x') as stream:
                json.dump(record, stream)
        epoch = self.clock()
        record['host_epoch_monotonic'] = epoch
        progress = on_progress or (lambda *args: None)
        try:
            self.light(False)
            progress(0, 'START host_epoch')
            for index, bit in enumerate(bits):
                deadline = epoch+.2+index*period
                self.wait_until(deadline, progress, epoch)
                requested = self.clock()
                slot = dict(index=index, bit=int(bit), intended_deadline=deadline,
                            request=requested, completion=None, lateness=requested-deadline)
                record['slots'].append(slot)
                if requested-deadline >= period:
                    raise RuntimeError('Full-slot scheduling overrun; keep this failed attempt.')
                self.bit = int(bit)
                self.renderer.show(self.bit, self.caption)
                slot['completion'] = self.clock()
                if slot['completion']-deadline >= period:
                    raise RuntimeError('Full-slot display overrun; keep this failed attempt.')
                progress(self.clock()-epoch)
            self.wait_until(epoch+.2+len(bits)*period, progress, epoch)
            self.light(False)
            progress(self.clock()-epoch, 'DONE')
            record['status'] = 'controller_completed'
        except BaseException as exc:
            record.update(status='failed_or_interrupted', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            record['host_elapsed_seconds'] = self.clock()-epoch
            if path:
                save(path, record)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--retake', action='store_true')
    args = parser.parse_args()
    def stop(*_):
        raise KeyboardInterrupt('Notebook stopped screen transmitter')
    signal.signal(signal.SIGTERM, stop)
    tx = ScreenTransmitter()
    setup = json.loads((args.root/DATA/'setup.json').read_text())
    if setup.get('transmitter') != 'mac_screen':
        raise ValueError('Run ScreenRecorder.setup() before Mac recordings.')
    folder = run_session(args.root, args.session, 'mac-screen', setup, tx.display,
                         retake=args.retake, transmitter_factory=lambda _: tx, sleep=tx.pause)
    print('STOP PHONE RECORDING. Saved attempt:', folder)


if __name__ == '__main__':
    main()
