"""Cache-only physical replay and separately labelled modeled sensitivity study."""
import csv
import hashlib
from importlib.metadata import version
import json
import re
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .baseline_analysis import assess_received
from .protocol import CODECS, GUARD_BITS, PREAMBLE, HEADER_BITS, make_packet
from .receiver_layers import COMPARISON_METHODS, FILTER_DEFAULTS, decode_comparison
from .recording_model import calibrate, FEATURES

STUDY = Path('data/analysis/receiver_layers_2026-10-24')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def recording_slug(name):
    return re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_') or 'recording'


def resolve_recording(root, name):
    manifest = json.loads((root/STUDY/'manifest.json').read_text())
    exact = [v for v in manifest if v['id'] == name]
    candidates = exact or [v for v in manifest if Path(v['video']).name == name]
    if len(candidates) != 1:
        raise ValueError('Recording is ambiguous or unregistered. Use a unique manifest ID. New movies need a manifest entry, packet windows, ROI geometry, matching ground-truth logs and a verified feature cache; no download is performed.')
    v = candidates[0]
    slug = recording_slug(v['id'])
    if sum(recording_slug(x['id']) == slug for x in manifest) > 1:
        slug += '_'+hashlib.sha256(v['id'].encode()).hexdigest()[:8]
    return v, slug


def load_cache(root, video):
    file = root/STUDY/'features'/(video['id']+'.npz')
    try:
        meta = json.loads(file.with_suffix('.json').read_text())
        if digest(file) != meta['feature_sha256']:
            raise ValueError('Feature cache SHA-256 mismatch.')
        for key, expected in [('video_id', video['id']), ('video_sha256', video['sha256']),
                              ('original_roi', video['original_roi']), ('study_roi', video['study_roi']),
                              ('reference_rois', video['reference_rois'])]:
            if meta[key] != expected:
                raise ValueError('Feature cache provenance mismatch: '+key)
        with np.load(file, allow_pickle=False) as z:
            t = z['times'].copy()
            f = {k: z[k].copy() for k in FEATURES}
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError(f'Invalid/missing verified cache for {video["id"]}: {exc}. Restore the matching .npz and .json cache; arbitrary movies cannot be scored.') from exc
    if t.ndim != 1 or len(t) < 40 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Invalid cache timestamps.')
    if len(t) != meta['frames']:
        raise ValueError('Cache frame count mismatch.')
    if any(a.shape[0] != len(t) or not np.isfinite(a).all() for a in f.values()):
        raise ValueError('Cache features must be finite with one row per timestamp.')
    if f['original'].shape != t.shape or f['patch_mean'].shape != t.shape or f['tiles'].ndim != 2 or f['tiles'].shape[1] < 4 or f['references'].ndim != 2 or f['references'].shape[1] < 2:
        raise ValueError('Invalid feature channel geometry.')
    # Verify exact archived times and original ROI, including silent-container mapping:
    # the movie identity above is the original manifest hash, never a new movie hash.
    trace = root/'data'/video['trace']
    if video['trace_format'] == 'npz':
        with np.load(trace, allow_pickle=False) as z:
            archived_t, archived_y = z['times'], z['brightness']
    else:
        z = np.genfromtxt(trace, delimiter=',', names=True)
        archived_t, archived_y = z['time_seconds'], z['mean_brightness']
    if not np.array_equal(t, archived_t) or not np.allclose(f['original'], archived_y, rtol=0, atol=1e-9):
        raise ValueError('Cache does not match archived timestamps/original ROI.')
    windows = []
    for p in video['packets']:
        mask = np.ones(len(t), bool) if p['window'] is None else (t >= p['window'][0]) & (t <= p['window'][1])
        if mask.sum() < 40:
            raise ValueError('Insufficient cached samples for '+p['id'])
        tx = json.loads((root/'data'/p['tx']).read_text())
        tx['_condition'] = p['expected'].get('condition', 'noisy')
        # Check log integrity against its actual protocol packet; never rewrite it.
        packet = make_packet(bytes.fromhex(tx['payload_hex']), tx['codec'], tx['sequence'])
        logged = ''.join(map(str, packet.bits))
        if logged != tx['transmitted_bits']:
            raise ValueError('Transmission log bits do not match the declared packet: '+p['id'])
        depth = tx.get('interleave_depth', 1)
        if depth != 1:
            raise ValueError('Physical interleaved log requires explicit wire-order support.')
        windows.append((p['id'], t[mask], {k: a[mask] for k, a in f.items()}, tx))
    return windows, meta


