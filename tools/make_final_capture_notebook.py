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
This notebook is only for recording. Transmission logs are saved automatically;
I will handle the video organisation and analysis afterwards.

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
from optical_link.device import ports
from optical_link.capture import load_capture_plan
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
## 3 · Finished

After all three batches, AirDrop the original videos to your Mac with their
existing iPhone filenames. Tell me in chat when they have arrived.

**You do not need to rename files, enter video paths, choose folders, attach
recordings, or run decoding here.** I will organise the originals, check their
optical packet IDs against the automatically saved logs, and prepare the analysis
separately. Keep any partial recordings or retakes too.

This notebook only controls transmission for your phone recordings. Its progress
table confirms which batches were transmitted; it does not claim that phone
footage has been received or verified.
''')
nb=nbf.v4.new_notebook(cells=cells)
nb.metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}}
nbf.validate(nb)
nbf.write(nb,root/'Final_Recordings.ipynb')
print('Created Final_Recordings.ipynb with',len(cells),'cells')
