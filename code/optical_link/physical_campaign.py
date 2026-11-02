"""Manifest-driven LCD capture. Import/list/rehearse never open hardware.

Scientific source modules and historical datasets are deliberately unchanged.
"""
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
import shutil
import time
import uuid

from .protocol import make_packet, GUARD_BITS, PREAMBLE, HEADER_BITS
from .coding_experiments import interleave
from .device import Transmitter

PLAN = Path('data/plans/physical_campaign_v1/schedule.csv')
DATA = Path('data/physical_campaign_v1')
LABELS = {'CLEAN': 'Keep everything steady', 'OCC_SPLIT': 'Three short card blocks',
          'OCC_CLUSTER': 'One longer card block', 'GLARE_BODY': 'One glare pulse',
          'LONG_PAYLOAD_CLUSTER': 'Long message + card block', 'GLARE_PREAMBLE': 'Early glare pulse'}

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    tmp.replace(path)

def wire_packet(row):
    packet = make_packet(bytes.fromhex(row['payload_hex']), row['codec'], int(row['sequence']))
    depth = int(row['interleave_depth'])
    if depth not in (1, 8): raise ValueError('Interleaving depth must be 1 or 8.')
    wire = packet.bits.copy()
    first = GUARD_BITS+len(PREAMBLE)+HEADER_BITS
    wire[first:first+len(packet.body_bits)] = interleave(packet.body_bits, depth)
    return packet, replace(packet, bits=wire)

def load_sessions(root):
    with (Path(root)/PLAN).open(newline='') as stream: rows = list(csv.DictReader(stream))
    sessions = {}
    ids = set()
    for row in rows:
        if row['packet_id'] in ids: raise ValueError('Duplicate packet identity.')
        ids.add(row['packet_id'])
        if row['phase'] not in ('pilot','calibration','main','holdout') or row['condition'] not in LABELS:
            raise ValueError('Unknown experiment phase/condition.')
        bit_ms = int(row['bit_ms'])
        if not 200 <= bit_ms <= 1000: raise ValueError('Unsupported bit duration.')
        packet, _ = wire_packet(row)
        if len(packet.bits) != int(row['packet_bits']): raise ValueError('Packet length mismatch.')
        if packet.payload.decode('utf8') != row['payload_utf8']: raise ValueError('Payload mismatch.')
        row = dict(row, events=json.loads(row['cue_events_json']))
        prior_end = 0
        total = .2+len(packet.bits)*bit_ms/1000
        body_start = .2+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*bit_ms/1000
        body_end = total-GUARD_BITS*bit_ms/1000
        for e in row['events']:
            a,b = float(e['start_after_START_ack_s']),float(e['duration_target_s'])
            if not all(math.isfinite(v) for v in (a,b)) or a<prior_end or b<=0 or a+b>=total:
                raise ValueError('Invalid disturbance interval.')
            if row['condition'] != 'GLARE_PREAMBLE' and not body_start <= a < a+b <= body_end:
                raise ValueError('Body disturbance falls outside body.')
            prior_end=a+b
        sessions.setdefault(row['session_id'], []).append(row)
    for group in sessions.values():
        if len({r['sequence'] for r in group})!=len(group): raise ValueError('Ambiguous session sequences.')
        if [int(r['packet_order']) for r in group] != list(range(1,len(group)+1)):
            raise ValueError('Invalid packet order.')
        if len({(r['phase'],r['condition']) for r in group})!=1: raise ValueError('Mixed session condition.')
    return sessions

def attempts(root):
    return [(p.parent,json.loads(p.read_text())) for p in sorted((Path(root)/DATA/'attempts').glob('*/session.json'))]

def next_session(root, phase='pilot'):
    sessions=load_sessions(root)
    prior=attempts(root)
    for sid,rows in sessions.items():
        if rows[0]['phase']!=phase: continue
        matches=[(p,r) for p,r in prior if r['session_id']==sid]
        if any(r['status']=='controller_completed' for _,r in matches): continue
        if matches:
            raise ValueError(f'{sid} has an unfinished attempt. Preserve its video; explicitly resume with a retained retake, rather than silently skipping it.')
        return sid
    return None

