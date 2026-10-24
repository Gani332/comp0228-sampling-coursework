"""Baseline diagnostics; transmitted data is used only after optical decoding.

Uses the unchanged receiver. On a rejected packet, repeats its acquisition steps
solely to retain raw body measurements and distinguish an FEC rejection.
"""
import numpy as np
from optical_link.receiver import decode_trace, _trace, find_preamble, sample_slots
from optical_link.protocol import (GUARD_BITS, PREAMBLE, HEADER_BITS, parse_header,
                                   body_length, to_bits)


def receive_diagnostic(times, brightness, bit_ms=200):
    try:
        result = decode_trace(times, brightness, bit_ms)
        result['failure_stage'] = None
        return result
    except ValueError as error:
        result = {'failure_reason': str(error), 'failure_stage': 'acquisition'}
    try:
        t, y = _trace(times, brightness)
        sync = find_preamble(t, y, bit_ms)
        result.update(sync)
        start, period, threshold = (sync[k] for k in ('start_seconds', 'period_seconds', 'threshold'))
        result['failure_stage'] = 'header'
        first = len(PREAMBLE)
        values, _ = sample_slots(t, y, start, period, range(first, first+HEADER_BITS))
        header = parse_header((values > threshold).astype(np.uint8))
        result.update({k: header[k] for k in ('codec', 'sequence', 'payload_bytes')})
        result['failure_stage'] = 'body_sampling'
        first += HEADER_BITS
        n = body_length(header['payload_bytes'], header['codec'])
        values, counts = sample_slots(t, y, start, period, range(first, first+n))
        result.update(body_bits=(values > threshold).astype(np.uint8),
                      body_sample_values=values, body_sample_counts=counts,
                      body_sample_times=start+(np.arange(first, first+n)+.5)*period,
                      failure_stage='fec')
    except ValueError:
        pass
    return result


def error_structure(sent, received, codec):
    mask = np.asarray(sent) != np.asarray(received)
    indices = np.flatnonzero(mask)
    runs = np.split(indices, np.flatnonzero(np.diff(indices) > 1)+1) if len(indices) else []
    result = {'body_error_indices': indices.tolist(),
              'consecutive_error_runs': [{'start': int(r[0]), 'length': len(r)} for r in runs],
              'max_consecutive_errors': max([len(r) for r in runs], default=0),
              'zero_to_one_errors': int(np.count_nonzero(mask & (np.asarray(sent) == 0))),
              'one_to_zero_errors': int(np.count_nonzero(mask & (np.asarray(sent) == 1)))}
    width = {'repeat3': 3, 'repeat5': 5, 'hamming74': 7, 'rs4': 8}.get(codec)
    if width:
        blocks = mask.reshape(-1, width).sum(axis=1)
        result['errors_per_code_block'] = blocks.tolist()
        result['damaged_code_blocks'] = int(np.count_nonzero(blocks))
        if codec.startswith('repeat'):
            result['blocks_exceeding_guaranteed_correction'] = int(np.count_nonzero(blocks > width//2))
        elif codec == 'hamming74':
            result['blocks_exceeding_guaranteed_correction'] = int(np.count_nonzero(blocks > 1))
        else:
            result['damaged_rs_bytes'] = int(np.count_nonzero(blocks))
    return result


def assess_received(received, tx):
    """Ground truth enters here, after the receiver has produced its result."""
    payload = bytes.fromhex(tx['payload_hex'])
    bits = np.array([int(b) for b in tx['transmitted_bits']], dtype=np.uint8)
    sent = bits[GUARD_BITS+len(PREAMBLE)+HEADER_BITS:-GUARD_BITS]
    seconds = tx['scheduled_channel_seconds']
    m = {'codec': tx['codec'], 'message': payload.decode('utf8', errors='replace'),
         'sequence': tx['sequence'], 'status': 'decode_failed', 'packet_failed': True,
         'failure_stage': received.get('failure_stage'), 'reason': received.get('failure_reason'),
         'body_channel_bit_errors': None, 'body_channel_bits': len(sent), 'body_channel_ber': None,
         'payload_bit_errors': None, 'payload_bits': len(payload)*8, 'payload_ber': None,
         'received_text': None, 'crc_ok': None, 'exact_payload_match': None,
         'channel_seconds_including_overhead': seconds,
         'offered_payload_rate_bps': len(payload)*8/seconds,
         'correct_delivered_bits': 0, 'correct_payload_goodput_bps': 0.0}
    if 'sequence' in received and (received['sequence'], received['codec']) != (tx['sequence'], tx['codec']):
        m.update(status='association_error', reason='Optical header does not match the selected transmission.')
        return m
    if 'body_bits' in received:
        body = received['body_bits']
        if len(body) != len(sent):
            m.update(status='association_error', reason='Body length does not match the selected transmission.')
            return m
        errors = int(np.count_nonzero(sent != body))
        m.update(body_channel_bit_errors=errors, body_channel_ber=errors/len(sent))
        m.update(error_structure(sent, body, tx['codec']))
        # A same-denominator before/after check is possible for systematic codes.
        if tx['codec'] in ('hamming74', 'rs4', 'none'):
            raw_data = (body.reshape(-1,7)[:,[2,4,5,6]].ravel()
                        if tx['codec']=='hamming74' else body)
            m['systematic_payload_errors_before_correction'] = int(np.count_nonzero(raw_data[:len(payload)*8] != to_bits(payload)))
        counts = received['body_sample_counts']
        m.update(min_samples_per_body_bit=int(min(counts)), max_samples_per_body_bit=int(max(counts)))
    if 'payload' in received:
        if len(received['payload']) != len(payload):
            m.update(status='association_error', reason='Payload length mismatch.')
            return m
        errors = int(np.count_nonzero(to_bits(payload) != to_bits(received['payload'])))
        valid, exact = bool(received['crc_ok']), received['payload'] == payload
        delivered = len(payload)*8*bool(valid and exact)
        m.update(status='crc_pass' if valid else 'crc_fail', received_text=received['text'],
                 payload_bit_errors=errors, payload_ber=errors/(len(payload)*8),
                 crc_ok=valid, exact_payload_match=exact, packet_failed=not(valid and exact),
                 correct_delivered_bits=delivered, correct_payload_goodput_bps=delivered/seconds)
    return m
