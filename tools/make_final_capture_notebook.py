"""Generate an unexecuted capture-only notebook; no hardware actions."""
from pathlib import Path
import textwrap
import nbformat as nbf
root=Path(__file__).resolve().parents[1]
cells=[]
def md(s):cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(s).strip()))
def code(s):cells.append(nbf.v4.new_code_cell(textwrap.dedent(s).strip()))
md('''
# Finish the physical recordings
### COMP0228 · Four-person group · 3 phone videos, 11 missing transmissions

**Purpose:** reuse the existing uncoded noisy recordings of MANUNITED, ADRIAN and
OMAR, and the noisy repeat3 MANUNITED recording. Capture only the missing cells.
This is a compact comparison across three message cases, not a guarantee of 90%+
or three repetitions of an identical experiment. Historical conditions are not
proved identical. The later receiver extension will reuse these videos.

| Phone recording | Messages transmitted in sequence | Flashing time |
|---|---|---:|
| B01 — MANUNITED | Repeat5 → Hamming → Reed–Solomon | 200.4 s |
| B02 — ADRIAN | Reed–Solomon → Repeat3 → Hamming → Repeat5 | 220.8 s |
| B03 — OMAR | Hamming → Repeat5 → Reed–Solomon → Repeat3 | 186.4 s |

The screen pauses for eight seconds between messages. **Keep the phone recording
through those pauses.** Allow roughly 4 minutes per video. Each packet gets its
own unique optical ID and saved transmission log; each batch gets a retained folder.

**Run All only loads this notebook and its controls. It never starts the screen.**
Flashing requires ticking “My iPhone is recording continuously” and clicking
“Start this recording”. Re-running the dashboard cell does not transmit either.
''')
md('''
## 1 · Load the project and record the setup

Open this notebook from the optical_link project folder. Restart the kernel if
older project helpers were imported. The supplied launcher uses the project-local environment prepared for these
controls. In VS Code, select this project’s `.venv` Python kernel. If another
kernel reports missing widgets, run `%pip install "ipywidgets>=8,<9"` in a
separate cell and restart it.

Keep the phone stationary with the whole flashing patch and nearby non-flashing
screen area visible. Keep camera settings and lamp brightness comparable across
recordings. Enter actual setup information below where known; unknown values
remain explicitly unreported rather than invented.
''')
code('''
from pathlib import Path
import json
from IPython.display import display, HTML
from optical_link.device import ports
from optical_link.capture import load_capture_plan, capture_status, LABELS
from optical_link.capture_ui import CaptureDashboard

ROOT = Path.cwd().resolve()
assert (ROOT / 'optical_link').is_dir(), 'Open this notebook from the project folder.'
plan = load_capture_plan(ROOT)
available = ports()
esp_ports = [p['port'] for p in available if p['vid'] == 0x303A and p['pid'] == 0x1001]
PORT = esp_ports[0] if len(esp_ports) == 1 else '/dev/cu.usbmodem101'
SETUP = {
    'phone_model': 'iPhone — exact model unreported',
    'distance_cm': None,
    'camera_mode_fps_and_exposure_lock': '',
    'room_lighting': '',
    'lamp_setting_and_movement': '',
    'notes': '',
}
print('Selected serial port:', PORT)
print('Available ports:', available)
print('New transmissions:', sum(len(b['packets']) for b in plan['batches']))
print('Total flashing time:', round(sum(b['channel_seconds'] for b in plan['batches']), 1), 'seconds')
print('The original recordings and previous notebook are preserved.')
''')
md('''
## 2 · Record each batch

1. Run the next cell once to display the controls.
2. Check the selected recording, then start filming on your iPhone.
3. Tick the recording checkbox and click **Start this recording**.
4. During **KEEP STEADY**, leave the lighting steady so the header can be read.
5. During **MESSAGE BODY**, introduce a comparable light disturbance when you
   choose. There is no strict sweep instant or two-second validity requirement.
   Note what actually happened; keep failures as evidence.
6. Keep filming through the eight-second gaps and repeat the disturbance during
   the body of each new message.
7. Only after **BATCH FINISHED**, film two more seconds and stop.
8. Click **Prepare next recording**, start a new phone video, and repeat.

If you need to stop a running batch, use the notebook's **Interrupt kernel**
control. This requests STOP and retains partial logs. Keep that partial video.
A completed batch cannot be sent again without explicitly enabling the retake
checkbox. Retakes receive fresh IDs and never overwrite prior evidence.

If the controls do not appear, check the selected kernel and widget support;
do not substitute the old repetition notebook, which has a different plan.
''')
code('''
dashboard = CaptureDashboard(ROOT, plan, PORT, SETUP).show()
''')
md('''
## 3 · AirDrop and attach the three original videos

You may do this after all three recordings. Rename the files in Downloads:

- `B01_MANUNITED_NOISY.MOV`
- `B02_ADRIAN_NOISY.MOV`
- `B03_OMAR_NOISY.MOV`

In the attachment controls above, select the matching batch attempt, check the
path, describe actual disturbance and deviations, and click **Save original video
+ notes**. If the filename or extension differs, enter the real path instead.
For a retake, keep a distinct filename and select its distinct attempt folder.

The program copies the original, checks its hash, and records basic video
metadata. It flags unexpectedly short clips. It does not yet claim that the
optical IDs match, all headers decode, or the message was recovered: those checks
belong to the analysis stage. Do not discard a video because its eventual CRC fails.

These are continuous multi-packet videos. Later analysis must locate each packet
and verify its unique optical ID against the saved per-packet logs. Do not pass
a whole batch through the old one-packet evaluation cell and count it as all
three/four transmissions. Host acknowledgment times and eight-second gaps are
retained to assist segmentation; the receiver must decode message bits independently.
''')
code('''
rows = capture_status(ROOT, plan)
for row in rows:
    print(f"{row['batch']} | {row['message']} | {row['latest_status']} | video saved: {row['video_saved']}")
    if row['attempt_dir']:
        print('  ', row['attempt_dir'])
if all(r['latest_status'] == 'controller_completed' and r['video_saved'] for r in rows):
    print('All planned batches are sent and attached. Optical association, completeness and decoding still need verification.')
else:
    print('Complete the remaining captures/attachments shown above. Partial and earlier attempts remain saved.')
''')
md('''
## 4 · What comes after recording

Use the previous eight videos to develop the receiver. Keep these new recordings
for evaluation once settings are frozen; checking capture completeness is fine,
but tuning to their decoded message outcomes would make them development data.

Compare the original mean-ROI receiver, reference-region lighting compensation,
spatially robust patch aggregation, and their combination on identical recordings.
Measure errors before/after correction, CRC and exact-match results, packet
failures, airtime and useful delivered-bit rate. Retain failed headers and all
retakes. Three message cases provide descriptive evidence, not precise reliability
estimates or proof that all conditions are matched.

**Reed–Solomon implementation:** the project bundles the unmodified, attributed
`reedsolo` 1.7.0 library (see `optical_link/_vendor/README.txt`). The integration
uses byte symbols in GF(256), four parity bytes, and the existing payload CRC.
Four parity bytes correct up to two erroneous byte symbols per codeword;
beyond that capacity, failure or miscorrection is possible, so CRC still matters.
Understand and explain the library use in your presentation rather than claiming
to have written its algebraic decoder.
''')
nb=nbf.v4.new_notebook(cells=cells)
nb.metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}}
nbf.validate(nb)
nbf.write(nb,root/'Final_Recordings.ipynb')
print('Created Final_Recordings.ipynb with',len(cells),'cells')
