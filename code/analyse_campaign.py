"""Reconcile November physical evidence; expected data is used only for scoring.

Run from any directory: python optical_link/code/analyse_campaign.py
Inputs: immutable review traces/audits and the campaign's actual attempt logs.
Outputs: portable evidence snapshots, packet CSVs, manifest and descriptive tables.
Unprovided remote logs remain explicitly provisional; no depth is inferred from CRC.
"""
from pathlib import Path
import hashlib, json, shutil
import numpy as np
import pandas as pd
from optical_link.physical_campaign import load_sessions, wire_packet
from optical_link.protocol import GUARD_BITS, PREAMBLE, HEADER_BITS
from optical_link.coding_experiments import deinterleave

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
OUT = PROJECT/'data/analysis/physical_campaign_2026-11-08'
REV = ROOT/'reviews'
SESSIONS = load_sessions(PROJECT)
SIDS = list(SESSIONS)

def read(p): return json.loads(Path(p).read_text())
def save(p, value): Path(p).write_text(json.dumps(value, indent=2, default=lambda x:x.item() if isinstance(x,np.generic) else x.tolist())+'\n')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def sources(n, original=False):
    if n<8: folder=REV/'2026-11-07_noise_calibration_recheck'; name='audit.json'
    elif n==8: folder=REV/'2026-11-07_video8_review';name='audit.json'
    elif n==9: folder=REV/('2026-11-07_videos8_9_10_review' if original else '2026-11-07_video9_blocked_review');name='Video9_audit.json'
    elif n==10: folder=REV/'2026-11-07_videos8_9_10_review';name='Video10_audit.json'
    elif n in (11,12,19) and not original: folder=REV/'2026-11-08_retakes11_12_19_review';name=f'Video{n}_audit.json'
    else: folder=REV/'2026-11-08_videos11_21_review';name=f'Video{n}_audit.json'
    a=read(folder/name)
    if n<8: a=next(x for x in a['unique_video_results'] if x['video'].startswith(f'Video{n}.'))
    meta=a.get('trace') or read(folder/f'Video{n}_trace.json')
    reconciliation=OUT/'omar_log_reconciliation.json'
    if reconciliation.exists():
        match=read(reconciliation)['matches_by_video_sha256'].get(meta['sha256'])
        if match:
            assert sha(PROJECT/match['session_path'])==match['session_sha256'], 'Imported log changed'
            a=read(PROJECT/match['audit'])
            assert a['trace']['sha256']==meta['sha256'], 'Reconciliation belongs to a different video'
    return folder,a,meta

def normalize(n,a,meta, cohort):
    sid=a['session_id']; attempt=a.get('attempt_id')
    planned=SESSIONS[sid]; verified=False
    if attempt:
        p=(PROJECT/a['transmitter_log_path'] if a.get('transmitter_log_path') else
           PROJECT/'data/physical_campaign_mac_v1/attempts'/attempt/'session.json')
        if p.exists(): planned=read(p)['packets'];verified=True
    found={int(r['sequence']):r for r in a['packets']}
    rows=[]
    for sent in planned:
        seq=int(sent['sequence']);r=found.get(seq, {})
        _,wire=wire_packet(sent)
        if verified: assert ''.join(map(str,wire.bits))==sent['wire_bits']
        truth=wire.bits[GUARD_BITS+len(PREAMBLE)+HEADER_BITS:-GUARD_BITS]
        depth=int(sent['interleave_depth']); nbits=len(truth)
        errors=r.get('error_bit_indices')
        mask=None
        if errors is not None:
            assert len(errors)==r['body_bit_errors']
            mask=np.zeros(nbits,dtype=np.uint8);mask[errors]=1
        runs=[]
        if mask is not None:
            padded=np.r_[0,mask,0];starts=np.flatnonzero(np.diff(padded.astype(int))==1);ends=np.flatnonzero(np.diff(padded.astype(int))==-1)
            runs=(ends-starts).tolist()
        delivered=bool(r.get('crc_ok',False) and r.get('exact_message',False))
        remote=(n in range(13,19) or n>=20 or (cohort=='earliest_available_completed' and n in (11,12,19)))
        row=dict(cohort=cohort,video=n,session_id=sid,sequence=seq,
            phase='calibration' if n<8 else ('main' if n<20 else 'holdout'),condition=sent['condition'],
            codec=sent['codec'],depth=depth,payload_bytes=int(sent['payload_bytes']),payload_hex=sent['payload_hex'],
            success=delivered,crc_ok=bool(r.get('crc_ok',False)),exact_message=bool(r.get('exact_message',False)),
            acquired=bool(r),failure_stage=r.get('failure_stage') if r else 'acquisition_or_header',
            body_bits=nbits,body_errors=r.get('body_bit_errors'),error_indices=errors,error_runs=runs,
            zero_to_one=int(np.sum(truth[errors]==0)) if errors is not None else None,
            one_to_zero=int(np.sum(truth[errors]==1)) if errors is not None else None,
            preamble_start=r.get('preamble_start_seconds'),airtime_seconds=len(wire.bits)*.2,
            mac_transmit_seconds=len(wire.bits)*.2+.2,delivered_bits=int(sent['payload_bytes'])*8*delivered,
            logs_verified=verified,attempt_id=attempt,video_sha256=meta['sha256'],
            phone='iPhone 15 Pro' if remote else 'iPhone 15',
            operator='Omar' if remote else 'local recorder',
            reference_caveat='Blocker overlaps reference regions; inspect robustness separately' if sent['condition'].startswith('OCC') else 'References visible; illumination may be non-common-mode')
        if mask is not None:
            decoded_mask=deinterleave(mask,depth)
            width={'none':1,'repeat3':3,'repeat5':5,'hamming74':7,'rs4':8}[sent['codec']]
            counts=decoded_mask.reshape(-1,width).sum(axis=1)
            row['max_errors_per_correction_group']=int(counts.max())
            row['affected_correction_groups']=int((counts>0).sum())
            row['correction_group_errors']=counts[counts>0].tolist()
        rows.append(row)
    return rows

