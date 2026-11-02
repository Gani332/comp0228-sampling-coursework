"""Depth-aware pilot decoder. Receives brightness and public settings, never truth.

Does not alter the historical receiver. Nominal timing is an explicitly labelled
pilot diagnostic, not an automatically selected answer or validated improvement.
"""
import numpy as np
from .receiver import _trace, find_preamble, sample_slots
from .protocol import PREAMBLE, HEADER_BITS, parse_header, body_length, unpack_body
from .coding_experiments import deinterleave

def decode_pilot(times, brightness, *, depth=1, bit_ms=200, timing='estimated'):
    if depth not in (1,8) or timing not in ('estimated','nominal_diagnostic'):
        raise ValueError('Unsupported public decoder configuration.')
    result=dict(failure_stage='acquisition',timing_policy=timing,interleave_depth=depth)
    try:
        t,y=_trace(times,brightness)
        sync=find_preamble(t,y,bit_ms)
        result['estimated_period_seconds']=sync['period_seconds']
        if timing=='nominal_diagnostic':sync=dict(sync,period_seconds=bit_ms/1000)
        result.update(sync)
        result['failure_stage']='header'
        start,period=sync['start_seconds'],sync['period_seconds']
        vals,_=sample_slots(t,y,start,period,range(len(PREAMBLE),len(PREAMBLE)+HEADER_BITS))
        h=parse_header((vals>sync['threshold']).astype(np.uint8))
        result.update({k:h[k] for k in ('codec','sequence','payload_bytes')})
        first=len(PREAMBLE)+HEADER_BITS;n=body_length(h['payload_bytes'],h['codec'])
        result['failure_stage']='body_sampling'
        vals,counts=sample_slots(t,y,start,period,range(first,first+n))
        wire=(vals>sync['threshold']).astype(np.uint8)
        body=deinterleave(wire,depth)
        result.update(wire_body_bits=wire,body_bits=body,body_sample_values=vals,body_sample_counts=counts,failure_stage='fec')
        result.update(unpack_body(h,body))
        result.update(failure_stage=None,text=result['payload'].decode('utf8',errors='replace'))
    except ValueError as exc:result['failure_reason']=str(exc)
    return result
