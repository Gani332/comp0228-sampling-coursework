"""Three retained repeat recordings with a timed single-sweep cue.

Shares the existing batch lock and sequence allocator. Earlier B01--B03 plans
and captures remain untouched. No serial connection is opened on import.
"""
import html
import json
import math
import time
from pathlib import Path
from IPython.display import HTML, display
from .capture import (BodyCue, DATA_DIR, GAP_SECONDS, LABELS, run_batch,
                      batch_attempts, capture_plan)
from .device import ports
from .experiment import _save
from .protocol import make_packet

SWEEP_START_SECONDS = 21.0
SWEEP_DURATION_SECONDS = 1.0


def guided_retakes_plan():
    batches = []
    for original in capture_plan()['batches']:
        batch = dict(original)
        batch['batch_id'] = 'G'+original['batch_id'][1:]
        batch['protocol'] = 'guided_retakes_v1'
        batch['repeats_original_batch'] = original['batch_id']
        batch['packets'] = [dict(p, trial_id=f"{batch['batch_id']}_{i}")
                            for i,p in enumerate(original['packets'],1)]
        batch['video_name'] = f"{batch['batch_id']}_{batch['message']}_SINGLE_SWEEP.MOV"
        batch['planned_interference'] = 'One approximately one-second light pass at 21 seconds after each START acknowledgment. Same light setting, path and direction. Keep source out of camera view of patch.'
        batch['timing_note'] = 'Host cue guidance, not measured physical onset/duration. Retain early, late and missed sweeps and annotate during video review.'
        batches.append(batch)
    return {'version':1, 'protocol':'guided_retakes_v1', 'batches':batches,
            'scope':'Same three batch contents as B01-B03, repeated with one cued side-light sweep per packet and instructions to avoid occlusion. Earlier evidence is retained, not replaced. Not a matched comparison to earlier uncoded recordings.'}


def load_guided_retakes_plan(root):
    plan = guided_retakes_plan()
    path = Path(root)/DATA_DIR/'guided_retakes_plan.json'
    if path.exists():
        if json.loads(path.read_text()) != plan:
            raise ValueError('Saved guided-retakes plan differs. Review it before recording.')
    else:
        _save(path, plan)
    return plan


class SingleSweepCue(BodyCue):
    def __init__(self, packet, bit_ms, display):
        super().__init__(packet, bit_ms, display)
        self.sweep_seen = False
        self.missed_logged = False
        self.schedule = {'basis': 'Seconds after host receipt of START acknowledgment',
                         'start_seconds': SWEEP_START_SECONDS,
                         'end_seconds': SWEEP_START_SECONDS+SWEEP_DURATION_SECONDS,
                         'sweeps_per_transmission': 1,
                         'note': 'Displayed instruction only; actual disturbance must be assessed from video.'}
        if not self.header_end+1 < self.schedule['start_seconds'] < self.schedule['end_seconds'] < self.body_end-1:
            raise ValueError('Sweep window must be inside the coded body, clear of header and guard.')

    def __call__(self, elapsed, line=''):
        if self.start_ack_unix is None:
            self.start_ack_unix = time.time()-elapsed
        begin, end = self.schedule['start_seconds'], self.schedule['end_seconds']
        if elapsed >= end and not self.sweep_seen and not self.missed_logged:
            self.events.append({'phase': 'sweep_cue_missed', 'seconds_after_start_ack': round(elapsed,4)})
            self.missed_logged = True
        countdown = None
        if line.startswith('DONE'):
            phase, message = 'packet_done', 'MESSAGE FINISHED — keep filming. No sweep during the pause.'
        elif elapsed < begin:
            countdown = math.ceil(begin-elapsed)
            phase = 'countdown' if countdown <= 5 else 'steady'
            message = f'SWEEP IN {countdown} — keep the light away from the patch.'
        elif elapsed < end:
            self.sweep_seen = True
            phase, message = 'sweep', 'SWEEP NOW — ONE smooth pass. Do not sweep back.'
        else:
            phase = 'hold'
            message = ('STOP — point the light away. No more sweeps for this message.'
                       if self.sweep_seen else
                       'Cue was missed — keep steady; do not add a late sweep. Keep this recording.')
        changed = phase != self.last_phase
        if changed:
            self.events.append({'phase': phase, 'seconds_after_start_ack': round(elapsed,4)})
            self.last_phase = phase
        if self.display and (changed or elapsed-self.last_display >= .2):
            self.display({'phase': phase, 'message': message,
                          'countdown_seconds': countdown,
                          'remaining_seconds': max(0, math.ceil(self.total-elapsed))})
            self.last_display = elapsed