def summarize(rows, keys):
    f=pd.DataFrame(rows); out=[]
    for labels,g in f.groupby(keys,dropna=False,sort=True):
        if not isinstance(labels,tuple): labels=(labels,)
        available=g.body_errors.notna()
        bits=int(g.loc[available,'body_bits'].sum());errors=int(g.loc[available,'body_errors'].sum())
        out.append(dict(zip(keys,labels),packets=len(g),successes=int(g.success.sum()),
            acquired=int(g.acquired.sum()),errors=errors,observed_body_bits=bits,
            conditional_ber=errors/bits if bits else None,
            goodput_bps=float(g.delivered_bits.sum()/g.airtime_seconds.sum()),
            all_logs_verified=bool(g.logs_verified.all())))
    return out

def main():
    (OUT/'evidence').mkdir(parents=True,exist_ok=True)
    freeze=read(PROJECT/'data/physical_campaign_mac_v1/analysis_freeze.json')
    assert sha(PROJECT/'code/optical_link/physical_campaign_receiver.py')==freeze['receiver_settings']['receiver_source_sha256']
    assert sha(PROJECT/'data/plans/physical_campaign_v1/schedule.csv')==freeze['plan_sha256']
    rows=[];manifest=[]
    for n in range(1,5):
        folder=REV/'2026-11-07_physical_pilot_review'
        meta=read(folder/f'Video{n}_trace.json')
        raw=next(p for p in (ROOT/'Data').iterdir() if p.stem.lower()==f'video{n}')
        assert sha(raw)==meta['sha256'],f'Stale pilot evidence for Video{n}'
        shutil.copyfile(folder/f'Video{n}_trace.npz',OUT/f'evidence/Video{n}_trace.npz')
        save(OUT/f'evidence/Video{n}_trace.json',dict(meta,video=f'Data/{raw.name}'))
        manifest.append(dict(video=n,path=f'Data/{raw.name}',sha256=meta['sha256'],audit_source=str(folder.relative_to(ROOT)),
            trace_sha256=sha(OUT/f'evidence/Video{n}_trace.npz'),frames=meta['frames'],
            max_frame_gap=meta['max_frame_interval'],duration=meta['duration'],logs_verified=True))
    for n in range(5,22):
        folder,a,meta=sources(n)
        raw=next(p for p in (ROOT/'Data').iterdir() if p.stem.lower()==f'video{n}')
        actual=sha(raw);assert actual==meta['sha256'],f'Stale evidence for Video{n}'
        rows+=normalize(n,a,meta,'selected_current')
        save(OUT/f'evidence/Video{n}_audit.json',a)
        shutil.copyfile(folder/f'Video{n}_trace.npz',OUT/f'evidence/Video{n}_trace.npz')
        save(OUT/f'evidence/Video{n}_trace.json',dict(meta,video=f'Data/{raw.name}'))
        geom=folder/(f'Video{n}_geometry_selection.json' if n!=8 else 'geometry_selection.json')
        if geom.exists(): shutil.copyfile(geom,OUT/f'evidence/Video{n}_geometry.json')
        manifest.append(dict(video=n,path=f'Data/{raw.name}',sha256=actual,audit_source=str(folder.relative_to(ROOT)),
            trace_sha256=sha(OUT/f'evidence/Video{n}_trace.npz'),frames=meta['frames'],
            max_frame_gap=meta['max_frame_gap'],duration=meta['duration'],
            logs_verified=all(r['logs_verified'] for r in rows if r['video']==n)))
        print(f'Verified Video{n}',flush=True)
    save(OUT/'packets.json',rows)
    pd.DataFrame(rows).to_csv(OUT/'packets.csv',index=False)
    save(OUT/'manifest.json',dict(videos=manifest,operator_confirmation='User: Omar recorded remote clips using iPhone 15 Pro',
        policy='Selected current recordings; retakes are replacements, not independent replicates. Original-attempt sensitivity separate. Remote log verification is matched by video hash; acquisition failures use capture-time association, without decoded header identities.',
        freeze_sha256=sha(PROJECT/'data/physical_campaign_mac_v1/analysis_freeze.json')))
    shutil.copyfile(PROJECT/'data/physical_campaign_mac_v1/analysis_freeze.json',OUT/'evidence/analysis_freeze.json')
    pilot=read(REV/'2026-11-07_receiver_timing_fix/physical_replay.json')
    save(OUT/'evidence/pilot_replay.json',pilot)
    prior=[]
    for n in range(8,20):
        folder,a,meta=sources(n,original=n in (9,11,12,19))
        prior+=normalize(n,a,meta,'earliest_available_completed')
    save(OUT/'earlier_attempt_packets.json',prior)
    summary=dict(by_phase=summarize(rows,['phase']),by_condition_code=summarize(rows,['phase','condition','codec','depth']),
        by_setup=summarize([r for r in rows if r['phase']=='main'],['condition','phone']),
        earlier_completed_sensitivity=summarize(prior,['condition']),
        caveat='Earlier cohort includes wrong-condition Video9 and differing reference framing; not an intention-to-treat account of all interrupted attempts.')
    save(OUT/'summary.json',summary)
    pd.DataFrame(summary['by_condition_code']).to_csv(OUT/'summary.csv',index=False)
    print((OUT/'summary.json').read_text())

if __name__=='__main__':main()