def score(rx, tx, *, identity, method, depth, elapsed):
    m = assess_received(rx, tx)
    row = dict(identity, actual_codec=tx['codec'] if identity['evidence_kind']=='physical_replay' else None,
               candidate_codec=tx['codec'], camera_method=method, interleave_depth=depth,
               bit_seconds=.2, reference_alpha=1., spatial_quantile=.25,
               condition=tx.get('_condition', 'modeled'), filter_parameters_json=json.dumps(FILTER_DEFAULTS, sort_keys=True),
               status=('crc_valid_wrong_payload' if m['crc_ok'] and not m['exact_payload_match'] else m['status']), failure_stage=m['failure_stage'], reason=m['reason'],
               crc_ok=m['crc_ok'], exact_payload_match=m['exact_payload_match'],
               packet_success=not m['packet_failed'], returned_payload=m['received_text'],
               returned_payload_hex=rx['payload'].hex() if 'payload' in rx else None,
               channel_bit_errors=m['body_channel_bit_errors'],
               channel_bits_measured=m['body_channel_bits'] if m['body_channel_bit_errors'] is not None else None,
               channel_ber=m['body_channel_ber'], payload_bit_errors=m['payload_bit_errors'],
               payload_bits_measured=m['payload_bits'] if m['payload_bit_errors'] is not None else None,
               payload_ber=m['payload_ber'], payload_bits_offered=m['payload_bits'],
               channel_seconds_including_overhead=m['channel_seconds_including_overhead'],
               correct_delivered_bits=m['correct_delivered_bits'], goodput_bps=m['correct_payload_goodput_bps'],
               processing_seconds=elapsed)
    return row


def tx_for(packet):
    return dict(payload_hex=packet.payload.hex(), codec=packet.codec, sequence=packet.sequence,
                transmitted_bits=''.join(map(str, packet.bits)), scheduled_channel_seconds=len(packet.bits)*.2)


def receive(t, f, method, depth, *, acquisition_end_seconds=None):
    start = time.perf_counter()
    rx = decode_comparison(t, f, method, depth=depth, acquisition_end_seconds=acquisition_end_seconds)
    return rx, time.perf_counter()-start


def physical(windows, identity):
    rows = []
    for pid, t, f, tx in windows:
        for method in COMPARISON_METHODS:
            rx, elapsed = receive(t, f, method, 1)
            rows.append(score(rx, tx, identity=dict(identity, packet_id=pid, trial=None),
                              method=method, depth=1, elapsed=elapsed))
    return rows


