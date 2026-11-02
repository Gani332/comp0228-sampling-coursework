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
 'CLEAN': ('No disturbance','Keep the LCD, phone and room lighting steady throughout. No card or lamp action.'),
 'OCC_SPLIT': ('Three short LCD blocks per packet','Hold a card near the LCD without covering the phone lens or surrounding reference areas. At each red BLOCK cue, cover the flashing patch; clear it at the next cue. Three target 0.4-second blocks per packet. Keep the prefix clean.'),
 'OCC_CLUSTER': ('One longer LCD block per packet','At the red BLOCK cue, cover the flashing patch with the card. Clear it at the next cue. One target 1.2-second block per packet. Keep the prefix clean.'),
 'GLARE_BODY': ('One glare pulse per packet','Keep the lamp fixed at its marked position and its beam covered. At the red cue uncover the beam; cover it again as soon as the cue changes. One target 1.2-second glare pulse during the body. Do not wave the lamp.'),
 'LONG_PAYLOAD_CLUSTER': ('Longer message + one LCD block','Same card procedure as the clustered condition, with a previously unused 25-byte message. Follow the cue, not elapsed time guessed from the start of the video.'),
 'GLARE_PREAMBLE': ('Early glare: during acquisition','Keep the lamp fixed. Uncover/cover the beam at the early cue, during the preamble. This deliberately challenges acquisition. Keep the video even if decoding later fails.')}
CODECS={'none':'Uncoded','repeat3':'Repetition ×3','repeat5':'Repetition ×5','hamming74':'Hamming (7,4)','rs4':'Reed–Solomon'}

def estimate(rows):
 return (sum(float(r['scheduled_channel_seconds'])+.2 for r in rows)+8*(len(rows)-1)+8)/60

