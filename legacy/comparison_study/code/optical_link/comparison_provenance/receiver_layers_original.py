"""Receiver front-end ablations with shared optical timing and no sent data.

Original ROI -> public-preamble clock. All new methods use the same larger
geometric patch support. They differ only in brightness processing. Payloads,
expected bits and transmission logs are deliberately absent from this API.
"""
import numpy as np
from .receiver import _trace, find_preamble, sample_slots
from .baseline_analysis import receive_diagnostic
from .protocol import PREAMBLE, HEADER_BITS, parse_header, body_length, unpack_body

METHODS = ('original', 'patch_mean', 'reference', 'spatial', 'combined')


def preamble_samples(t, matrix, sync):
    matrix = np.asarray(matrix, float)
    if matrix.ndim == 1:
        matrix = matrix[:, None]
    return np.column_stack([sample_slots(t, matrix[:, i], sync['start_seconds'],
                                         sync['period_seconds'], range(len(PREAMBLE)))[0]
                            for i in range(matrix.shape[1])])


def processed_signal(t, features, method, sync, alpha=1.0, quantile=.5):
    if method not in METHODS:
        raise ValueError('Unknown front-end method.')
    if not np.isfinite(alpha) or not 0 <= alpha <= 2:
        raise ValueError('Reference gain must be finite and in [0,2].')
    if not np.isfinite(quantile) or not 0 < quantile < 1:
        raise ValueError('Spatial quantile must be strictly between zero and one.')
    original = np.asarray(features['original'], float)
    patch = np.asarray(features['patch_mean'], float)
    tiles = np.asarray(features['tiles'], float)
    references = np.asarray(features['references'], float)
    if original.shape != t.shape or patch.shape != t.shape:
        raise ValueError('One original and patch mean are required per timestamp.')
    if tiles.ndim != 2 or tiles.shape[0] != len(t) or tiles.shape[1] < 4:
        raise ValueError('Need at least four spatial tiles per frame.')
    if references.ndim != 2 or references.shape[0] != len(t) or references.shape[1] < 2:
        raise ValueError('Need at least two independent reference regions per frame.')
    if not all(np.isfinite(a).all() for a in (original,patch,tiles,references)):
        raise ValueError('Brightness features must be finite.')
    notes = {'method': method, 'alpha': float(alpha), 'quantile': float(quantile),
             'calibration': 'public preamble only', 'timing': 'shared original-ROI optical clock'}
    if method == 'original':
        return original, notes
    if method == 'patch_mean':
        return patch, notes
    offset = np.zeros(len(t))
    if method in ('reference', 'combined'):
        reference_calibration = preamble_samples(t, references, sync)
        centre = np.median(reference_calibration, axis=0)
        # Changes relative to each region's own level avoid brightness/vignetting bias.
        # Median across the four regions estimates a shared illumination change.
        offset = np.median(references-centre, axis=1)
        notes['reference_centres'] = centre.tolist()
        notes['maximum_absolute_reference_change'] = float(np.max(abs(offset)))
    if method == 'reference':
        return patch-alpha*offset, notes
    adjusted = tiles-alpha*offset[:, None]
    calibration = preamble_samples(t, adjusted, sync)
    low = np.median(calibration[PREAMBLE == 0], axis=0)
    high = np.median(calibration[PREAMBLE == 1], axis=0)
    contrast = high-low
    valid = contrast >= 20
    if valid.sum() < max(4, int(np.ceil(len(valid)/2))):
        raise ValueError('Fewer than half the tiles have usable public-preamble contrast.')
    normalized = (adjusted[:, valid]-low[valid])/contrast[valid]
    # Do not clip: clipping can hide saturation and distort quantile behaviour.
    signal = 25+200*np.quantile(normalized, quantile, axis=1)
    notes.update(valid_tiles=int(valid.sum()), total_tiles=len(valid),
                 tile_dark_levels=low.tolist(), tile_bright_levels=high.tolist(),
                 valid_tile_indices=np.flatnonzero(valid).tolist(),
                 signal_units='25 + 200 × normalized tile-brightness quantile')
    return signal, notes


def decode_features(times, features, method='original', bit_ms=200, alpha=1.0, quantile=.5):
    """Return diagnostic receiver output, preserving missing/FEC-rejected cases.

All variants rely on the baseline optical acquisition. This isolates processing
effects; it does not claim to rescue packets whose original preamble is lost.
"""
    if method == 'original':
        return receive_diagnostic(times, features['original'], bit_ms)
    result = {'failure_stage': 'acquisition'}
    try:
        t, original = _trace(times, features['original'])
        sync = find_preamble(t, original, bit_ms)
        result.update(sync)
        result['failure_stage'] = 'calibration'
        signal, notes = processed_signal(t, features, method, sync, alpha, quantile)
        samples = preamble_samples(t, signal, sync).ravel()
        low, high = (float(np.median(samples[PREAMBLE == bit])) for bit in [0,1])
        if high-low < 20:
            raise ValueError('Processed preamble contrast is too low.')
        threshold = (low+high)/2
        errors = int(np.count_nonzero((samples > threshold) != PREAMBLE))
        if errors > 1:
            raise ValueError('Processed public preamble is damaged.')
        result.update(threshold=threshold, dark_level=low, bright_level=high,
                      preamble_bit_errors=errors, frontend=notes)
        start, period = sync['start_seconds'], sync['period_seconds']
        first = len(PREAMBLE)
        result['failure_stage'] = 'header'
        header_values, _ = sample_slots(t, signal, start, period, range(first,first+HEADER_BITS))
        header = parse_header((header_values > threshold).astype(np.uint8))
        result.update({k:header[k] for k in ('codec','sequence','payload_bytes')})
        result['failure_stage'] = 'body_sampling'
        first += HEADER_BITS
        n = body_length(header['payload_bytes'],header['codec'])
        values, counts = sample_slots(t,signal,start,period,range(first,first+n))
        bits = (values > threshold).astype(np.uint8)
        result.update(body_bits=bits, body_sample_values=values, body_sample_counts=counts,
                      body_sample_times=start+(np.arange(first,first+n)+.5)*period,
                      failure_stage='fec')
        result.update(unpack_body(header,bits))
        result.update(failure_stage=None,text=result['payload'].decode('utf8',errors='replace'),
                      low_confidence_body_bits=int(np.count_nonzero(abs(values-threshold)<.15*(high-low))))
    except ValueError as exc:
        result['failure_reason'] = str(exc)
    return result