def modeled(windows, identity, trials, seed, *, random_payload=False):
    model = calibrate(windows)
    model_json = json.dumps(model.metadata, sort_keys=True)
    rng = np.random.default_rng(seed)
    source = windows[0][3]
    payload = bytes.fromhex(source['payload_hex'])
    rows = []
    for trial in range(trials):
        offered = rng.bytes(len(payload)) if random_payload else payload
        packets = [make_packet(offered, codec, source['sequence']) for codec in CODECS]
        duration = max(len(p.bits) for p in packets)*.2
        t, disturbance = model.timeline(rng, duration)
        for packet in packets:
            keep = t < len(packet.bits)*.2
            tt = t[keep]
            for depth in (1, 8):
                features = model.features(packet, depth, tt, disturbance[keep])
                for method in COMPARISON_METHODS:
                    rx, elapsed = receive(tt, features, method, depth,
                        acquisition_end_seconds=(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*.2)
                    rows.append(score(rx, tx_for(packet), identity=dict(identity,
                        packet_id=windows[0][0], trial=trial, model_parameters_json=model_json),
                        method=method, depth=depth, elapsed=elapsed))
        print(f'Modeled trial {trial+1}/{trials} complete', flush=True)
    model.metadata.update(fixed_payload_source_packet=windows[0][0],
                          payload_mode='random bytes of recorded length' if random_payload else 'fixed recorded payload',
                          sequence=source['sequence'])
    return rows, model.metadata


def wilson(successes, n):
    z = 1.959963984540054
    p = successes/n
    centre = (p+z*z/(2*n))/(1+z*z/n)
    half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return max(0., centre-half), min(1., centre+half)


def aggregate(rows):
    result = []
    for depth in (1, 8):
        for method in COMPARISON_METHODS:
            for codec in CODECS:
                selected = [r for r in rows if (r['interleave_depth'], r['camera_method'], r['candidate_codec']) == (depth, method, codec)]
                n = len(selected)
                if not n:
                    raise ValueError('Missing modeled configuration.')
                successful = sum(r['packet_success'] for r in selected)
                low, high = wilson(successful, n)
                seconds = sum(r['channel_seconds_including_overhead'] for r in selected)
                delivered = sum(r['correct_delivered_bits'] for r in selected)
                row = dict(recording_id=selected[0]['recording_id'], evidence_kind='modeled_replay',
                           camera_method=method, candidate_codec=codec, interleave_depth=depth,
                           trials_attempted=n, successful_packets=successful, success_rate=successful/n,
                           wilson95_low=low, wilson95_high=high, total_airtime_seconds=seconds,
                           total_correct_delivered_bits=delivered, goodput_bps=delivered/seconds,
                           processing_seconds=sum(r['processing_seconds'] for r in selected))
                for kind in ('channel', 'payload'):
                    available = [r for r in selected if r[kind+'_bit_errors'] is not None]
                    bits = sum(r[kind+'_bits_measured'] for r in available)
                    row['packets_with_'+('channel_bits' if kind == 'channel' else 'payload')] = len(available)
                    row['pooled_'+kind+'_ber'] = sum(r[kind+'_bit_errors'] for r in available)/bits if bits else None
                # Paired bootstrap against patch_mean for the same trial/code/depth.
                baseline = {r['trial']: r for r in rows if r['interleave_depth']==depth and r['camera_method']=='patch_mean' and r['candidate_codec']==codec}
                delta = np.array([int(r['packet_success'])-int(baseline[r['trial']]['packet_success']) for r in selected])
                boot = np.random.default_rng(0).choice(delta, (1000, n)).mean(axis=1)
                row.update(success_difference_vs_patch_mean=float(delta.mean()),
                           paired_bootstrap95_low=float(np.quantile(boot, .025)),
                           paired_bootstrap95_high=float(np.quantile(boot, .975)))
                result.append(row)
    return result


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def plot_physical(path, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    ids = list(dict.fromkeys(r['packet_id'] for r in rows))
    values = np.full((7, len(ids)), np.nan)
    labels = np.full(values.shape, '', dtype=object)
    for r in rows:
        i, j = COMPARISON_METHODS.index(r['camera_method']), ids.index(r['packet_id'])
        values[i,j] = 2 if r['status']=='association_error' else int(r['packet_success'])
        labels[i,j] = 'unavailable' if values[i,j]==2 else ('pass' if r['packet_success'] else 'fail')
    fig, ax = plt.subplots(figsize=(max(7, len(ids)*1.7), 5), layout='constrained')
    ax.imshow(values, cmap=ListedColormap(['#eaa39d', '#8dc9a0', '#bbbbbb']), vmin=0, vmax=2, aspect='auto')
    ax.set_yticks(range(7), COMPARISON_METHODS)
    codecs = {r['packet_id']: r['actual_codec'] for r in rows}
    ax.set_xticks(range(len(ids)), [p+'\n'+codecs[p] for p in ids])
    for i, j in np.ndindex(values.shape):
        ax.text(j, i, labels[i,j], ha='center', va='center')
    ax.set_title(rows[0]['recording_id']+' — physical replay (retrospective)\nActual transmitted codecs; interleaving off\nSuccess requires valid CRC + exact payload', fontsize=11)
    fig.savefig(path, dpi=220); plt.close(fig)


def plot_modeled(path, summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout='constrained')
    for row, metric in enumerate(('success_rate', 'goodput_bps')):
        vmax = 1 if row==0 else max(s[metric] for s in summary)
        for col, depth in enumerate((1, 8)):
            ax = axes[row,col]
            values = np.full((7, 5), np.nan)
            for s in summary:
                if s['interleave_depth']==depth:
                    values[COMPARISON_METHODS.index(s['camera_method']), list(CODECS).index(s['candidate_codec'])] = s[metric]
            cmap = plt.get_cmap('YlGnBu').copy(); cmap.set_bad('#bbbbbb')
            im = ax.imshow(values, vmin=0, vmax=max(vmax, .001), cmap=cmap, aspect='auto')
            ax.set_xticks(range(5), CODECS); ax.set_yticks(range(7), COMPARISON_METHODS)
            ax.set_title(('Success probability' if row==0 else 'Goodput (bit/s)')+f' — interleaving {"off" if depth==1 else "on (8)"}')
            best = np.nanmax(values)
            for i,j in np.ndindex(values.shape):
                v = values[i,j]
                ax.text(j,i, '—' if np.isnan(v) else f'{v:.2f}'+(' *' if np.isclose(v,best) else ''),
                        ha='center',va='center', color='white' if v>vmax*.65 else 'black', fontsize=9)
            fig.colorbar(im, ax=ax, shrink=.8)
    fig.suptitle(f'{summary[0]["recording_id"]} — MODELED in-sample sensitivity analysis; {summary[0]["trials_attempted"]} paired trials/configuration\nCRC fixed; clean acquisition/header assumed; * best within panel (ties retained)')
    fig.savefig(path, dpi=220); plt.close(fig)


def run(root, *, recording='G02', mode='both', output=None, seed=20261027, trials=200, random_payload=False):
    root = Path(root).resolve()
    if mode not in ('physical', 'modeled', 'both') or trials < 1 or seed < 0:
        raise ValueError('Require a valid mode, positive trials and nonnegative seed.')
    video, slug = resolve_recording(root, recording)
    windows, cache = load_cache(root, video)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    base = root/'playground'/'comparison_results'/slug if output is None else root/Path(output)
    out = base/stamp
    out.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), Path(__file__).with_name('recording_model.py'),
               Path(__file__).with_name('receiver_layers.py'), Path(__file__).with_name('protocol.py'),
               Path(__file__).with_name('receiver.py'), Path(__file__).with_name('baseline_analysis.py'),
               Path(__file__).with_name('coding_experiments.py'), root/'code/tools/run_recording_comparison.py']
    hashes = {str(p.relative_to(root)): digest(p) for p in sources}
    metadata = dict(recording_id=video['id'], safe_recording_slug=slug, mode=mode, seed=seed,
                    trials=trials, created_utc=stamp, input_kind='verified feature cache',
                    cohort=video['cohort'], evidence='Retrospective physical replay; modeled runs are in-sample sensitivity analysis.',
                    filter_parameters=FILTER_DEFAULTS, temporal_input_feature='patch_mean', tuning_source_ids=[],
                    filter_selection='Fixed conservative defaults: tau=1/8 slot; q/R=400 per second. No evaluation tuning.',
                    source_hashes=hashes,
                    snapshot_sha256=digest(Path(__file__).with_name('comparison_provenance')/'receiver_layers_original.py'),
                    front_end_parameters={'reference_alpha': 1., 'spatial_quantile': .25, 'source': 'historical frozen_config.json'},
                    python=sys.version, platform=platform.platform(),
                    manifest_sha256=digest(root/STUDY/'manifest.json'), cache=cache,
                    transmission_log_hashes={pid: digest(root/'data'/p['tx']) for pid, p in zip([w[0] for w in windows], video['packets'])},
                    frozen_source='Historical strict source checker remains unchanged and will reject modified receiver_layers.py. Original bytes/hash in code/optical_link/comparison_provenance; use original revision for exact frozen reruns.',
                    csv_encoding='UTF-8; empty numeric/boolean cells are null; booleans are True/False.',
                    packages={name: version(name) for name in ('numpy', 'matplotlib', 'pandas')})
    identity = dict(recording_id=video['id'], safe_recording_slug=slug, seed=seed,
                    model_source_id=video['id'], mode=mode, feature_sha256=cache['feature_sha256'],
                    source_config_sidecar=slug+'__run_metadata.json', cohort=video['cohort'],
                    input_kind='verified feature cache', model_parameters_json=None)
    if mode in ('physical', 'both'):
        rows = physical(windows, dict(identity, evidence_kind='physical_replay'))
        write_csv(out/(slug+'__physical_results.csv'), rows)
        plot_physical(out/(slug+'__physical_comparison.png'), rows)
        print(f'Physical replay: {len(rows)} rows; {len(windows)} packets (one recording).', flush=True)
    if mode in ('modeled', 'both'):
        print('MODELED: joint residual replay; clean prefix; in-sample sensitivity, not physical validation.', flush=True)
        rows, model = modeled(windows, dict(identity, evidence_kind='modeled_replay'), trials, seed, random_payload=random_payload)
        summary = aggregate(rows)
        write_csv(out/(slug+'__modeled_trials.csv'), rows)
        write_csv(out/(slug+'__modeled_summary.csv'), summary)
        plot_modeled(out/(slug+'__modeled_comparison.png'), summary)
        metadata['model'] = model
    save_json(out/(slug+'__run_metadata.json'), metadata)
    return out
