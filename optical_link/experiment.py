"""Matched uncoded/repeat3 pilot with recorded cues and automatic log pairing.

No hardware is opened on import. Receiver decoding never receives sent bits.
The cue is a host instruction to the operator, not a measurement of the light.
"""
import hashlib
import json
import math
import random
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .device import Transmitter
from .protocol import GUARD_BITS, PREAMBLE, HEADER_BITS, make_packet, to_bits
from .receiver import decode_trace
from .video import extract_trace, save_trace

DATA_DIR = Path('experiments/repetition_comparison')
FIRMWARE_START_LEAD = .2  # Optical firmware schedules its first slot 200 ms after START.
HEADER_MARGIN = 2.0
SWEEP_WINDOW = 2.0


def _save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
    temporary.replace(path)


def _stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')+'_'+uuid.uuid4().hex[:6]


def _sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def make_plan():
    rng = random.Random(20261024)
    trials = []
    for repeat in range(1, 4):
        block = [(codec, condition) for codec in ('none', 'repeat3') for condition in ('clean', 'noisy')]
        rng.shuffle(block)
        if repeat == 1:
            block.remove(('repeat3', 'clean'))
            block.insert(0, ('repeat3', 'clean'))
        for codec, condition in block:
            i = len(trials)+1
            packet = make_packet('MANUNITED', codec=codec, sequence=39+i)
            trials.append({'trial_id': f'T{i:02d}', 'repeat': repeat, 'codec': codec,
                           'condition': condition, 'message': 'MANUNITED', 'bit_ms': 200,
                           'sequence': 39+i, 'channel_seconds': len(packet.bits)*.2})
    return {'version': 1, 'description': 'Matched MANUNITED none vs repeat3 pilot',
            'order': 'Three randomized blocks; first trial fixed to repeat3/clean as a hardware check.',
            'noise_protocol': 'One gentle light sweep during the two-second visual cue window. Keep the same lamp setting, marked start/end positions, camera, display and room lighting.',
            'scope': 'A controlled single-interference-event-per-packet experiment; not continuous random noise.',
            'trials': trials}


def load_plan(root):
    path = Path(root)/DATA_DIR/'plan.json'
    if not path.exists():
        _save(path, make_plan())
    return json.loads(path.read_text())


def get_trial(plan, trial_id):
    matches = [t for t in plan['trials'] if t['trial_id'] == trial_id]
    if len(matches) != 1:
        raise ValueError('Choose a trial ID shown in the plan.')
    return dict(matches[0])


def attempts(root, trial_id=None):
    records = []
    for path in sorted((Path(root)/DATA_DIR/'attempts').glob('*/trial.json')):
        record = json.loads(path.read_text())
        if trial_id is None or record['trial_id'] == trial_id:
            records.append((path.parent, record))
    return records


def create_attempt(root, plan, trial_id, setup):
    trial = get_trial(plan, trial_id)
    previous = attempts(root)
    used = {r['sequence'] for _, r in previous}
    sequence = trial['sequence']
    if sequence in used:
        # Retakes get new optical IDs and new directories; old failures survive.
        reserved = {t['sequence'] for t in plan['trials']}
        available = [s for s in range(52, 256) if s not in used | reserved]
        if not available:
            raise ValueError('Sequence IDs exhausted. Start a separately named experiment.')
        sequence = available[0]
    trial['sequence'] = sequence
    trial['attempt_id'] = trial_id+'_'+_stamp()
    trial['retake'] = any(r['trial_id'] == trial_id for _, r in previous)
    trial['created_utc'] = datetime.now(timezone.utc).isoformat()
    trial['status'] = 'prepared'
    trial['setup'] = dict(setup)
    trial['planned_interference'] = 'none' if trial['condition']=='clean' else plan['noise_protocol']
    trial['operator_observations'] = ''
    trial['cue_events'] = []
    destination = Path(root)/DATA_DIR/'attempts'/trial['attempt_id']
    _save(destination/'trial.json', trial)
    return destination, trial


