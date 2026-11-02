"""Create a proposed recording manifest. Does not connect to or operate hardware."""
from pathlib import Path
import csv, json, random, sys
PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / 'data/plans/physical_campaign_v1'
sys.path.insert(0, str(PROJECT / 'code'))
from optical_link.protocol import make_packet, GUARD_BITS, PREAMBLE, HEADER_BITS
if list((PROJECT/'data/physical_campaign_v1/attempts').glob('*/session.json')):
    raise RuntimeError('Recordings already exist. Preserve this schedule; create a reviewed new plan version instead of overwriting it.')
rng = random.Random(20261101)
configs = [(c, d) for c in ('none', 'repeat3', 'repeat5', 'hamming74', 'rs4') for d in (1, 8)]
sequences = {c: i+1 for i, c in enumerate(configs)}
rows = []
def add(session, phase, block, condition, message, cases, role, sequence_map=None):
    # Paired on/off transmissions receive the same intended physical event centres.
    # These are cues, not measurements of realised interference.
    centre = rng.uniform(.35, .65)
    short_centres = [.20+rng.uniform(-.025,.025), .50+rng.uniform(-.025,.025), .80+rng.uniform(-.025,.025)]
    for position, (codec, depth) in enumerate(cases, 1):
        seq = (sequence_map or sequences)[(codec, depth)]
        p = make_packet(message, codec, seq)
        body_start = .2+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*.2
        body_duration = len(p.body_bits)*.2
        if condition == 'OCC_SPLIT':
            events = [(body_start+f*body_duration-.2, .4, 'full_patch_occlusion') for f in short_centres]
        elif condition in ('OCC_CLUSTER','LONG_PAYLOAD_CLUSTER'):
            events = [(body_start+centre*body_duration-.6, 1.2, 'full_patch_occlusion')]
        elif condition == 'GLARE_BODY':
            events = [(body_start+centre*body_duration-.6, 1.2, 'localized_glare')]
        elif condition == 'GLARE_PREAMBLE':
            events = [(.2+GUARD_BITS*.2+1.0, 1.2, 'localized_glare')]
        else:
            events = []
        for start, length, _ in events:
            if condition != 'GLARE_PREAMBLE':
                assert start >= body_start+.5 and start+length <= body_start+body_duration-.5
        rows.append(dict(session_id=session, phase=phase, block=block, packet_order=position,
                         packet_id=f'{session}_seq{seq:03d}', sequence=seq,
                         condition=condition, payload_utf8=message, payload_hex=message.encode().hex(),
                         payload_bytes=len(message.encode()), codec=codec, interleave_depth=depth,
                         bit_ms=200, packet_bits=len(p.bits), scheduled_channel_seconds=round(len(p.bits)*.2,3),
                         cue_events_json=json.dumps([dict(start_after_START_ack_s=round(a,3),duration_target_s=b,kind=c) for a,b,c in events]),
                         evidence_role=role, status='planned_not_recorded'))
# Timing pilot: 4/16-byte human messages x 2 codes x 2 depths x 2 physical repetitions.
for repeat in (1,2):
    for length, message in [(4,'LARA'),(16,'CANIGETAFIRSTPLS')]:
        cases=[(c,d) for c in ('none','repeat5') for d in (1,8)];rng.shuffle(cases)
        add(f'PILOT_T{repeat}_L{length}','pilot',repeat,'CLEAN',message,cases,'development_only')
# Development calibration is explicit and excluded from confirmatory results.
for index,condition in enumerate(['OCC_SPLIT','OCC_CLUSTER','GLARE_BODY'],1):
    cases=[('none',1),('hamming74',1)];rng.shuffle(cases)
    add(f'CAL_{index}_{condition}','calibration',index,condition,'LARA',cases,'development_only')