def cue_html(state):
    phase = state['phase']
    colour = {'sweep':'#166534','countdown':'#92400e','hold':'#1e3a8a',
              'complete':'#166534','error':'#991b1b'}.get(phase,'#243449')
    title = html.escape(state.get('packet', 'Guided recording'))
    count = state.get('countdown_seconds')
    extra = f'<div style="font-size:76px;font-weight:800">{count}</div>' if phase=='countdown' else ''
    remaining = (f'<p style="font-size:18px">{state["remaining_seconds"]} seconds left in this transmission</p>'
                 if 'remaining_seconds' in state else '')
    return HTML(f'<div style="padding:28px;background:{colour};color:white;border-radius:12px">'
                f'<div style="font-size:20px">{title}</div>{extra}'
                f'<p style="font-size:32px;font-weight:700">{html.escape(state["message"])}</p>{remaining}</div>')


def record_guided_batch(batch_id, root=None, port=None, setup=None):
    root = Path(root or Path.cwd()).resolve()
    if not (root/'optical_link').is_dir():
        raise ValueError('Open this notebook from the optical_link project folder.')
    plan = load_guided_retakes_plan(root)
    batch = next((b for b in plan['batches'] if b['batch_id']==batch_id), None)
    if batch is None: raise ValueError('Choose G01, G02 or G03.')
    previous = batch_attempts(root, batch_id)
    seconds = batch['approx_capture_seconds']
    print(f"{batch_id} — {batch['message']} · ONE video · about {seconds//60} min {seconds%60} s")
    print(' → '.join(LABELS[p['codec']] for p in batch['packets']))
    print(f"ONE sweep per method = {len(batch['packets'])} sweeps in this video. Follow the countdown; no extra sweeps.")
    print('Keep filming through every pause. Stop only after BATCH FINISHED.')
    if previous:
        print('A previous attempt exists. It will be retained with its original IDs and logs.')
        answer = input('Start a NEW phone video, then type RETAKE to record again (anything else cancels): ')
        ready = answer.strip() == 'RETAKE'
    else:
        answer = input('Start the phone video, then press Enter here. Type cancel to skip: ')
        ready = not answer.strip()
    if not ready:
        print('Cancelled. Nothing transmitted.')
        return None
    if port is None:
        candidates = [p['port'] for p in ports() if p['vid']==0x303A and p['pid']==0x1001]
        if len(candidates) != 1:
            raise RuntimeError('Cannot identify exactly one ESP32. Stop the phone, check USB, then rerun.')
        port = candidates[0]
    planned_setup = {'phone_model':'iPhone — exact model unreported',
                     'actual_camera_settings':'Not yet verified',
                     'actual_light_strength_distance_path':'Not yet measured; inspect video and operator notes',
                     'operator_instruction':'Fixed camera and exposure if available; same light setting and one-direction pass; avoid occluding patch.'}
    if setup: planned_setup.update(setup)
    cue = display(cue_html({'phase':'connecting','message':'Connecting — keep filming and keep the light away.'}),display_id=True)
    try:
        folder = run_batch(root, plan, batch_id, port, planned_setup,
                           display=lambda state: cue.update(cue_html(state)),
                           retake=bool(previous), cue_factory=SingleSweepCue)
    except (Exception, KeyboardInterrupt):
        cue.update(cue_html({'phase':'error','message':'Stopped. Keep the partial video; logs are saved. Rerun and type RETAKE for a fresh attempt.'}))
        raise
    print('Finished. Record two more seconds, then stop the phone.')
    print('AirDrop the original video without renaming it. Logs and optical IDs were saved automatically.')
    return folder