class CaptureCue:
    def __init__(self, packet, bit_ms, condition, display=None):
        self.condition = condition
        self.display = display
        self.events = []
        self.last_phase = None
        self.last_display = -float('inf')
        self.start_seconds = FIRMWARE_START_LEAD+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*bit_ms/1000+HEADER_MARGIN
        self.stop_seconds = self.start_seconds+SWEEP_WINDOW
        self.total_seconds = FIRMWARE_START_LEAD+len(packet.bits)*bit_ms/1000
        body_end = FIRMWARE_START_LEAD+(len(packet.bits)-GUARD_BITS)*bit_ms/1000
        if condition == 'noisy' and self.stop_seconds >= body_end:
            raise ValueError('Message body is too short for this interference window.')

    def __call__(self, elapsed, line=''):
        if line.startswith('DONE'):
            phase, message = 'complete', 'FINISHED — keep recording for two more seconds, then stop.'
        elif self.condition == 'clean':
            phase, message = 'steady', 'CLEAN TRIAL — keep the lighting steady throughout.'
        elif elapsed < self.start_seconds:
            phase = 'wait'
            message = f'KEEP CLEAN — start the light sweep in {max(0, math.ceil(self.start_seconds-elapsed))} s.'
        elif elapsed < self.stop_seconds:
            phase, message = 'sweep', 'START LIGHT SWEEP NOW — one gentle sweep.'
        else:
            phase, message = 'stop', 'STOP THE LIGHT SWEEP — keep lighting steady until finished.'
        changed = phase != self.last_phase
        if changed:
            self.events.append({'phase': phase, 'host_seconds_after_start_ack': round(elapsed, 4),
                                'host_time_unix': time.time()})
            self.last_phase = phase
        if self.display and (changed or elapsed-self.last_display >= .5):
            self.display({'phase': phase, 'message': message,
                          'remaining_seconds': max(0, math.ceil(self.total_seconds-elapsed))})
            self.last_display = elapsed


def run_trial(root, plan, trial_id, port, setup, display=None):
    destination, trial = create_attempt(root, plan, trial_id, setup)
    packet = make_packet(trial['message'], trial['codec'], trial['sequence'])
    cue = CaptureCue(packet, trial['bit_ms'], trial['condition'], display)
    trial['cue_schedule'] = {'basis': 'Host receipt of firmware START acknowledgment',
                             'start_seconds': cue.start_seconds if trial['condition']=='noisy' else None,
                             'stop_seconds': cue.stop_seconds if trial['condition']=='noisy' else None,
                             'note': 'Operator guidance only; actual light onset/duration must be checked in the video.'}
    _save(destination/'trial.json', trial)
    print('Attempt:', destination.name, '| sequence:', trial['sequence'], flush=True)
    try:
        with Transmitter(port) as tx:
            tx.transmit(packet, trial['bit_ms'], destination/'tx.json', on_progress=cue)
        trial['status'] = 'controller_completed'
    except BaseException as e:
        trial['status'] = 'transmission_aborted'
        trial['transmission_error'] = str(e)
        raise
    finally:
        trial['cue_events'] = cue.events
        trial['cue_window_displayed'] = any(e['phase']=='sweep' for e in cue.events) if trial['condition']=='noisy' else None
        _save(destination/'trial.json', trial)
    return destination


def attach_video(attempt_dir, source):
    attempt_dir, source = Path(attempt_dir), Path(source).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    trial = json.loads((attempt_dir/'trial.json').read_text())
    if trial['status'] != 'controller_completed':
        raise ValueError('The transmitter did not complete this attempt; retain its failure record.')
    digest = _sha(source)
    for other in attempt_dir.parent.glob('*/trial.json'):
        if other.parent != attempt_dir and json.loads(other.read_text()).get('video_sha256') == digest:
            raise ValueError('This video is already attached to another attempt. Select the new recording.')
    if 'video' in trial and trial['video_sha256'] != digest:
        raise ValueError('Another recording is already attached. Do not replace a trial recording.')
    destination = attempt_dir/('recording'+source.suffix.lower())
    if destination.exists() and _sha(destination) != digest:
        raise ValueError('Existing recording differs; it will not be overwritten.')
    if not destination.exists():
        shutil.copy2(source, destination)
    if _sha(destination) != digest:
        raise ValueError('Copied recording hash differs.')
    trial.update({'video': destination.name, 'video_sha256': digest, 'source_video_name': source.name})
    _save(attempt_dir/'trial.json', trial)
    return destination