# Six message blocks: five uncoded/non-interleaved codes + two interleaved additions.
# One video per condition/block avoids extra camera starts and time-order confounding.
messages=['RIYAADH','ADRIAN','OMAR','LARA','MANUNITED','PLEASEWORK']
comparison=[(c,1) for c in ('none','repeat3','repeat5','hamming74','rs4')]+[('hamming74',8),('rs4',8)]
sequence_rng=random.Random(20261102)
config_order=sequence_rng.sample(comparison,len(comparison))
sequence_labels=sequence_rng.sample(list(range(1,8)),7)
for block,message in enumerate(messages,1):
    sequence_map={config:sequence_labels[(j+block-1)%7] for j,config in enumerate(config_order)}
    conditions=['OCC_CLUSTER','GLARE_BODY'];rng.shuffle(conditions)
    for position,condition in enumerate(conditions,1):
        cases=list(comparison) if condition=='OCC_CLUSTER' else [('none',1),('hamming74',1)]
        rng.shuffle(cases)
        add(f'MAIN_B{block:02d}_{position}_{condition}','main',block,condition,message,cases,'frozen_comparison',sequence_map)
# Predeclared acquisition challenge; keep failures and never tune on these outcomes.
for repeat,message in enumerate(['CANIGETAFIRSTPLS','UCLISGREATSY'],1):
    cases=[('none',1),('hamming74',1),('rs4',1)];rng.shuffle(cases)
    add(f'HOLD_R{repeat}_GLARE_PREAMBLE','holdout',repeat,'GLARE_PREAMBLE',message,cases,'unseen_until_analysis_frozen')
with (ROOT/'schedule.csv').open('w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
sessions=[]
for session in dict.fromkeys(r['session_id'] for r in rows):
    rr=[r for r in rows if r['session_id']==session]
    channel=sum(r['scheduled_channel_seconds'] for r in rr)
    # Assumed future runner: 8 s between packets, 5 s lead, 3 s tail, .2 s firmware start lead/packet.
    planned=channel+8*(len(rr)-1)+8+.2*len(rr)
    sessions.append(dict(session_id=session,phase=rr[0]['phase'],block=rr[0]['block'],condition=rr[0]['condition'],
                         payload=rr[0]['payload_utf8'],packets=len(rr),nominal_channel_seconds=round(channel,2),
                         estimated_video_minutes=round(planned/60,2),raw_video_path='',tx_manifest_path='',operator='',
                         phone_model='',video_mode='',exposure_setting='',focus_setting='',distance_cm='',
                         lamp_setting='',lamp_position='',source_revision='',protocol_deviations='',recording_status='not_started'))
with (ROOT/'session_log.csv').open('w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(sessions[0]));writer.writeheader();writer.writerows(sessions)
summary={phase:dict(packets=sum(r['phase']==phase for r in rows),sessions=sum(s['phase']==phase for s in sessions),
                    estimated_recording_hours=round(sum(s['estimated_video_minutes'] for s in sessions if s['phase']==phase)/60,2))
         for phase in ['pilot','calibration','main','holdout']}
summary.update(schedule_seed=20261101, sequence_balance_seed=20261102,
    hardware='Original ESP32-S3/ST7796S LCD to phone',
    main_payload_policy='Six natural messages; matched within blocks. Content and length are not separately estimated.',
    sequence_policy='Rotating IDs across six blocks, unique within video. Not a fully balanced seven-block design; CRCs differ between paired packets.',
    readiness='Pilot first, then calibration. Main/holdout require documented timing/noise review and frozen settings.',
    noise_policy='Provisional fixed 1.2-second body occlusion/glare; verify feasibility during calibration before freezing. Changes require a versioned continuation plan once recording starts.',
    timing_note='Includes nominal firmware lead, gaps, video lead/tail. Excludes setup, transfer, operator pauses and retakes.')
(ROOT/'schedule_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
assert len(rows)==82
assert len({r['packet_id'] for r in rows})==82
assert len(sessions)==21
print(json.dumps(summary,indent=2))