def build(root=ROOT):
 root=Path(root);sessions=load_sessions(root);cells=[]
 def md(s):cells.append(nbformat.v4.new_markdown_cell(s))
 def code(s,**meta):cells.append(nbformat.v4.new_code_cell(s,metadata=meta))
 def link(sid):return 'video-'+sid.lower().replace('_','-')
 md('''# LCD → phone: every recording, in order

**One labelled section per video. Every packet is listed inside it and sent automatically.** This notebook covers 21 planned videos / 82 packet transmissions: four clean pilots, three noise-calibration clips, twelve main comparisons, and two acquisition challenges. These are planned counts, not completed results.

**Budget: approximately 83 minutes of footage, excluding setup, transfer and retakes.** This is a focused experimental study, not a precise reliability certification. Start with development data, then freeze the receiver and disturbance settings before the main comparisons.

**Start with the first four CLEAN videos only (about 23 minutes).** We review their actual footage and timing before the main campaign. The next three calibration clips are development data too. Do not assume a 0.4-second hand movement is accurate without checking. Keep the card edge or a reference marker visible so actual disturbance timing can be annotated.

You can leave the phone fixed on a stand. You still start/stop each video and perform the card/lamp actions in noisy conditions. An overnight recording cannot supply those interventions. Separate files make failures, transfers and packet association easier to handle.

| You do | Notebook does |
|---|---|
| Run setup once | Loads the frozen planned order and saved progress |
| Run one section's Record cell, start the phone, press Enter | Sends that section's complete batch; displays cues; saves actual wire bits and logs |
| Stop at green STOP | Preserves the attempt, including failures |
| Transfer originals; run that section's optional Attach cell | Opens a file picker explicitly tied to that session |
| Paste the final handover summary in chat | Identifies which original videos and logs are ready for analysis |

**Printed output alone is not enough.** Analysis needs the original phone videos plus saved transmitter/cue logs. Copy originals without recompression. On the shared computer, their local paths are sufficient for us to inspect them.

Run **one recording cell at a time**, not Run All. Rerunning a completed section will show its saved attempt without transmitting again. Keep interrupted recordings; retakes are explicit and retain originals.
''')
 md("""## Experiment structure — fixed message set, matched comparisons

A **transmission** is one message sent using one configuration. A **video** contains several automatic transmissions. A **message block** uses the same message across its coding, interleaving and glare comparisons.

The main study uses the same **six messages for every relevant configuration**. Each message has seven card-occlusion transmissions and two glare transmissions: **nine transmissions in two videos per message**. The packet order is randomized in advance; the number and coverage are fixed.

| Comparison | Messages | Configurations per message | Physical transmissions | Additional videos |
|---|---:|---:|---:|---:|
| Codes under clustered occlusion | Same six | Uncoded, repetition-3, repetition-5, Hamming, RS; interleaving off | 30 | Six shared card videos |
| Interleaving under clustered occlusion | Same six | Hamming and RS with interleaving on; reuse off-controls above | 12 additional | Included in those six |
| Processing without coding, under glare | Same six | Uncoded; apply each frozen processing method offline | 6 | Six shared glare videos |
| Processing with coding, under glare | Same six | Hamming; apply the same processing methods offline | 6 | Included in those six |
| **Main total** | **Six matched message blocks** | **Nine transmissions per message** | **54** | **12 videos** |

Pilot/calibration are development checks, not extra main replicates. The held-out acquisition challenge uses reserved conditions/messages and frozen settings. Six different messages provide six matched observations per main configuration, not six repeats of an identical message. Shared controls and multiple processing methods do not multiply the number of physical observations.
""")
 blocks={}
 for sid,rows in sessions.items():
  r=rows[0]
  if r['phase']=='main':blocks.setdefault(int(r['block']),[]).append((sid,rows))
 table=['### Your six standard main messages','', '| Block | Message | Card video: 7 transmissions | Glare video: 2 transmissions | Total video time |','|---:|---|---|---|---:|']
 for block,groups in sorted(blocks.items()):
  by_condition={rows[0]['condition']:(sid,rows) for sid,rows in groups}
  card=by_condition['OCC_CLUSTER'][0];glare=by_condition['GLARE_BODY'][0]
  message=groups[0][1][0]['payload_utf8']
  table.append(f'| {block} | `{message}` | [{card}](#{link(card)}) | [{glare}](#{link(glare)}) | {sum(estimate(rows) for _,rows in groups):.1f} min |')
 md('\n'.join(table))
 md('## 0 — Load the recorder (once per notebook/kernel restart)')
 code('''from pathlib import Path
import sys
candidates = [Path.cwd(), Path.cwd() / "optical_link", Path.cwd().parent / "optical_link"]
PROJECT = next((p.resolve() for p in candidates if (p / "code/optical_link/physical_campaign.py").exists()), None)
if PROJECT is None:
    raise RuntimeError("Open this notebook from the optical_link folder.")
sys.path.insert(0, str(PROJECT / "code"))
from optical_link.physical_campaign_ui import Recorder
from optical_link.physical_campaign import PLAN, digest
recorder = Recorder(PROJECT)
if digest(PROJECT / PLAN) != "PLAN_DIGEST":
    raise RuntimeError("The schedule has changed since this notebook was generated. Regenerate its sections before recording.")
recorder.overview("pilot")
'''.replace('PLAN_DIGEST',hashlib.sha256((root/PLAN).read_bytes()).hexdigest()))
 md('''## Setup details — saved once
Connect the LCD USB cable. Fix the phone on a stable support, with the whole flashing patch and static reference surroundings visible. Keep resolution, orientation, distance and lighting consistent. Lock exposure/focus where available; otherwise record the setting as automatic or unknown.

Enter model, video settings, distance and operator once. Existing settings are reused. Update them before a changed setup using, for example, `recorder.setup(phone_model="iPad ...", distance_cm=40)`. Changing phone/iPad is a setup change; do not pool their recordings without labelling it.''')
 code('recorder.setup()')
 index=['## Recording checklist','', '| Video | Phase / block | Session | Message | Action | Packets | Approx. min |','|---|---|---|---|---|---:|---:|']
 for number,(sid,rows) in enumerate(sessions.items(),1):
  r=rows[0];index.append(f'| {number:02d} | {r["phase"]} / {r["block"]} | [{sid}](#{link(sid)}) | `{r["payload_utf8"]}` | {ACTIONS[r["condition"]][0]} | {len(rows)} | {estimate(rows):.1f} |')
 md('\n'.join(index))
 phase=None
 for number,(sid,rows) in enumerate(sessions.items(),1):
  first=rows[0]
  if first['phase']!=phase:
   phase=first['phase']
   if phase=='pilot':md('## Stage 1 — four clean pilot videos\nRecord these first. No disturbances. Start/stop once per section, not once per packet.')
   elif phase=='calibration':
    md("""## Stage 2 — three noise-calibration videos (about 4 minutes)
**Pause after the clean pilot.** Attach those four originals and run the handover cell before proceeding: timing must be checked first. The software permits development recordings, but it cannot establish that the physical link is valid on its own.

These three short clips establish whether card occlusion and glare actually create useful, measurable errors. They are excluded from main comparison statistics. Use the same fixed card/lamp arrangement throughout. Keep the card edge or a reference marker in view for timing annotation. Optional rehearsal below sends no data.

After calibration, attach all three originals and pause again. If the disturbance is too weak, too strong or impractical, we will make a versioned continuation plan and keep this development evidence. Do not edit the manifest or tune the main settings mid-study.""")
    code('# Optional rehearsal: uncomment ONE line.\n# recorder.rehearse("OCC_SPLIT")\n# recorder.rehearse("OCC_CLUSTER")\n# recorder.rehearse("GLARE_BODY")')
   elif phase=='main':
    md("""## Stage 3 — twelve main videos (about 50 minutes)
**Start only after pilot + calibration review and the documented analysis freeze.** Until then, these Record cells intentionally stop before accessing hardware. The freeze records real reviewed settings; it is not a checkbox to bypass.

Each of six message blocks has two videos, with their order randomized:

| Video type | Automatic transmissions | Purpose |
|---|---|---|
| One clustered card block per packet | Five codes with interleaving off, plus Hamming and Reed–Solomon with interleaving on (7 packets) | Code comparison and targeted interleaving comparison; off-controls are reused |
| One glare pulse per packet | Uncoded and Hamming, interleaving off (2 packets) | Apply receiver processing offline, with and without coding |

Follow the listed order. The message is identical within a block; messages and lengths vary between blocks. Sequence IDs rotate to avoid a fixed ID/configuration association, but six blocks do not fully balance seven IDs. Packet CRCs can differ across paired transmissions.

**No separate filter recordings are required.** Process the same raw videos with each frozen method later. Six observations per configuration support a focused comparison, not a precise high-reliability claim. Count failures and report uncertainty. The main noise protocol is fixed-duration disturbance per message, not constant noise rate per transmitted bit.""")
   else:md("""## Stage 4 — two reserved acquisition challenges (about 6 minutes)
Early glare deliberately interferes with the preamble. Keep receiver settings frozen and retain missed packets and header failures. Three codes per video, no interleaving. These are limited end-to-end stress checks; do not tune on their outcomes or treat them as six independent replications of one identical condition.""")
  table=['| Order | Optical sequence | Coding | Interleaving | Packet airtime (s) |','|---:|---:|---|---|---:|']
  for r in rows:table.append(f'| {r["packet_order"]} | {r["sequence"]} | {CODECS[r["codec"]]} | {"Off" if r["interleave_depth"]=="1" else "On — depth 8"} | {float(r["scheduled_channel_seconds"]):.1f} |')
  md(f'''<a id="{link(sid)}"></a>
## Video {number:02d}/{len(sessions):02d} — {sid}

**Message block:** {first['block']} · **Message:** `{first['payload_utf8']}` · **Condition:** {ACTIONS[first['condition']][0]} · **Approximate video:** {estimate(rows):.1f} minutes.

**Your action:** {ACTIONS[first['condition']][1]}

1. Run the Record cell below. It checks USB selection before prompting you.
2. Start ONE continuous phone video, then press Enter at the prompt. Any text cancels.
3. Keep recording through every packet and gap. Follow the large cues if this is a disturbance condition.
4. Stop at green **STOP PHONE RECORDING**. Keep the original file; no renaming needed.

The following {len(rows)} packets are automatic—do not restart the camera between them:

'''+'\n'.join(table))
  code(f'folder = recorder.record_next(phase="{phase}", session_id="{sid}")',campaign_role='record',session_id=sid,phase=phase)
  md(f'''**Optional after transfer — attach this section's original video.** You may return to this cell later; it is explicitly bound to `{sid}`, not whichever batch ran most recently. Cancel leaves files unchanged. If retakes exist, the notebook lists their attempt IDs rather than guessing.

If something unusual happened, use the commented note line to preserve it. A mistimed action or failed decode is not a reason to delete a recording.''')
  code(f'recorder.attach_session("{sid}")\n# recorder.note_session("{sid}", "Describe any interruption, mistimed cue or changed setting here.")',campaign_role='attach',session_id=sid)
 md('''## Handover — run after the pilot or whenever you pause
Paste this output into chat for progress and troubleshooting. For scientific analysis, also retain/provide the original video files and the logs in the printed local folder. Do not delete originals on the phone until the copies are verified.

No result is assumed to be correct merely because the transmitter finished. We still need optical association, timing checks, error analysis and matching decoding.''')
 code('recorder.handover()')
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
