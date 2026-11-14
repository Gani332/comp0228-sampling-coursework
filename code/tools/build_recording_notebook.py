"""Build a section for every planned recording, without opening hardware.

Refuses to replace an executed notebook: preserve its output or use --output.
"""
from pathlib import Path
import argparse
import hashlib
import sys
import nbformat

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code'))
from optical_link.physical_campaign import PLAN, load_sessions

ACTIONS={
 'CLEAN': ('No disturbance','Keep the screen patch, phone and room lighting steady throughout. No card or lamp action.'),
 'OCC_SPLIT': ('Three short patch blocks per packet','Hold a card near the screen patch without covering the phone lens or surrounding reference areas. At each BLOCK cue, cover the flashing patch; clear it at the next cue. Three target 0.4-second blocks per packet. Keep the prefix clean.'),
 'OCC_CLUSTER': ('One longer patch block per packet','At the BLOCK cue, cover the flashing patch with the card. Clear it at the next cue. One target 1.2-second block per packet. Keep the prefix clean.'),
 'GLARE_BODY': ('One glare pulse per packet','Keep the lamp fixed at its marked position and its beam covered. At the action cue uncover the beam; cover it again as soon as the cue changes. One target 1.2-second glare pulse during the body. Do not wave the lamp.'),
 'LONG_PAYLOAD_CLUSTER': ('Longer message + one patch block','Same card procedure as the clustered condition, with a previously unused 25-byte message. Follow the cue, not elapsed time guessed from the start of the video.'),
 'GLARE_PREAMBLE': ('Early glare: during acquisition','Keep the lamp fixed. Uncover/cover the beam at the early cue, during the preamble. This deliberately challenges acquisition. Keep the video even if decoding later fails.')}
CODECS={'none':'Uncoded','repeat3':'Repetition ×3','repeat5':'Repetition ×5','hamming74':'Hamming (7,4)','rs4':'Reed–Solomon'}

def estimate(rows):
 return (sum(float(r['scheduled_channel_seconds'])+.2 for r in rows)+8*(len(rows)-1)+8)/60

