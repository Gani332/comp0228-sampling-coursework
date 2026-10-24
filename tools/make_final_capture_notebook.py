"""Generate exactly three plain recording cells; no widgets or hardware actions."""
from pathlib import Path
import textwrap
import nbformat as nbf
root=Path(__file__).resolve().parents[1]
cells=[]
def md(s):cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(s).strip()))
def code(s):cells.append(nbf.v4.new_code_cell(textwrap.dedent(s).strip()))
md('''
# Record the three videos

**Run cell 1, then cell 2, then cell 3. Each cell records one batch.**
The iPhone records the video; the cell controls the flashing screen.

For each cell:
1. Click its **Run ▶** button. A text prompt will appear.
2. Start recording on your iPhone, then press **Enter in the prompt** to begin flashing.
   Type `cancel` instead if you are not ready.
3. Follow **KEEP STEADY** for each header and **DO A LIGHT SWEEP NOW** during each message.
   Roughly following the cue is fine; there is no strict two-second window.
4. Keep filming through the pauses and all methods in that cell.
5. After **BATCH FINISHED**, film two more seconds, then stop your phone.

There is no dropdown, checkbox, ROI box or video playback in this notebook.
The ROI is chosen later when analysing the recordings. Use a separate phone video
for each cell and keep the whole flashing patch and nearby screen visible.

If the notebook already has an older kernel running, **restart the kernel once**.
No setup cell is needed. Running all cells will still pause at each start prompt.
''')
for number,batch_id,message,methods,duration in [
 (1,'B01','MANUNITED','Repeat5 → Hamming → Reed–Solomon','3 min 45 s'),
 (2,'B02','ADRIAN','Reed–Solomon → Repeat3 → Hamming → Repeat5','4 min 15 s'),
 (3,'B03','OMAR','Hamming → Repeat5 → Reed–Solomon → Repeat3','3 min 40 s')]:
 md(f'''## {number} · Record {message}

**{methods}** — allow approximately **{duration}**.
Run this cell, start a fresh iPhone video, then press Enter at the prompt.
Keep recording until the whole batch finishes.
''')
 code(f'''from optical_link.capture_cell import record_batch_cell
recording_{number} = record_batch_cell('{batch_id}', setup=globals().get('SETUP'))''')
md('''
## Finished

AirDrop the original videos with their existing iPhone filenames and tell me
when they arrive. I will organise the files, match them to the saved transmission
logs, and prepare the analysis. Keep partial recordings and retakes too.

A completed batch will not transmit again if you rerun its cell accidentally.
If a batch must be stopped, use **Interrupt kernel**; the partial logs are retained.
A deliberate retake can be requested separately. Capturing completes the hardware
step; video completeness, optical IDs and decoding still need to be checked later.
''')
nb=nbf.v4.new_notebook(cells=cells)
nb.metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}}
nbf.validate(nb);nbf.write(nb,root/'Final_Recordings.ipynb')
print('Created exactly',sum(c.cell_type=='code' for c in cells),'recording code cells.')