def score_trace(times, brightness, tx):
    # Nothing from the sent message is given to the decoder.
    try:
        received = decode_trace(times, brightness, bit_ms=tx['bit_ms'])
    except ValueError as e:
        return {'status': 'decode_failed', 'reason': str(e), 'packet_failed': True,
                'channel_seconds_including_overhead': tx['scheduled_channel_seconds'],
                'payload_bit_errors': None, 'payload_bits_measured': 0,
                'body_channel_bit_errors': None, 'body_channel_bits_measured': 0,
                'correct_delivered_bits': 0, 'crc_valid_delivered_bits': 0}, None
    if (received['sequence'], received['codec']) != (tx['sequence'], tx['codec']):
        return {'status': 'association_error', 'reason': 'Video packet sequence/code does not match this attempt. Select the correct recording.'}, received
    # Sent bits are used only now, for assessment.
    bits = np.array([int(b) for b in tx['transmitted_bits']], dtype=np.uint8)
    body = bits[GUARD_BITS+len(PREAMBLE)+HEADER_BITS:-GUARD_BITS]
    payload = bytes.fromhex(tx['payload_hex'])
    if len(body)!=len(received['body_bits']) or len(payload)!=len(received['payload']):
        return {'status': 'association_error', 'reason': 'Received lengths do not match the transmission log.'}, received
    body_errors = int(np.count_nonzero(body!=received['body_bits']))
    payload_errors = int(np.count_nonzero(to_bits(payload)!=to_bits(received['payload'])))
    exact = received['payload']==payload
    valid = bool(received['crc_ok'])
    seconds = tx['scheduled_channel_seconds']
    metrics = {'status': 'crc_pass' if valid else 'crc_fail', 'packet_failed': not (valid and exact),
               'received_text': received['text'], 'crc_ok': valid, 'exact_payload_match': exact,
               'body_channel_bit_errors': body_errors, 'body_channel_bits_measured': len(body),
               'body_channel_ber': body_errors/len(body),
               'payload_bit_errors': payload_errors, 'payload_bits_measured': len(payload)*8,
               'payload_ber': payload_errors/(len(payload)*8),
               'channel_seconds_including_overhead': seconds,
               'correct_delivered_bits': len(payload)*8*bool(valid and exact),
               'crc_valid_delivered_bits': len(payload)*8*valid,
               'correct_payload_goodput_bps': len(payload)*8*bool(valid and exact)/seconds}
    return metrics, received


def evaluate_attempt(attempt_dir, roi, observations=''):
    attempt_dir = Path(attempt_dir)
    trial = json.loads((attempt_dir/'trial.json').read_text())
    if trial['status'] != 'controller_completed' or 'video' not in trial:
        raise ValueError('Complete a transmission and attach its recording first.')
    video = attempt_dir/trial['video']
    if _sha(video) != trial['video_sha256']:
        raise ValueError('Attached recording changed.')
    output = attempt_dir/'evaluations'/_stamp()
    output.mkdir(parents=True)
    trial['operator_observations'] = observations
    try:
        t, y, metadata = extract_trace(video, roi)
        save_trace(t, y, metadata, output/'brightness')
        tx = json.loads((attempt_dir/'tx.json').read_text())
        metrics, received = score_trace(t, y, tx)
        if received is not None:
            serializable = {k:(v.tolist() if isinstance(v, np.ndarray) else v.hex() if isinstance(v, bytes) else v) for k,v in received.items()}
            _save(output/'receiver.json', serializable)
    except (ValueError, FileNotFoundError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        metrics = {'status': 'analysis_error', 'reason': str(e)}
    metrics.update({'attempt_id': trial['attempt_id'], 'trial_id': trial['trial_id'],
                    'codec': trial['codec'], 'condition': trial['condition'],
                    'roi_xywh': list(roi), 'operator_observations': observations})
    _save(output/'metrics.json', metrics)
    trial['latest_evaluation'] = str(output.relative_to(attempt_dir))
    _save(attempt_dir/'trial.json', trial)
    return metrics, output


def comparison_rows(root):
    groups = {(codec, condition): [] for codec in ('none', 'repeat3') for condition in ('clean', 'noisy')}
    for folder, trial in attempts(root):
        metric = None
        if 'latest_evaluation' in trial:
            metric = json.loads((folder/trial['latest_evaluation']/'metrics.json').read_text())
        groups[(trial['codec'], trial['condition'])].append((trial, metric))
    rows = []
    for (codec, condition), records in groups.items():
        evaluated = [m for _,m in records if m and m['status'] in ('crc_pass','crc_fail','decode_failed')]
        with_ber = [m for m in evaluated if m.get('payload_bit_errors') is not None]
        total_bits = sum(m['payload_bits_measured'] for m in with_ber)
        errors = sum(m['payload_bit_errors'] for m in with_ber)
        seconds = sum(m['channel_seconds_including_overhead'] for m in evaluated)
        rows.append({'codec':codec,'condition':condition,'attempts_started':len(records),
                     'retakes':sum(bool(t['retake']) for t,_ in records),
                     'transmission_aborted':sum(t['status']=='transmission_aborted' for t,_ in records),
                     'awaiting_evaluation':sum(t['status']=='controller_completed' and m is None for t,m in records),
                     'analysis_or_pairing_errors':sum(bool(m) and m['status'] in ('analysis_error','association_error') for _,m in records),
                     'evaluated_packets':len(evaluated),'packets_with_ber':len(with_ber),
                     'packet_failures':sum(m['packet_failed'] for m in evaluated),
                     'packet_failure_rate':sum(m['packet_failed'] for m in evaluated)/len(evaluated) if evaluated else None,
                     'payload_bit_errors':errors,'payload_bits_measured':total_bits,
                     'payload_ber':errors/total_bits if total_bits else None,
                     'correct_payload_goodput_bps':sum(m['correct_delivered_bits'] for m in evaluated)/seconds if seconds else None})
    return rows
