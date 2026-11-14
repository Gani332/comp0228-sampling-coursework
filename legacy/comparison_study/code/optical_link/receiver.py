"""Decode one packet from a timestamped brightness trace, without sent data.

This initial receiver uses a fixed ROI, one preamble, and a fitted fixed clock.
Use short messages first. It intentionally reports missing samples/CRC failures.
"""
import numpy as np
from .protocol import PREAMBLE, HEADER_BITS, parse_header, body_length, unpack_body


def _trace(times, brightness):
    t, y = np.asarray(times, float), np.asarray(brightness, float)
    if t.ndim != 1 or y.shape != t.shape or len(t) < 40:
        raise ValueError('Need at least 40 timestamped brightness measurements.')
    if not np.isfinite(t).all() or not np.isfinite(y).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Timestamps must increase strictly; samples must be finite.')
    return t, y


def sample_slots(t, y, start, period, indices):
    values, counts = [], []
    for i in indices:
        # Middle half avoids LCD scan-out transitions and camera exposure mixing.
        left, right = start + (i+.25)*period, start + (i+.75)*period
        a, b = np.searchsorted(t, [left, right])
        if a == b:
            raise ValueError(f'Missing camera samples in bit slot {i}; packet incomplete.')
        values.append(float(np.median(y[a:b])))
        counts.append(int(b-a))
    return np.array(values), np.array(counts)


def find_preamble(t, y, bit_ms=200):
    nominal = bit_ms/1000
    if not 200 <= bit_ms <= 1000:
        raise ValueError('Use the public transmitter bit duration, 200..1000 ms.')
    lo, hi = np.percentile(y, [5, 95])
    if hi-lo < 20:
        raise ValueError('Too little brightness contrast. Check ROI, exposure and recording.')
    level = (lo+hi)/2
    binary = y > level
    changes = np.flatnonzero(binary[1:] != binary[:-1])+1
    # Linear crossing estimate within the pair of camera samples.
    edges = t[changes-1] + ((level-y[changes-1]) / (y[changes]-y[changes-1])) * (t[changes]-t[changes-1])
    rises = edges[binary[changes]]
    starts = rises[rises+(len(PREAMBLE)-.25)*nominal < t[-1]]
    if not len(starts):
        raise ValueError('No complete optical start pattern. Record before transmission starts.')
    best = None
    # Coarse optical match only. No CRC, known payload, or transmitter time is used.
    offsets = np.linspace(-.25, .25, 11)*nominal
    periods = nominal*np.linspace(.97, 1.03, 31)
    for rise in starts:
        s, p = np.meshgrid(rise+offsets, periods)
        centres = s.ravel()[:, None] + (np.arange(len(PREAMBLE))+.5)*p.ravel()[:, None]
        values = np.interp(centres.ravel(), t, y).reshape(centres.shape)
        normalized = np.clip((values-lo)/(hi-lo), 0, 1)
        scores = np.mean((normalized-PREAMBLE)**2, axis=1)
        k = int(np.argmin(scores))
        # Prefer the nominal clock in exact ties; edge fitting below refines it.
        near = np.flatnonzero(scores <= scores[k]+1e-10)
        k = int(near[np.argmin(abs(p.ravel()[near]-nominal)+abs(s.ravel()[near]-rise)/100)])
        candidate = (float(scores[k]), float(s.ravel()[k]), float(p.ravel()[k]))
        if best is None or candidate[0] < best[0]:
            best = candidate
    score, start, period = best
    if score > .10:
        raise ValueError('Could not identify the public optical preamble.')
    # Fit observed preamble transitions to recover a precise clock. Edge zero
    # is the leading rise after the dark guard. Reject transitions far from it.
    indices = np.r_[0, np.flatnonzero(PREAMBLE[1:] != PREAMBLE[:-1])+1]
    ix, observed = [], []
    for i in indices:
        expected = start+i*period
        edge = edges[np.argmin(abs(edges-expected))]
        if abs(edge-expected) < .35*period:
            ix.append(i)
            observed.append(edge)
    if len(ix) < 12:
        raise ValueError('Too few clear transitions to recover the optical clock.')
    period, start = np.polyfit(ix, observed, 1)
    if abs(period/nominal-1) > .04:
        raise ValueError('Recovered clock differs too much from the configured bit rate.')
    residual = np.asarray(observed) - (start+np.asarray(ix)*period)
    if np.max(abs(residual)) > .3*period:
        raise ValueError('Unstable preamble timing; check video gaps and exposure.')
    values, _ = sample_slots(t, y, start, period, range(len(PREAMBLE)))
    low = float(np.median(values[PREAMBLE == 0]))
    high = float(np.median(values[PREAMBLE == 1]))
    if high-low < 20:
        raise ValueError('Preamble contrast is too low.')
    threshold = (low+high)/2
    errors = int(np.count_nonzero((values>threshold) != PREAMBLE))
    if errors > 1:
        raise ValueError('Preamble is too damaged to synchronize reliably.')
    return {'start_seconds': float(start), 'period_seconds': float(period),
            'threshold': threshold, 'dark_level': low, 'bright_level': high,
            'preamble_bit_errors': errors, 'edge_residual_rms_seconds': float(np.sqrt(np.mean(residual**2)))}


def decode_trace(times, brightness, bit_ms=200):
    t, y = _trace(times, brightness)
    sync = find_preamble(t, y, bit_ms)
    start, period, threshold = (sync[k] for k in ('start_seconds', 'period_seconds', 'threshold'))
    first = len(PREAMBLE)
    header_values, _ = sample_slots(t, y, start, period, range(first, first+HEADER_BITS))
    header = parse_header((header_values > threshold).astype(np.uint8))
    body_start = first+HEADER_BITS
    n = body_length(header['payload_bytes'], header['codec'])
    values, counts = sample_slots(t, y, start, period, range(body_start, body_start+n))
    decoded = unpack_body(header, (values>threshold).astype(np.uint8))
    decoded.update(sync)
    decoded['body_sample_values'] = values
    decoded['body_sample_counts'] = counts
    decoded['body_sample_times'] = start+(np.arange(body_start, body_start+n)+.5)*period
    decoded['low_confidence_body_bits'] = int(np.count_nonzero(abs(values-threshold) < .15*(sync['bright_level']-sync['dark_level'])))
    decoded['text'] = decoded['payload'].decode('utf-8', errors='replace')
    return decoded


def synthetic_trace(packet, bit_ms=200, fps=30, seed=8, drop_fraction=.04, noise=4):
    """Synthetic software check only: never evidence of a physical link."""
    rng = np.random.default_rng(seed)
    period = bit_ms/1000
    t = np.arange(0, len(packet.bits)*period+4, 1/fps)
    t += rng.uniform(-.001, .001, len(t))
    t -= t[0]
    t = t[rng.random(len(t)) >= drop_fraction]
    # Capture begins two seconds before the packet; LCD transition has a delay.
    slot = np.floor((t-2-.015)/period).astype(int)
    valid = (slot >= 0) & (slot < len(packet.bits))
    b = np.zeros(len(t))
    b[valid] = packet.bits[slot[valid]]
    y = 25+180*b+rng.normal(0, noise, len(t))
    return t, np.clip(y, 0, 255)