def check_freeze(root, phase):
    if phase in ('pilot','calibration'): return
    path=Path(root)/DATA/'analysis_freeze.json'
    if not path.exists():
        raise ValueError('Pilot review is pending. Main/challenge recording requires a documented timing/noise review and frozen settings; run the four clean pilot videos first.')
    record=json.loads(path.read_text())
    if record.get('plan_sha256')!=digest(Path(root)/PLAN) or not record.get('pilot_review') or not record.get('receiver_settings'):
        raise ValueError('The freeze record is missing its pilot review/settings or refers to a different schedule.')

def source_hashes():
    here=Path(__file__).parent
    names=['physical_campaign.py','device.py','protocol.py','coding_experiments.py']
    return {name:digest(here/name) for name in names}

class Cue:
    """Logs displayed cues relative to acknowledged START, never measured interference."""
    def __init__(self, row, display):
        self.row,self.display=row,display
        self.transitions=[]
        self.key=None
        self.last_update=-1e9
        self.start_unix=None
        self.seen=set()
    def __call__(self, elapsed, line=''):
        if self.start_unix is None: self.start_unix=time.time()-elapsed
        events=self.row['events']; active=None; upcoming=None
        for i,e in enumerate(events):
            start=e['start_after_START_ack_s'];end=start+e['duration_target_s']
            if start<=elapsed<end: active=(i,e);break
            if elapsed<start: upcoming=(i,e);break
        if line.startswith('DONE'):
            key=('done',);text='PACKET FINISHED — keep recording';target=None
        elif active:
            i,e=active;self.seen.add(i);key=('active',i);target=e['start_after_START_ack_s']
            text=('BLOCK LCD NOW' if e['kind']=='full_patch_occlusion' else 'UNCOVER LAMP BEAM NOW')
        elif upcoming and upcoming[1]['start_after_START_ack_s']-elapsed<=3:
            i,e=upcoming;key=('ready',i);target=None
            text=f'KEEP LCD CLEAR / COVER LAMP — next action in {max(1,math.ceil(e["start_after_START_ack_s"]-elapsed))}'
        else:
            key=('clear',len(self.seen));target=None
            text='KEEP LCD CLEAR / LAMP BEAM BLOCKED — keep recording'
        if key!=self.key:
            self.transitions.append(dict(state=list(key),host_seconds_after_START_ack=round(elapsed,4),
                                    target_start_seconds=target,cue_lateness_seconds=None if target is None else round(elapsed-target,4)))
            self.key=key
            changed=True
        else: changed=False
        if changed or elapsed-self.last_update>=.2:
            self.display(dict(state=key[0],text=text,packet_id=self.row['packet_id'],
                              codec=self.row['codec'],depth=self.row['interleave_depth'],
                              seconds_remaining=max(0,math.ceil(float(self.row['scheduled_channel_seconds'])+.2-elapsed))))
            self.last_update=elapsed
    def record(self):
        return dict(acknowledged_start_unix_estimate=self.start_unix,displayed_transitions=self.transitions,
                    events_without_active_display=[i for i in range(len(self.row['events'])) if i not in self.seen],
                    meaning='Host cue timing only; actual physical onset/duration requires video annotation.')

