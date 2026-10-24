"""Generate the controlled repetition-comparison walkthrough. No hardware actions."""
from pathlib import Path
import textwrap
import nbformat as nbf
ROOT=Path(__file__).resolve().parents[1]
cells=[]
def md(s):cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(s).strip()))
def code(s):cells.append(nbf.v4.new_code_cell(textwrap.dedent(s).strip()))
md('''
# Does repetition make our optical link more reliable?
### COMP0228 · First controlled coding comparison

**Goal:** compare uncoded and repetition-3 transmissions of **MANUNITED**, using
200 ms bit slots, under clean conditions and one defined light disturbance.

```text
Choose a planned trial → start phone recording → transmit with a visual cue
    → attach that recording → decode independently → measure and compare
```

The six earlier recordings remain our exploratory pilot. This new experiment uses
matched messages and settings. The plan has **12 trials**: 2 coding methods ×
2 conditions × 3 repeats. This is an initial comparison, not a precise final
performance estimate. First trial: **T01, repeat3, clean, 72 seconds**.

No firmware update is required. A fresh Run All does **not** open the transmitter
or flash the screen. The transmit switch starts False and resets to False when
used. The original Optical_Link_Guided notebook is preserved.
''')
md('''
## 1 · Load the project and experiment plan

Open this notebook from the optical-link project folder. Use your working Python
kernel; restart it if you have imported an older version of the helpers.
If a package is missing, run `%pip install -r requirements.txt` in a separate cell.
FFprobe must also be available. Creating the plan only writes local bookkeeping.
''')
code(r'''
from pathlib import Path
import json, math, html
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from IPython.display import display, HTML
from optical_link.device import ports
from optical_link.protocol import make_packet
from optical_link.video import preview
from optical_link.experiment import (
    load_plan, get_trial, attempts, run_trial, attach_video,
    evaluate_attempt, comparison_rows, CaptureCue, DATA_DIR
)
ROOT = Path.cwd().resolve()
assert (ROOT/'optical_link').is_dir(), 'Open the notebook from the project folder.'
plan = load_plan(ROOT)

def show_table(rows, columns):
    def cell(v):
        if v is None: return '—'
        if isinstance(v, float): return f'{v:.4g}'
        return str(v)
    header = ''.join('<th style="padding:7px;text-align:left">'+html.escape(c.replace('_',' '))+'</th>' for c in columns)
    body = ''.join('<tr>'+''.join('<td style="padding:7px;border-top:1px solid #ddd">'+html.escape(cell(r.get(c)))+'</td>' for c in columns)+'</tr>' for r in rows)
    display(HTML('<table>'+header+body+'</table>'))

show_table(plan['trials'], ['trial_id','repeat','codec','condition','message','sequence','channel_seconds'])
print('Available serial ports:', ports())
print('Plan saved in:', ROOT/DATA_DIR/'plan.json')
''')
md('''
## 2 · Fix the setup and choose one trial

Keep phone position, focus/exposure settings, display position and room lighting
constant. Choose a lamp setting and mark the start/end positions of a gentle
sweep so you can repeat it. Record the details below; do not invent measurements.

- **Clean:** leave the lighting steady for the entire transmission.
- **Noisy:** keep the start/header clean, make **one light sweep during the
  two-second visual cue**, then return to steady lighting.

The cue is timed from the firmware's START acknowledgment. At 200 ms/bit it begins
about **19.8 seconds after that acknowledgment**, including a two-second margin
past the header. Do not time it from when the phone starts recording.
The notebook records cue times; these are instructions to you, not proof of when
or how strongly the light actually moved. Note deviations after the recording.

This tests **one interference event per packet**. It is not a constant-noise-rate
experiment: coded packets last longer. State this scope in the report.
''')
code(r'''
PORT = '/dev/cu.usbmodem101'
TRIAL_ID = 'T01'  # Follow the saved order: T01 through T12.
SETUP = {
    'phone_model': '',
    'distance_cm': None,
    'camera_mode': 'Record the actual resolution/fps and focus/exposure setting',
    'room_lighting': '',
    'lamp_setting_and_marked_sweep_positions': '',
    'notes': '',
}
trial = get_trial(plan, TRIAL_ID)
packet = make_packet(trial['message'], trial['codec'], trial['sequence'])
cue_preview = CaptureCue(packet, trial['bit_ms'], trial['condition'])
print(f"{TRIAL_ID}: {trial['codec']} | {trial['condition']} | {trial['message']}")
print(f"Scheduled channel duration: {trial['channel_seconds']:.1f} seconds")
if trial['condition'] == 'noisy':
    print(f'Follow the on-screen cue: one sweep from approximately {cue_preview.start_seconds:.1f} to {cue_preview.stop_seconds:.1f} seconds after START acknowledgment.')
else:
    print('This is CLEAN: do not introduce the light disturbance.')
prior = attempts(ROOT, TRIAL_ID)
print('Previous attempts for this trial:', len(prior))
if prior:
    print('Sending again creates a retained retake with a new sequence number; it does not overwrite an earlier attempt.')
''')
md('''
## 3 · Start the phone, then transmit

**For T01, record the full 72-second clean transmission.** Start the phone first,
then set RUN_TRANSMISSION=True in the short arming cell below and run it,
then run the transmission cell beneath it. The large cue updates while the
controller transmits. The transmission cell consumes the switch: rerunning that
cell alone will not send again. Rerunning the arming cell with True (or Run All
while it contains True) enables another attempt. On a noisy trial, wait for **START LIGHT SWEEP NOW**, then stop when
instructed. Keep recording for two seconds after FINISHED.

Connecting should last only a few seconds. The host uploads long commands in small
chunks and reports an error if START is not acknowledged within three seconds of
upload. Restart the kernel after updating the project helpers.

The program saves a separate folder for every attempt, including aborted ones.
A fresh optical sequence number on each retake helps detect a mismatched video.
The eight-bit sequence ID is limited; this notebook refuses to reuse exhausted IDs.
''')
code(r'''
RUN_TRANSMISSION = False  # Set True and run this short cell only when ready to send.
''')
code(r'''
attempt_dir = None
if RUN_TRANSMISSION:
    RUN_TRANSMISSION = False  # One-shot: consciously re-enable for another send.
    cue_display = display(HTML('<div style="padding:18px;background:#fff3cd;font-size:23px">Connecting — keep the scene steady.</div>'), display_id=True)
    def show_cue(state):
        colours = {'wait':'#fff3cd', 'steady':'#e7f1ff', 'sweep':'#ffe2e2', 'stop':'#e7f1ff', 'complete':'#dcfce7'}
        message = html.escape(state['message'])
        cue_display.update(HTML(f'<div style="padding:18px;background:{colours[state["phase"]]};color:#111;font-size:23px"><strong>{message}</strong><br><small>Approximately {state["remaining_seconds"]} seconds remaining</small></div>'))
    try:
        attempt_dir = run_trial(ROOT, plan, TRIAL_ID, PORT, SETUP, display=show_cue)
        print('Saved transmission and cue record:', attempt_dir)
    except (Exception, KeyboardInterrupt) as e:
        cue_display.update(HTML('<div style="padding:18px;background:#ffe2e2">Transmission did not complete. The attempt is retained; inspect the error below.</div>'))
        print(type(e).__name__+':', e)
        previous = attempts(ROOT, TRIAL_ID)
        attempt_dir = previous[-1][0] if previous else None
else:
    previous = attempts(ROOT, TRIAL_ID)
    attempt_dir = previous[-1][0] if previous else None
    print('No transmission started. Start phone recording before enabling this cell.')
    if attempt_dir: print('Latest saved attempt for this trial:', attempt_dir)
''')
md('''
## 4 · Attach the recording and check its ROI

AirDrop the original video to the Mac. Put its path in VIDEO_SOURCE. The code
copies it into this attempt's folder, hashes it and keeps the original file.
Do not reuse a clean/uncoded video for a new coded trial. Repetition protection
must have been transmitted physically. The header's sequence/code are checked
against the automatically linked transmission log during decoding.

If you reopen the notebook later, select the same TRIAL_ID and run the disabled
transmission cell to locate its latest attempt. For a specific earlier retake,
set REVIEW_ATTEMPT explicitly to the printed attempt-folder path.
''')
code(r'''
REVIEW_ATTEMPT = attempt_dir  # Or Path('.../experiments/repetition_comparison/attempts/T01_...')
VIDEO_SOURCE = None          # Example: Path.home() / 'Downloads' / 'IMG_1234.MOV'
PREVIEW_FRAME = 150
local_video = None
if REVIEW_ATTEMPT is not None and VIDEO_SOURCE is not None:
    local_video = attach_video(REVIEW_ATTEMPT, VIDEO_SOURCE)
    frame = preview(local_video, frame=PREVIEW_FRAME)
    fig, ax = plt.subplots(figsize=(10,6))
    ax.imshow(frame)
    ax.set(xlabel='x (stored pixels)', ylabel='y (stored pixels)', title='Select a box inside the flashing patch')
    plt.show()
    print('Local recording:', local_video)
else:
    print('Select the completed attempt and its original phone recording.')
''')
code(r'''
ROI = (1050, 300, 150, 150)  # Previous setup only: confirm against THIS preview.
if local_video is not None:
    fig, ax = plt.subplots(figsize=(10,6))
    ax.imshow(frame)
    ax.add_patch(Rectangle(ROI[:2], ROI[2], ROI[3], fill=False, ec='lime', lw=2))
    ax.set_title('Confirm this box stays inside the patch for the entire recording')
    plt.show()
''')
md('''
## 5 · Decode and score this attempt

Choose the ROI from the video before inspecting decoding success; keep the
selection procedure consistent across methods. Enter what actually happened,
including early/late sweeps, unexpected lighting changes or a moved camera.

There is **no manual TX_LOG selection**. The attempt folder contains its own
transmission log. The receiver sees only camera measurements and the public bit
duration. Sent bits are used afterwards to calculate errors.

For repetition-3, three consecutive received bits vote on one original bit:
`101 → 1`. One error per triplet is repairable; two can produce the wrong result.
The body includes the message and its CRC. The header remains uncoded.
''')
code(r'''
OPERATOR_OBSERVATIONS = ''  # Describe actual conditions and any deviation from the cue.
if local_video is not None:
    metrics, evaluation_dir = evaluate_attempt(REVIEW_ATTEMPT, ROI, OPERATOR_OBSERVATIONS)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print('Saved evaluation:', evaluation_dir)
    print('Previous evaluations, if any, remain in their own folders.')
    trace_file = evaluation_dir/'brightness.csv'
    if trace_file.exists():
        t, y = np.loadtxt(trace_file, delimiter=',', skiprows=1).T
        fig, ax = plt.subplots(figsize=(12,3))
        ax.plot(t,y,lw=1)
        ax.set(xlabel='Video time (s)', ylabel='Mean ROI brightness', title=f'{TRIAL_ID}: measured optical signal')
        plt.show()
else:
    print('No recording attached yet; no physical result is being claimed.')
''')
md('''
## 6 · Compare the groups and continue to the next trial

After saving an evaluation, move to the next TRIAL_ID in the plan and repeat
sections 2–5. Retakes remain separate physical attempts, with their own IDs and
records. Do not replace failures with successful retakes.

- **Body channel BER:** errors in received coded body bits before correction.
- **Payload BER:** errors in the recovered message after correction.
- **Packet failure rate:** includes synchronization/header failures.
- **Goodput:** correct, CRC-valid message bits divided by total channel time for
  evaluated packets, including failed packets and all framing/coding overhead.

A header failure has unknown payload BER; it is not recorded as zero errors.
Technical transmission aborts, missing evaluations and wrong-video associations
are reported separately. Group BER pools measured errors/bits rather than
averaging percentages. The table uses the latest retained evaluation for each
physical attempt; earlier evaluations remain available for audit.
''')
code(r'''
rows = comparison_rows(ROOT)
show_table(rows, ['codec','condition','attempts_started','retakes','evaluated_packets',
                  'packets_with_ber','packet_failures','payload_bit_errors',
                  'payload_bits_measured','payload_ber','correct_payload_goodput_bps'])
show_table(rows, ['codec','condition','transmission_aborted','awaiting_evaluation','analysis_or_pairing_errors'])
print('No recorded comparison result exists until actual attempts have been transmitted and evaluated.')
''')
md('''
## What this comparison will establish

For the same message and defined interference event, does repetition-3 reduce
payload errors or packet failures, and does that compensate for the longer
transmission? Uncoded MANUNITED takes **36.8 seconds**; repetition-3 takes
**72.0 seconds**. A clean repetition packet delivers fewer useful bits per second
than a clean uncoded packet because of the extra transmitted bits.

Three repeats per condition are a pilot, not evidence for a precise general
error probability. The first trial is deliberately repeat3/clean; the remaining
order is mixed in blocks. Message patterns and disturbance position can affect
results. Later broaden the message set, quantify actual interference and add
uncertainty estimates. Hamming, the third researched coding approach and an
extension remain separate coursework tasks.

All new trial records and videos stay under `experiments/repetition_comparison/`,
which is ignored by Git. The previously published six-video pilot is unchanged.
The cue is new host software: its scheduling and error handling are tested in
software, but its usability while you operate the light must be checked during
capture. Original firmware and decoder algorithms remain unchanged.
''')
nb=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3 (ipykernel)','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.11'}})
nbf.validate(nb)
nbf.write(nb,ROOT/'Repetition_Comparison.ipynb')
print('Created',len(cells),'cells')
