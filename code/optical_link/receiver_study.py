"""Local, reproducible receiver study on cached physical-video features."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .receiver_layers import decode_features, METHODS
from .baseline_analysis import assess_received


def json_value(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,np.generic): return x.item()
    if isinstance(x,bytes): return x.hex()
    raise TypeError(type(x).__name__)


def save_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,default=json_value)+'\n')


def evaluate(root,study,method,cohorts=None,alpha=1.0,quantile=.5,save_to=None):
    root,study=Path(root),Path(study)
    manifest=json.loads((study/'manifest.json').read_text())
    rows=[]
    if save_to:
        save_to=Path(save_to);save_to.mkdir(parents=True,exist_ok=False)
    for video in manifest:
        if cohorts is not None and video['cohort'] not in cohorts: continue
        file=study/'features'/(video['id']+'.npz')
        meta=json.loads(file.with_suffix('.json').read_text())
        if hashlib.sha256(file.read_bytes()).hexdigest()!=meta['feature_sha256']:
            raise ValueError('Feature cache hash changed: '+video['id'])
        if meta['video_sha256']!=video['sha256'] or meta['study_roi']!=video['study_roi'] or meta['reference_rois']!=video['reference_rois']:
            raise ValueError('Feature geometry or source-video provenance changed.')
        with np.load(file) as z:
            t=z['times'];features={k:z[k] for k in ['original','patch_mean','tiles','references']}
        for packet in video['packets']:
            mask=np.ones(len(t),bool) if packet['window'] is None else (t>=packet['window'][0])&(t<=packet['window'][1])
            # Receiver receives measured pixels, clock rate and front-end settings only.
            rx=decode_features(t[mask],{k:a[mask] for k,a in features.items()},method,200,alpha,quantile)
            # Ground truth enters only after the receiver returns its answer.
            tx=json.loads((root/packet['tx']).read_text())
            m=assess_received(rx,tx)
            m.update(trial_id=packet['id'],video_id=video['id'],cohort=video['cohort'],
                     method=method,alpha=alpha,quantile=quantile,
                     condition=packet['expected'].get('condition','noisy'),
                     original_roi=video['original_roi'],study_roi=video['study_roi'])
            if method=='original':
                for key in ['body_channel_bit_errors','payload_bit_errors','crc_ok','packet_failed']:
                    if m[key]!=packet['expected'][key]:
                        raise AssertionError(f"Archived baseline differs: {packet['id']} {key}")
            rows.append(m)
            if save_to:
                save_json(save_to/(packet['id']+'_receiver.json'),rx)
    if save_to:save_json(save_to/'metrics.json',rows)
    return rows


def summarize(rows):
    channel=[r for r in rows if r['body_channel_bit_errors'] is not None]
    payload=[r for r in rows if r['payload_bit_errors'] is not None]
    channel_bits=sum(r['body_channel_bits'] for r in channel)
    payload_bits=sum(r['payload_bits'] for r in payload)
    seconds=sum(r['channel_seconds_including_overhead'] for r in rows)
    channel_errors=sum(r['body_channel_bit_errors'] for r in channel)
    payload_errors=sum(r['payload_bit_errors'] for r in payload)
    return {'packets':len(rows),'successes':sum(not r['packet_failed'] for r in rows),
            'failures':sum(bool(r['packet_failed']) for r in rows),
            'clean_failures':sum(r['condition']=='clean' and r['packet_failed'] for r in rows),
            'channel_outputs':len(channel),'channel_errors':channel_errors,'channel_bits':channel_bits,
            'channel_ber':channel_errors/channel_bits if channel_bits else None,
            'payload_outputs':len(payload),'payload_errors':payload_errors,'payload_bits_with_output':payload_bits,
            'payload_ber_with_output':payload_errors/payload_bits if payload_bits else None,
            'airtime_seconds':seconds,
            'goodput_bps':sum(r['correct_delivered_bits'] for r in rows)/seconds if seconds else 0,
            'association_errors':sum(r['status']=='association_error' for r in rows)}


def selection_score(summary):
    # First protect clean controls, then prioritize complete-packet delivery.
    # BER is only a tie breaker; a missing output is never treated as zero errors.
    return (summary['clean_failures'],summary['failures'],
            summary['packets']-summary['channel_outputs'],
            summary['channel_ber'] if summary['channel_ber'] is not None else 1.)