def run_session(root, session_id, port, setup, display=lambda state:None, *, retake=False,
                transmitter_factory=Transmitter, sleep=time.sleep):
    root=Path(root).resolve();rows=load_sessions(root)[session_id]
    check_freeze(root,rows[0]['phase'])
    previous=[r for _,r in attempts(root) if r['session_id']==session_id]
    if previous and not retake: raise ValueError('Attempt already exists. Use an explicit retained retake; previous results are not overwritten.')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')+'_'+uuid.uuid4().hex[:8]
    folder=root/DATA/'attempts'/(session_id+'__'+stamp);folder.mkdir(parents=True,exist_ok=False)
    plan_hash=digest(root/PLAN)
    record=dict(schema_version=1,session_id=session_id,attempt_id=folder.name,phase=rows[0]['phase'],
                condition=rows[0]['condition'],status='prepared',plan_sha256=plan_hash,source_sha256=source_hashes(),
                setup=dict(setup),retake_of=[r['attempt_id'] for r in previous],created_utc=stamp,
                association='Use this attempt ID + optical sequence; header does not contain interleaving depth.',
                video=None,packets=[dict(r,status='not_started') for r in rows],operator_notes='')
    if rows[0]['phase'] not in ('pilot','calibration'):record['analysis_freeze']=json.loads((root/DATA/'analysis_freeze.json').read_text())
    save(folder/'session.json',record)
    try:
        with transmitter_factory(port) as tx:
            tx.light(False)
            for remaining in range(5,0,-1):
                display(dict(state='ready',text=f'RECORDING STARTS IN {remaining} — phone stays recording'))
                sleep(1)
            record['status']='transmitting';save(folder/'session.json',record)
            for index,entry in enumerate(record['packets']):
                packet,wire=wire_packet(entry)
                entry.update(status='transmitting',canonical_bits=''.join(map(str,packet.bits)),
                             wire_bits=''.join(map(str,wire.bits)),interleave_depth=int(entry['interleave_depth']),
                             tx_file=f'tx_{index+1:02d}_seq{packet.sequence:03d}.json',host_called_unix=time.time())
                save(folder/'session.json',record)
                cue=Cue(entry,display)
                try:
                    tx.transmit(wire,int(entry['bit_ms']),folder/entry['tx_file'],on_progress=cue)
                    log=json.loads((folder/entry['tx_file']).read_text())
                    if log['transmitted_bits']!=entry['wire_bits']: raise ValueError('Transmitter log does not match planned wire bits.')
                    log.update(canonical_bits=entry['canonical_bits'],wire_bits=entry['wire_bits'],
                               interleave_depth=entry['interleave_depth'],packet_id=entry['packet_id'],
                               attempt_id=folder.name,condition=entry['condition'],_condition=entry['condition'])
                    save(folder/entry['tx_file'],log)
                    entry['status']='controller_completed'
                except BaseException as exc:
                    entry.update(status='failed_or_interrupted',error=f'{type(exc).__name__}: {exc}')
                    raise
                finally:
                    entry['cue_log']=cue.record()
                    entry['host_returned_unix']=time.time()
                    save(folder/'session.json',record)
                if index+1<len(rows):
                    for remaining in range(8,0,-1):
                        display(dict(state='gap',text=f'KEEP RECORDING — next packet in {remaining}; clear the LCD / block lamp beam'))
                        sleep(1)
            display(dict(state='clear',text='LAST PACKET FINISHED — keep recording for 3 seconds'))
            sleep(3)
        record['status']='controller_completed'
        display(dict(state='done',text='STOP PHONE RECORDING — this video is finished'))
    except BaseException as exc:
        record.update(status='failed_or_interrupted',error=f'{type(exc).__name__}: {exc}')
        display(dict(state='error',text='STOPPED — stop the phone and keep the partial video'))
        raise
    finally: save(folder/'session.json',record)
    return folder

def attach_video(root, folder, source):
    root=Path(root).resolve();folder=Path(folder).resolve();source=Path(source).expanduser().resolve()
    folder.relative_to(root/DATA/'attempts')
    record=json.loads((folder/'session.json').read_text())
    if record.get('video'): raise ValueError('A video is already attached; never overwrite it.')
    if source.suffix.lower() not in ('.mov','.mp4','.avi') or not source.is_file():
        raise ValueError('Select an original MOV, MP4 or AVI file.')
    sha=digest(source)
    for _,other in attempts(root):
        if (other.get('video') or {}).get('sha256')==sha:
            raise ValueError('This video is already assigned to a trial; it is not a new replicate.')
    dest=folder/('original'+source.suffix.lower())
    # Exclusive destination; a failed copy is never mistaken for an attached video.
    with source.open('rb') as inp, dest.open('xb') as out: shutil.copyfileobj(inp,out)
    if digest(dest)!=sha: raise IOError('Copied-video hash mismatch.')
    record['video']=dict(path=dest.name,sha256=sha,source_filename=source.name,
                         bytes=dest.stat().st_size,association='Operator selected; verify against optical sequence/session before analysis.',
                         raw_video_validation='pending')
    save(folder/'session.json',record)
    return dest
