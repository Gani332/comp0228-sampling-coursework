"""Depth-aware Mac campaign decoder using the public transmitter bit duration.

The pilot showed that extrapolating a clock fitted to a short preamble can drift
across a packet. The campaign therefore uses configured timing by default, with
optical acquisition/thresholds still recovered from the public preamble. This
choice is made before decoding, never selected by payload truth or CRC success.
Estimated timing and the original nominal diagnostic remain explicit comparisons.
"""
import numpy as np
from .receiver import _trace, find_preamble, sample_slots
from .protocol import PREAMBLE, HEADER_BITS, parse_header, body_length, unpack_body
from .coding_experiments import deinterleave


def decode_pilot(times, brightness, *, depth=1, bit_ms=200, timing='configured'):
    if depth not in (1,8) or timing not in ('configured','estimated','nominal_diagnostic'):
        raise ValueError('Unsupported public decoder configuration.')
    result=dict(failure_stage='acquisition',timing_policy=timing,interleave_depth=depth,
                configured_bit_ms=bit_ms)
    try:
        t,y=_trace(times,brightness)
        sync=find_preamble(t,y,bit_ms)
        result['estimated_period_seconds']=sync['period_seconds']
        if timing in ('configured','nominal_diagnostic'):
            sync=dict(sync,period_seconds=bit_ms/1000)
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
        result['text']=result['payload'].decode('utf8',errors='replace')
        if result['crc_ok']:
            result['failure_stage']=None
        else:
            result.update(failure_stage='crc',failure_reason='Payload CRC failed.')
    except ValueError as exc:result['failure_reason']=str(exc)
    return result
