"""Empirical residual replay, a sensitivity model rather than camera validation.

Joint moving blocks preserve spatial correlation and within-block frame gaps.
LCD transitions are instantaneous in generated signals. Source transition
artifacts remain in residuals; exposure and rolling shutter are not modeled.
"""
from dataclasses import dataclass
import numpy as np
from .protocol import GUARD_BITS, PREAMBLE, HEADER_BITS
from .receiver import find_preamble
from .receiver_layers import preamble_samples
from .coding_experiments import interleave

FEATURES = ('original', 'patch_mean', 'tiles', 'references')
BLOCK_SECONDS = 1.6  # Eight nominal slots; specified without outcome tuning.


def matrix(features):
    return np.column_stack([features[k] for k in FEATURES])


@dataclass
class ResidualModel:
    low: np.ndarray
    high: np.ndarray
    blocks: list
    widths: tuple
    metadata: dict

    def timeline(self, rng, duration):
        """No interpolation; concatenate joint blocks with a median-gap join."""
        times, residuals = [], []
        elapsed = 0.
        join = self.metadata['median_frame_gap_seconds']
        while elapsed <= duration:
            dt, residual = self.blocks[int(rng.integers(len(self.blocks)))]
            times.append(elapsed+dt)
            residuals.append(residual)
            elapsed += dt[-1]+join
        t, r = np.concatenate(times), np.concatenate(residuals)
        keep = t <= duration
        return t[keep], r[keep]

    def features(self, packet, depth, times, residuals, *, bit_seconds=.2, disturbed=True):
        bits = packet.bits.copy()
        first = GUARD_BITS+len(PREAMBLE)+HEADER_BITS
        bits[first:-GUARD_BITS] = interleave(packet.body_bits, depth)
        slot = np.floor(times/bit_seconds).astype(int)
        on = bits[np.minimum(slot, len(bits)-1)]
        ideal = self.low + on[:, None]*(self.high-self.low)
        # Public prefix is pristine; disturbances continue through the full body.
        body = (slot >= first) & (slot < len(bits)-GUARD_BITS)
        signal = ideal + (residuals*body[:, None] if disturbed else 0)
        signal = np.clip(signal, 0, 255)
        edges = np.cumsum((0,)+self.widths)
        result = {k: signal[:, edges[i]:edges[i+1]] for i, k in enumerate(FEATURES)}
        for k in ('original', 'patch_mean'):
            result[k] = result[k][:, 0]
        return result


def calibrate(windows, *, block_seconds=BLOCK_SECONDS, bit_ms=200):
    """windows contain (packet_id, measured times, features, logged tx).

    Truth is used here only to subtract the transmitted ideal signal. Level fits
    use middle-half public preamble samples; references use constant centres.
    Blocks never cross packet boundaries or gaps above 2.5 median frame gaps.
    """
    if not np.isfinite(block_seconds) or block_seconds <= 0:
        raise ValueError('Block duration must be finite and positive.')
    lows, highs, blocks, reports, gaps = [], [], [], [], []
    widths = None
    for packet_id, t, f, tx in windows:
        report = {'packet_id': packet_id, 'frames_in_window': len(t)}
        try:
            sync = find_preamble(t, f['original'], bit_ms)
        except ValueError as exc:
            report.update(excluded=True, reason=str(exc)); reports.append(report)
            continue
        y = matrix(f)
        widths = tuple(1 if np.asarray(f[k]).ndim == 1 else f[k].shape[1] for k in FEATURES)
        public = preamble_samples(t, y, sync)
        low = np.median(public[PREAMBLE == 0], axis=0)
        high = np.median(public[PREAMBLE == 1], axis=0)
        reference_start = sum(widths[:-1])
        low[reference_start:] = high[reference_start:] = np.median(public[:, reference_start:], axis=0)
        if np.any(high[:2]-low[:2] < 20):
            report.update(excluded=True, reason='Insufficient public preamble contrast')
            reports.append(report); continue
        bits = np.array([int(b) for b in tx['transmitted_bits']], dtype=np.uint8)
        origin = sync['start_seconds']-GUARD_BITS*sync['period_seconds']
        slot = np.floor((t-origin)/sync['period_seconds']).astype(int)
        keep = (slot >= 0) & (slot < len(bits))
        tt, yy, ss = t[keep], y[keep], slot[keep]
        residual = yy-(low+bits[ss, None]*(high-low))
        gap = float(np.median(np.diff(tt)))
        cuts = np.r_[0, np.flatnonzero(np.diff(tt) > 2.5*gap)+1, len(tt)]
        count_before = len(blocks)
        for a, b in zip(cuts[:-1], cuts[1:]):
            # Moving blocks start at every measured frame, with no wraparound.
            for i in range(a, b):
                end = np.searchsorted(tt, tt[i]+block_seconds, side='right')
                if end <= b and end > i+1 and tt[end-1]-tt[i] >= block_seconds-1.5*gap:
                    blocks.append((tt[i:end]-tt[i], residual[i:end]))
        count = len(blocks)-count_before
        report.update(excluded=count == 0, residual_frames=len(tt),
                      excluded_outside_packet_frames=int((~keep).sum()), blocks=count,
                      recovered_period_seconds=sync['period_seconds'])
        reports.append(report)
        if count:
            lows.append(low); highs.append(high); gaps.append(gap)
    if not blocks:
        raise ValueError('Model calibration unavailable: no synchronized, usable residual blocks. Source windows: '+str(reports))
    low, high = np.median(lows, axis=0), np.median(highs, axis=0)
    metadata = dict(model='empirical joint multichannel moving-block residual replay',
                    scope='in-sample sensitivity analysis; not held-out validation',
                    block_seconds=block_seconds, blocks=len(blocks), source_windows=reports,
                    median_frame_gap_seconds=float(np.median(gaps)),
                    timestamp_policy='Retain within-block frame gaps; join blocks using median source gap; no interpolation.',
                    level_fit='Middle-half public preamble slot medians; constant reference centres.',
                    prefix='Clean synthetic guards, preamble and header; optical acquisition search restricted to this public generated prefix; causal filters burn in on prefix.',
                    sensor_rule='Synthetic features clipped to [0,255]; measured data unchanged.',
                    limitations='Instantaneous ideal LCD edges; residuals retain source transition artifacts. No faithful exposure/rolling-shutter model.',
                    selection='Pool all usable packet windows without filtering by decode outcome.',
                    low_levels=low.tolist(), high_levels=high.tolist())
    return ResidualModel(low, high, blocks, widths, metadata)
