"""Ordinary notebook-cell capture, with no widget renderer required."""
import html
from pathlib import Path
from IPython.display import HTML, display

from .device import ports
from .capture import load_capture_plan, batch_attempts, run_batch, LABELS


def record_batch_cell(batch_id, root=None, port=None, setup=None, retake=False):
    root = Path(root or Path.cwd()).resolve()
    if not (root/'optical_link').is_dir():
        raise ValueError('Open this notebook from the optical_link project folder.')
    plan = load_capture_plan(root)
    batch = next((b for b in plan['batches'] if b['batch_id']==batch_id), None)
    if batch is None: raise ValueError('Unknown recording batch.')
    prior = batch_attempts(root,batch_id)
    completed = [(p,r) for p,r in prior if r['status']=='controller_completed']
    if completed and not retake:
        print(f'{batch_id} — {batch["message"]} already transmitted. This cell has not sent it again.')
        print('Keep the original phone video. A deliberate retake can be requested separately.')
        return completed[-1][0]
    print(f'{batch_id} — {batch["message"]}: '+ ' → '.join(LABELS[p['codec']] for p in batch['packets']))
    seconds=batch['approx_capture_seconds']
    print(f'One continuous phone video, approximately {seconds//60} min {seconds%60} s.')
    print('Keep recording between methods. Stop only after BATCH FINISHED.')
    answer=input('Start your iPhone recording, then press Enter here to begin. Type cancel to skip: ')
    if answer.strip():
        print('Skipped. No transmission started.')
        return None
    if port is None:
        candidates=[p['port'] for p in ports() if p['vid']==0x303A and p['pid']==0x1001]
        if len(candidates)!=1:
            raise RuntimeError('Could not select exactly one ESP32. Stop the phone, check its USB connection, and rerun this cell.')
        port=candidates[0]
    if setup is None:
        setup={'phone_model':'iPhone — exact model unreported', 'distance_cm':None,
               'camera_mode_fps_and_exposure_lock':'', 'room_lighting':'',
               'lamp_setting_and_movement':'', 'notes':''}
    cue=display(HTML('<div style="padding:20px;background:#fff3cd;color:#111;font-size:24px">Connecting — keep the camera and lighting steady.</div>'),display_id=True)
    def show(state):
        phase=state['phase']
        message=state['message']
        if phase=='body':
            message='DO A LIGHT SWEEP NOW — roughly following this cue is fine. Then keep lighting steady.'
        colour={'body':'#fff3cd','complete':'#dcfce7','header':'#e7f1ff','gap':'#e7f1ff'}.get(phase,'#f1f5f9')
        title=html.escape(state.get('packet',batch['message']))
        remaining=f'<br><small>{state["remaining_seconds"]} seconds remaining in this message</small>' if 'remaining_seconds' in state else ''
        cue.update(HTML(f'<div style="padding:20px;background:{colour};color:#111;font-size:24px"><b>{title}</b><br>{html.escape(message)}{remaining}</div>'))
    try:
        folder=run_batch(root,plan,batch_id,port,setup,display=show,retake=retake)
    except (Exception,KeyboardInterrupt):
        cue.update(HTML('<div style="padding:20px;background:#ffe2e2;color:#111"><b>Stopped before completion.</b> Stop your iPhone and keep the partial video. Transmission logs have been retained.</div>'))
        raise
    print('Finished. Stop the iPhone after two more seconds. Logs are saved automatically.')
    print('Keep the video’s original filename. I will organise it after AirDrop.')
    return folder
