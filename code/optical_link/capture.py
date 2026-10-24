"""Three continuous recordings covering the 11 missing method/message cases.

Imports, plan inspection and notebook Run All never open serial. Only explicit
operator action calls run_batch. Raw videos are retained for later evaluation.
"""
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

from .device import Transmitter
from .experiment import _save, _stamp, _sha
from .protocol import make_packet, GUARD_BITS, PREAMBLE, HEADER_BITS

DATA_DIR = Path('experiments/final_capture_v1')
LEAD_SECONDS = .2
GAP_SECONDS = 8
LABELS = {'repeat3': 'Repeat 3', 'repeat5': 'Repeat 5',
          'hamming74': 'Hamming (7,4)', 'rs4': 'Reed–Solomon (4 parity bytes)'}


def capture_plan():
    # Existing noisy cells: uncoded MANUNITED/ADRIAN/OMAR and repeat3 MANUNITED.
    # Orders frozen before collecting new outcomes. Three cases, not replicates.
    specs = [('B01', 'MANUNITED', ['repeat5', 'hamming74', 'rs4']),
             ('B02', 'ADRIAN', ['rs4', 'repeat3', 'hamming74', 'repeat5']),
             ('B03', 'OMAR', ['hamming74', 'repeat5', 'rs4', 'repeat3'])]
    batches = []
    number = 0
    for batch_id, message, codecs in specs:
        packets = []
        for codec in codecs:
            number += 1
            p = make_packet(message, codec)
            packets.append({'trial_id': f'R{number:02d}', 'message': message,
                            'codec': codec, 'bit_ms': 200,
                            'channel_seconds': len(p.bits)*.2})
        total = sum(p['channel_seconds'] for p in packets)
        batches.append({'batch_id': batch_id, 'message': message, 'packets': packets,
                        'video_name': f'{batch_id}_{message}_NOISY.MOV',
                        'channel_seconds': round(total, 1),
                        'approx_capture_seconds': math.ceil(total+GAP_SECONDS*(len(packets)-1)+8)})
    return {'version': 1, 'group_size': 4, 'batches': batches,
            'condition': 'Physical disturbance during each message body; onset is flexible.',
            'scope': 'Same-message/noise-category comparison; historical conditions are not proved identical.',
            'receiver_evaluation': 'Use previous videos for development; keep these new videos for frozen-receiver evaluation.'}


def load_capture_plan(root):
    path = Path(root)/DATA_DIR/'plan.json'
    plan = capture_plan()  # Also checks RS dependency and all packet lengths.
    if path.exists():
        if json.loads(path.read_text()) != plan:
            raise ValueError('Saved capture plan differs from this software. Preserve it and review before sending.')
    else:
        _save(path, plan)
    return plan


def batch_attempts(root, batch_id=None):
    result = []
    for p in sorted((Path(root)/DATA_DIR/'batches').glob('*/batch.json')):
        r = json.loads(p.read_text())
        if batch_id is None or r['batch_id'] == batch_id:
            result.append((p.parent, r))
    return result


def _used_sequences(root):
    used = {250}  # Reserved for the earlier controller-only bench check.
    root = Path(root)
    for p in (root/'experiments').rglob('*.json'):
        if p.name not in ('trial.json', 'tx.json', 'batch.json'):
            continue
        d = json.loads(p.read_text())
        if isinstance(d.get('sequence'), int): used.add(d['sequence'])
        used.update(x['sequence'] for x in d.get('packets', []) if 'sequence' in x)
    for p in (root/'results').glob('*_tx.json'):
        d = json.loads(p.read_text())
        if isinstance(d.get('sequence'), int): used.add(d['sequence'])
    return used


def new_batch_attempt(root, batch, setup, retake=False):
    previous = batch_attempts(root, batch['batch_id'])
    if any(r['status'] == 'controller_completed' for _, r in previous) and not retake:
        raise ValueError('This batch already completed. Attach its video, or explicitly enable a retained retake.')
    used = _used_sequences(root)
    available = [n for n in range(64, 250) if n not in used]
    if len(available) < len(batch['packets']):
        raise ValueError('Unique optical IDs exhausted; no transmission started.')
    record = dict(batch, setup=dict(setup), attempt_id=batch['batch_id']+'_'+_stamp(),
                  status='prepared', retake=bool(previous), events=[],
                  condition='noisy', actual_observations='',
                  association_status='awaiting_video', created_unix=time.time())
    record['packets'] = [dict(p, sequence=s, status='not_started')
                         for p, s in zip(batch['packets'], available)]
    destination = Path(root)/DATA_DIR/'batches'/record['attempt_id']
    _save(destination/'batch.json', record)
    return destination, record


class BodyCue:
    """A broad body window; there is intentionally no prescribed sweep instant."""
    def __init__(self, packet, bit_ms, display):
        self.display = display
        self.events = []
        self.last_phase = None
        self.last_display = -float('inf')
        self.header_end = LEAD_SECONDS+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*bit_ms/1000
        self.body_end = LEAD_SECONDS+(len(packet.bits)-GUARD_BITS)*bit_ms/1000
        self.total = LEAD_SECONDS+len(packet.bits)*bit_ms/1000
        self.start_ack_unix = None

    def __call__(self, elapsed, line=''):
        if self.start_ack_unix is None: self.start_ack_unix = time.time()-elapsed
        if line.startswith('DONE'):
            phase, message = 'packet_done', 'Message finished — keep recording and return to steady lighting.'
        elif elapsed < self.header_end+.5:
            phase, message = 'header', 'KEEP STEADY — acquiring this message’s header.'
        elif elapsed < self.body_end:
            phase, message = 'body', 'MESSAGE BODY — introduce comparable light disturbance when you choose.'
        else:
            phase, message = 'ending', 'KEEP STEADY — this message is ending.'
        changed = phase != self.last_phase
        if changed:
            self.events.append({'phase': phase, 'seconds_after_start_ack': round(elapsed, 4)})
            self.last_phase = phase
        if self.display and (changed or elapsed-self.last_display >= .5):
            self.display({'phase': phase, 'message': message,
                          'remaining_seconds': max(0, math.ceil(self.total-elapsed))})
            self.last_display = elapsed


