"""Frozen November front ends with configured clock and known interleaver depth.

No payload truth or transmit timestamps enter this API. Acquisition is shared
with the primary ROI: this ablation cannot rescue primary acquisition failure.
Historical receiver_layers and the frozen primary implementation are unchanged.
"""
import numpy as np
from .receiver import _trace,find_preamble,sample_slots
from .receiver_layers import processed_signal,preamble_samples
from .physical_campaign_receiver import decode_pilot
from .protocol import PREAMBLE,HEADER_BITS,parse_header,body_length,unpack_body
from .coding_experiments import deinterleave

METHODS=('original','patch_mean','reference','spatial','combined','ewma','kalman')

def temporal(t,y,method):
    # Fixed Nov 7 settings; no model fitting or parameter search.
    out=np.empty_like(y,dtype=float);out[0]=y[0];p=400.
    for i in range(1,len(t)):
        dt=t[i]-t[i-1]
        if method=='ewma':gain=-np.expm1(-dt/.025)
        elif method=='kalman':
            prior=p+160000.*dt;gain=prior/(prior+400.);p=(1-gain)*prior
        else:raise ValueError('Unknown temporal method')
        out[i]=out[i-1]+gain*(y[i]-out[i-1])
    return out

def decode(times,features,method='original',*,depth=1,bit_ms=200):
    if method not in METHODS or depth not in (1,8): raise ValueError('Unknown configuration')
    if method=='original':return decode_pilot(times,features['original'],depth=depth,bit_ms=bit_ms)
    result={'failure_stage':'acquisition','method':method,'timing_policy':'configured','interleave_depth':depth}
    try:
        t,y=_trace(times,features['original']);sync=find_preamble(t,y,bit_ms)
        sync=dict(sync,period_seconds=bit_ms/1000);result.update(sync)
        result['failure_stage']='calibration'
        if method in ('ewma','kalman'):
            signal=temporal(t,np.asarray(features['patch_mean'],float),method)
        else:signal,_=processed_signal(t,features,method,sync,alpha=1.,quantile=.25)
        s=preamble_samples(t,signal,sync).ravel()
        low,high=(float(np.median(s[PREAMBLE==b])) for b in (0,1))
        if high-low<20: raise ValueError('Insufficient processed preamble contrast')
        threshold=(low+high)/2
        if np.count_nonzero((s>threshold)!=PREAMBLE)>1:raise ValueError('Processed preamble is damaged')
        result.update(threshold=threshold,dark_level=low,bright_level=high)
        start,period=sync['start_seconds'],sync['period_seconds'];first=len(PREAMBLE)
        result['failure_stage']='header'
        vals,_=sample_slots(t,signal,start,period,range(first,first+HEADER_BITS))
        h=parse_header((vals>threshold).astype(np.uint8));result.update(h)
        result['failure_stage']='body_sampling';first+=HEADER_BITS
        vals,counts=sample_slots(t,signal,start,period,range(first,first+body_length(h['payload_bytes'],h['codec'])))
        wire=(vals>threshold).astype(np.uint8);body=deinterleave(wire,depth)
        result.update(wire_body_bits=wire,body_bits=body,body_sample_counts=counts,failure_stage='fec')
        result.update(unpack_body(h,body))
        result['failure_stage']=None if result['crc_ok'] else 'crc'
    except ValueError as e:result['failure_reason']=str(e)
    return result