def build(root=ROOT):
 root=Path(root);sessions=load_sessions(root);cells=[]
 phase_minutes={phase:sum(estimate(rows) for rows in sessions.values() if rows[0]['phase']==phase) for phase in ('pilot','calibration','main','holdout')}
 def md(s):
  for key,value in dict(TOTAL_MINUTES=sum(phase_minutes.values()),PILOT_MINUTES=phase_minutes['pilot'],CAL_MINUTES=phase_minutes['calibration'],MAIN_MINUTES=phase_minutes['main'],HOLD_MINUTES=phase_minutes['holdout']).items():
   s=s.replace(key,f'{value:.1f}')
  cells.append(nbformat.v4.new_markdown_cell(s))
 def code(s,**meta):cells.append(nbformat.v4.new_code_cell(s,metadata=meta))
 def link(sid):return 'video-'+sid.lower().replace('_','-')
 md('''# Mac screen → phone: every recording, in order

**Start here:** run the dependency check, Load recorder, and Setup cells in order. Then record **Videos 01–04 only**, attach their originals and stop at the pilot checkpoint. In Jupyter, select a code cell and press **Shift+Enter**. Do not use Run All.

**One labelled section per video. Every packet is listed inside it and sent automatically.** This notebook covers 21 planned videos / 82 packet transmissions: four clean pilots, three noise-calibration clips, twelve main comparisons, and two acquisition challenges. These are planned counts, not completed results.

**Budget: approximately TOTAL_MINUTES minutes of footage, excluding setup, transfer and retakes.** This is a focused experimental study, not a precise reliability certification. Start with development data, then freeze the receiver and disturbance settings before the main comparisons.

**Start with the first four CLEAN videos only (about PILOT_MINUTES minutes).** We review their actual footage and timing before the main campaign. The next three calibration clips are development data too. Do not assume a 0.4-second hand movement is accurate without checking. Keep the card edge or a reference marker visible so actual disturbance timing can be annotated.

You can leave the phone fixed on a stand. You still start/stop each video and perform the card/lamp actions in noisy conditions. An overnight recording cannot supply those interventions. Separate files make failures, transfers and packet association easier to handle.

| You do | Notebook does |
|---|---|
| Run setup once | Loads the frozen planned order and saved progress |
| Run one section's Record cell, start the phone, press SPACE in the signal window | Sends that section's complete batch; displays cues; saves actual wire bits and logs |
| Stop when the signal window closes and the notebook shows STOP | Preserves the attempt, including failures |
| Transfer originals; run the matching Attach cell (now or later) | Opens a file picker explicitly tied to that session |
| Paste the final handover summary in chat | Identifies which original videos and logs are ready for analysis |

**Printed output alone is not enough.** Analysis needs the original phone videos plus saved transmitter/cue logs. Copy originals without recompression. On the shared computer, their local paths are sufficient for us to inspect them.

Run **one recording cell at a time**, not Run All. Rerunning a completed section will show its saved attempt without transmitting again. Keep interrupted recordings; retakes are explicit and retain originals.
''')
 md("""## Experiment structure — fixed message set, matched comparisons

A **transmission** is one message sent using one configuration. A **video** contains several automatic transmissions. A **message block** uses the same message across its coding, interleaving and glare comparisons.

The main study uses **three fixed payloads, each recorded in two rounds**. Each length/round block has seven card-occlusion transmissions and two glare transmissions: **nine transmissions in two videos per block**. Every configuration receives all three lengths in both rounds. The packet order is randomized in advance; the number and coverage are fixed.

| Comparison | Messages | Configurations per message | Physical transmissions | Additional videos |
|---|---:|---:|---:|---:|
| Codes under clustered occlusion | 3 lengths × 2 rounds | Uncoded, repetition-3, repetition-5, Hamming, RS; interleaving off | 30 | Six shared card videos |
| Interleaving under clustered occlusion | 3 lengths × 2 rounds | Hamming and RS with interleaving on; reuse off-controls above | 12 additional | Included in those six |
| Processing without coding, under glare | 3 lengths × 2 rounds | Uncoded; apply each frozen processing method offline | 6 | Six shared glare videos |
| Processing with coding, under glare | 3 lengths × 2 rounds | Hamming; apply the same processing methods offline | 6 | Included in those six |
| **Main total** | **Three lengths × two rounds** | **Nine transmissions per length/round** | **54** | **12 videos** |

Pilot/calibration are development checks, not extra main replicates. The held-out acquisition challenge uses a reserved acquisition-interference condition with the same long payload and frozen settings. The payloads are `A7k2` (4 bytes), `A7k2M9q4` (8 bytes), and `A7k2M9q4R6v8` (12 bytes). Each message/configuration is physically captured twice, once per round. Two repeats provide a basic consistency check, not a precise reliability estimate. One string per length means length and content are not separately isolated. Shared controls and multiple processing methods do not multiply the number of physical observations.
""")
 blocks={}
 for sid,rows in sessions.items():
  r=rows[0]
  if r['phase']=='main':blocks.setdefault(int(r['block']),[]).append((sid,rows))
 table=['### Three payload lengths, repeated in two recording rounds','', 'Complete Round 1 before Round 2. Length order is randomised separately per round, as are condition/configuration orders. Keep settings fixed; retain every failed attempt.', '', '| Round | Block | Bytes | Message | Card video: 7 transmissions | Glare video: 2 transmissions | Total video time |','|---:|---:|---:|---|---|---|---:|']
 for block,groups in sorted(blocks.items()):
  by_condition={rows[0]['condition']:(sid,rows) for sid,rows in groups}
  card=by_condition['OCC_CLUSTER'][0];glare=by_condition['GLARE_BODY'][0]
  message=groups[0][1][0]['payload_utf8']
  table.append(f'| {groups[0][1][0]["repeat_round"]} | {block} | {len(message.encode("ascii"))} | `{message}` | [{card}](#{link(card)}) | [{glare}](#{link(glare)}) | {sum(estimate(rows) for _,rows in groups):.1f} min |')
 md('\n'.join(table))
 md("""## First-time setup on your friend's Mac

Clone/download this branch and keep the notebook beside its `code` and `data` folders. The notebook alone is not enough. Double-click `Record_Physical_Trials.command` to install missing Python dependencies and open Jupyter. Python 3 must already be installed.

The dependency cell below checks this notebook’s Python environment and installs missing requirements if necessary. It does not open a signal window. An installation needs internet access; restart the kernel if the cell reports that packages were installed. The flashing signal opens in its own window. No ESP32 or separate LCD is required.

Fix display brightness; disable automatic brightness, True Tone, Night Shift and automatic display sleep for the recording session. Keep the signal window visible and stationary. Record the central patch and the two static reference strips; keep the changing cue text outside the phone frame where practical. Cues are for the operator, not receiver inputs.

Mac data is saved separately under `data/physical_campaign_mac_v1/`. Earlier LCD results and readiness do not validate this display. Start with the four clean pilots. Display timestamps in logs measure host calls, not the actual light reaching the camera.
""")
 code('''from pathlib import Path
import importlib.util
import subprocess
import sys
candidates = [Path.cwd(), Path.cwd() / "optical_link", Path.cwd().parent / "optical_link"]
requirements_root = next((p.resolve() for p in candidates if (p / "code/requirements-screen-camera.txt").is_file()), None)
if requirements_root is None:
    raise RuntimeError("Open the notebook from the complete repository folder, beside code and data.")
modules = ["pygame", "cv2", "serial", "numpy", "pandas", "matplotlib", "nbformat", "ipywidgets", "ipykernel", "jupyterlab"]
missing = [name for name in modules if importlib.util.find_spec(name) is None]
if missing:
    print("Installing missing notebook dependencies:", ", ".join(missing))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(requirements_root / "code/requirements.txt"), "-r", str(requirements_root / "code/requirements-screen-camera.txt")])
    print("Installed. Restart the kernel, then rerun this cell and continue with Load recorder.")
else:
    print("Dependencies found. Continue with Load recorder. Python:", sys.executable)
''',campaign_role='dependencies')
 md('## 0 — Load the recorder (once per notebook/kernel restart)')
 code('''from pathlib import Path
import sys
candidates = [Path.cwd(), Path.cwd() / "optical_link", Path.cwd().parent / "optical_link"]
PROJECT = next((p.resolve() for p in candidates if (p / "code/optical_link/physical_campaign.py").exists()), None)
if PROJECT is None:
    raise RuntimeError("Open this notebook from the repository folder beside code and data.")
sys.path.insert(0, str(PROJECT / "code"))
from optical_link.physical_campaign_ui import ScreenRecorder
from optical_link.physical_campaign import PLAN, digest
recorder = ScreenRecorder(PROJECT)
if digest(PROJECT / PLAN) != "PLAN_DIGEST":
    raise RuntimeError("The schedule has changed since this notebook was generated. Regenerate its sections before recording.")
recorder.overview("pilot")
'''.replace('PLAN_DIGEST',hashlib.sha256((root/PLAN).read_bytes()).hexdigest()))
 md('''## Setup details — saved once
Use the Mac’s built-in display; no USB transmitter is needed. Fix the phone on a stable support, with the whole flashing patch and both static reference strips visible. Keep resolution, orientation, distance and lighting consistent. Lock exposure/focus where available; otherwise record the setting as automatic or unknown.

Enter model, video settings, distance and operator once. Existing settings are reused. Update them before a changed setup using, for example, `recorder.setup(phone_model="iPad ...", distance_cm=40)`. Changing phone/iPad is a setup change; do not pool their recordings without labelling it.''')
 code('recorder.setup()')
 index=['## Recording checklist','', '| Video | Phase / block | Session | Message | Action | Packets | Approx. min |','|---|---|---|---|---|---:|---:|']
 for number,(sid,rows) in enumerate(sessions.items(),1):
  r=rows[0];index.append(f'| {number:02d} | {r["phase"]} / {r["block"]} | [{sid}](#{link(sid)}) | `{r["payload_utf8"]}` | {ACTIONS[r["condition"]][0]} | {len(rows)} | {estimate(rows):.1f} |')
 md('\n'.join(index))
 phase=None
 main_round=None
 for number,(sid,rows) in enumerate(sessions.items(),1):
  first=rows[0]
  if first['phase']!=phase:
   phase=first['phase']
   if phase=='pilot':md('## Stage 1 — four clean pilot videos\nRecord these first. No disturbances. Start/stop once per section, not once per packet.')
   elif phase=='calibration':
    md('## STOP — pilot checkpoint\nBefore Video 05, transfer and attach all four pilot originals using their Attach cells. Run the summary below and share the original video paths plus the saved attempt logs for timing review. Resume calibration only after that review; a completed transmitter run does not establish decoding success.')
    code('recorder.handover()',campaign_role='checkpoint',after_phase='pilot')
    md("""## Stage 2 — three noise-calibration videos (about CAL_MINUTES minutes)
**Pause after the clean pilot.** Attach those four originals and run the handover cell before proceeding: timing must be checked first. The software permits development recordings, but it cannot establish that the physical link is valid on its own.

**Before Video 05:** frame the complete signal window, including the black reference strip on one side, the central flashing patch, and the white reference strip on the other. Use landscape phone orientation or move back if needed. Keep both strips visible while the card covers only the central patch. Record any framing change in your setup/notes; these calibration clips will check the changed view.

**Video 05 action:** follow three short BLOCK / CLEAR cues per packet. There are two automatic packets (uncoded and Hamming); keep one continuous phone video through both. Videos 06 and 07 calibrate a longer block and glare respectively. Stop for review after Video 07.

The campaign receiver uses the configured bit duration (200 ms here), with optical acquisition still found from the preamble. The earlier estimated-clock method remains available for comparison; no message truth or CRC result selects timing.

These three short clips establish whether card occlusion and glare actually create useful, measurable errors. They are excluded from main comparison statistics. Use the same fixed card/lamp arrangement throughout. Keep the card edge or a reference marker in view for timing annotation. Optional rehearsal below sends no data.

After calibration, attach all three originals and pause again. If the disturbance is too weak, too strong or impractical, we will make a versioned continuation plan and keep this development evidence. Do not edit the manifest or tune the main settings mid-study.""")
    code('# Optional rehearsal: uncomment ONE line.\n# recorder.rehearse("OCC_SPLIT")\n# recorder.rehearse("OCC_CLUSTER")\n# recorder.rehearse("GLARE_BODY")')
   elif phase=='main':
    md('## STOP — calibration checkpoint\nBefore Video 08, attach the three calibration originals and run this summary. We must review actual disturbances and document frozen settings before main recording. A missing-freeze error at this stage is expected until review is complete.')
    code('recorder.handover()',campaign_role='checkpoint',after_phase='calibration')
    md("""## Stage 3 — twelve main videos (about MAIN_MINUTES minutes)
**Start only after pilot + calibration review and the documented analysis freeze.** Until then, these Record cells intentionally stop before opening the signal window. The freeze records real reviewed settings; it is not a checkbox to bypass.

Each round tests all three payload lengths. Each length/round block has two videos, with their order randomized:

| Video type | Automatic transmissions | Purpose |
|---|---|---|
| One clustered card block per packet | Five codes with interleaving off, plus Hamming and Reed–Solomon with interleaving on (7 packets) | Code comparison and targeted interleaving comparison; off-controls are reused |
| One glare pulse per packet | Uncoded and Hamming, interleaving off (2 packets) | Apply receiver processing offline, with and without coding |

Follow the listed order. The message is identical within a block and repeated in the second round. Disturbance centres are drawn by the same predefined rule; realised hand actions and CRC bits need not be identical across repeats. Sequence IDs rotate to avoid a fixed ID/configuration association, but six blocks do not fully balance seven IDs. Packet CRCs can differ across paired transmissions.

**No separate filter recordings are required.** Process the same raw videos with each frozen method later. Six observations per configuration support a focused comparison, not a precise high-reliability claim. Count failures and report uncertainty. The main noise protocol is fixed-duration disturbance per message, not constant noise rate per transmitted bit.""")
   else:md("""## Stage 4 — two reserved acquisition challenges (about HOLD_MINUTES minutes)
Early glare deliberately interferes with the preamble. Keep receiver settings frozen and retain missed packets and header failures. Three codes per video, no interleaving. The same 12-byte payload is sent with each of three codes twice. Only the acquisition-interference condition is held out; the payload is already used in development and main trials. These are limited end-to-end stress checks, not a precise reliability estimate; do not tune on their outcomes.""")
  if phase=='main' and first['repeat_round']!=main_round:
   main_round=first['repeat_round']
   md(f'### Main recording round {main_round} of 2\n'+('First physical capture of each length/configuration. Follow the video order below.' if main_round=='1' else 'Repeat the same three payloads/configurations in the listed order. Keep the setup/settings fixed and retain first-round outcomes; this round adds evidence rather than replacing failures.'))
  table=['| Order | Optical sequence | Coding | Interleaving | Packet airtime (s) |','|---:|---:|---|---|---:|']
  for r in rows:table.append(f'| {r["packet_order"]} | {r["sequence"]} | {CODECS[r["codec"]]} | {"Off" if r["interleave_depth"]=="1" else "On — depth 8"} | {float(r["scheduled_channel_seconds"]):.1f} |')
  md(f'''<a id="{link(sid)}"></a>
## Video {number:02d}/{len(sessions):02d} — {sid}

**Round:** {first['repeat_round']} (0 = calibration) · **Message block:** {first['block']} · **Payload bytes:** {first['payload_bytes']} · **Message:** `{first['payload_utf8']}` · **Condition:** {ACTIONS[first['condition']][0]} · **Approximate video:** {estimate(rows):.1f} minutes.

**Your action:** {ACTIONS[first['condition']][1]}

1. Run the Record cell below. A separate signal window opens.
2. Frame the patch and both reference strips; start ONE continuous phone video. Click the signal window and press SPACE to start the countdown. ESC cancels and preserves the attempt.
3. Keep recording through every packet and gap. Follow the cues in the signal window if this is a disturbance condition.
4. Stop when the signal window closes. The notebook shows **STOP PHONE RECORDING** after success; if an error appears instead, keep the partial video and logs. Do not start a replacement automatically. Keep the original filename.

The following {len(rows)} packets are automatic—do not restart the camera between them:

'''+'\n'.join(table))
  code(f'folder = recorder.record_next(phase="{phase}", session_id="{sid}")',campaign_role='record',session_id=sid,phase=phase)
  md(f'''**After transfer — attach this section's original video (required for analysis).** Skip this Attach cell until the file has been transferred, then return to it; it is explicitly bound to `{sid}`, not whichever batch ran most recently. Cancel leaves files unchanged. If retakes exist, the notebook lists their attempt IDs rather than guessing.

If something unusual happened, use the commented note line to preserve it. A mistimed action or failed decode is not a reason to delete a recording.''')
  code(f'recorder.attach_session("{sid}")\n# recorder.note_session("{sid}", "Describe any interruption, mistimed cue or changed setting here.")',campaign_role='attach',session_id=sid)
 md('''## Handover — run after the pilot or whenever you pause
Paste this output into chat for progress and troubleshooting. For scientific analysis, also retain/provide the original video files and the logs in the printed local folder. Do not delete originals on the phone until the copies are verified.

No result is assumed to be correct merely because the transmitter finished. We still need optical association, timing checks, error analysis and matching decoding.''')
 code('recorder.handover()')
 md('''## If something does not work

| What you see | What to do |
|---|---|
| Dependency/import error | Run the dependency cell; after installation restart the kernel and rerun Load + Setup. |
| No signal window visible | Look behind Jupyter for the pygame window. Click it before pressing SPACE. Do not run another Record cell while one is active. |
| Window stays white | It is waiting for SPACE. Start the phone recording first, then click the signal window and press SPACE. |
| Window closes early or an error appears | Stop the phone and keep the partial original and logs. Annotate the attempt; use an explicit retained retake only when needed. |
| Main recording says pilot review/freeze pending | Stop and share the pilot/calibration originals and handover output. The documented review must precede the main trials. |
| Schedule hash mismatch | Stop and use the notebook and schedule from the same Git revision. Restart the kernel after updating files; do not bypass the check. |
| A section already has an attempt | Attach its matching video. Rerunning the cell deliberately does not send another packet batch. |

On a later day or after restarting Jupyter, run Load and Setup again to recover saved progress. Leave the data folder in place. After pulling updated code, restart the kernel before continuing. A planned second recording round is part of the schedule; a retake is a separate, retained attempt for an interrupted/mistaken recording.
''')
 md('''## Recovering from an interrupted attempt
Keep the partial video and its logs. To intentionally repeat a named session, use the example below with its actual ID. This creates a new attempt and never overwrites the previous one. If there are multiple attempts when attaching or annotating, pass the matching `attempt_id=` shown in the output.

Do not repeatedly retry until a success replaces a failure in the dataset. All attempts remain part of the evidence.''')
 code('# Example only — do not uncomment without choosing the intended session.\n# recorder.record_next(session_id="PILOT_T1_L4", retake=True)\n# recorder.pending_videos()')
 notebook=nbformat.v4.new_notebook(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),campaign_plan_sha256=hashlib.sha256((root/PLAN).read_bytes()).hexdigest()))
 nbformat.validate(notebook)
 for cell in cells:
  if cell.cell_type=='code':compile(cell.source,'Record_Physical_Trials.ipynb','exec')
 return notebook

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,default=ROOT/'Record_Physical_Trials.ipynb')
 args=parser.parse_args()
 if args.output.exists():
  old=nbformat.read(args.output,as_version=4)
  if any(c.cell_type=='code' and (c.outputs or c.execution_count is not None) for c in old.cells):
   parser.error('Existing notebook has executed cells. Preserve it and specify a fresh --output filename.')
 notebook=build();nbformat.write(notebook,args.output)
 print(f'Saved {sum(c.metadata.get("campaign_role")=="record" for c in notebook.cells)} recording sections to {args.output}')
if __name__=='__main__':main()