def run_batch(root, plan, batch_id, port, setup, display=None, retake=False, cue_factory=BodyCue):
    # Two notebook kernels must not allocate IDs or use the controller together.
    import fcntl
    lock_path = Path(root)/DATA_DIR/'capture.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another capture is running in this project. Wait or interrupt that notebook.') from exc
        return _run_batch(root, plan, batch_id, port, setup, display, retake, cue_factory)


def _run_batch(root, plan, batch_id, port, setup, display=None, retake=False, cue_factory=BodyCue):
    """Send one explicit operator-selected batch; preserve every partial attempt."""
    batch = next((b for b in plan['batches'] if b['batch_id'] == batch_id), None)
    if batch is None: raise ValueError('Unknown batch ID.')
    destination, record = new_batch_attempt(root, batch, setup, retake)
    def show(state):
        if display: display(state)
    try:
        show({'phase': 'connecting', 'message': 'Connecting — keep recording and keep lighting steady.'})
        with Transmitter(port) as tx:
            record['identity'] = tx.identity
            for i, trial in enumerate(record['packets']):
                if i:
                    for remaining in range(GAP_SECONDS, 0, -1):
                        show({'phase': 'gap', 'message': f'KEEP RECORDING — next message in {remaining} s. Keep lighting steady.'})
                        time.sleep(1)
                p = make_packet(trial['message'], trial['codec'], trial['sequence'])
                def packet_display(state, trial=trial, i=i):
                    show(dict(state, packet=f"{i+1}/{len(record['packets'])}: {LABELS[trial['codec']]}",
                              sequence=trial['sequence']))
                cue = cue_factory(p, trial['bit_ms'], packet_display)
                if hasattr(cue, 'schedule'):
                    trial['planned_sweep_schedule'] = cue.schedule
                trial['status'] = 'sending'
                trial['tx_log'] = f"{trial['trial_id']}/tx.json"
                _save(destination/'batch.json', record)
                try:
                    tx.transmit(p, trial['bit_ms'], destination/trial['tx_log'], on_progress=cue)
                    trial['status'] = 'controller_completed'
                except BaseException as exc:
                    trial['status'] = 'failed_or_interrupted'
                    trial['error'] = type(exc).__name__+': '+str(exc)
                    raise
                finally:
                    trial['start_ack_unix'] = cue.start_ack_unix
                    trial['cue_events'] = cue.events
                    trial['host_finished_unix'] = time.time()
                    _save(destination/'batch.json', record)
        record['status'] = 'controller_completed'
    except BaseException as exc:
        record['status'] = 'interrupted'
        record['error'] = type(exc).__name__+': '+str(exc)
        raise
    finally:
        record['host_finished_unix'] = time.time()
        _save(destination/'batch.json', record)
    show({'phase': 'complete', 'message': 'BATCH FINISHED — record two more seconds, then stop your iPhone.',
          'video_name': record['video_name']})
    return destination


def attach_batch_video(attempt_dir, source, observations=''):
    """Preserve original recording; optical packet association remains unverified."""
    folder, source = Path(attempt_dir), Path(source).expanduser().resolve()
    if not source.is_file(): raise FileNotFoundError(source)
    record = json.loads((folder/'batch.json').read_text())
    if not any(p['status'] == 'controller_completed' for p in record['packets']):
        raise ValueError('No completed message in this attempt; retain the log as a setup failure.')
    digest = _sha(source)
    for p in folder.parent.glob('*/batch.json'):
        if p.parent != folder and json.loads(p.read_text()).get('video_sha256') == digest:
            raise ValueError('This video is already attached to another batch attempt.')
    if record.get('video_sha256') and record['video_sha256'] != digest:
        raise ValueError('A different video is already attached. Existing evidence will not be overwritten.')
    meta = json.loads(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
         'stream=width,height,avg_frame_rate:format=duration', '-of', 'json', str(source)], timeout=60))
    if not meta.get('streams'): raise ValueError('No video stream found.')
    duration = float(meta['format']['duration'])
    # A short clip is retained but flagged, never silently treated as a full batch.
    expected = record['channel_seconds']+GAP_SECONDS*(len(record['packets'])-1)
    destination = folder/('recording'+source.suffix.lower())
    if destination.exists() and _sha(destination) != digest: raise ValueError('Destination differs.')
    if not destination.exists(): shutil.copy2(source, destination)
    if _sha(destination) != digest: raise IOError('Copied video hash mismatch.')
    record.update(video=destination.name, video_sha256=digest, source_video_name=source.name,
                  video_metadata=meta, actual_observations=observations,
                  capture_duration_warning=duration < expected-1,
                  association_status='video_attached; optical IDs and packet windows not yet verified')
    record.setdefault('observation_history', []).append({'saved_unix': time.time(), 'text': observations})
    _save(folder/'batch.json', record)
    return destination


def capture_status(root, plan):
    rows = []
    for batch in plan['batches']:
        records = batch_attempts(root, batch['batch_id'])
        last = records[-1] if records else None
        rows.append({'batch': batch['batch_id'], 'message': batch['message'],
                     'transmissions': len(batch['packets']), 'attempts': len(records),
                     'latest_status': last[1]['status'] if last else 'not_started',
                     'video_saved': bool(last and last[1].get('video')),
                     'attempt_dir': str(last[0]) if last else None})
    return rows
