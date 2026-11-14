"""Verify and replay the companion evidence without raw videos or hardware.

Run from the project root:
  python code/tools/verify_submission_evidence.py --evidence ../evidence --output ../verification

Evidence is read-only. Output must be a new directory. Acquisition failures
are retained, not magically replayed as successful packet detections. Expected
payloads are used for scoring only, after the receiver returns its result.
"""
from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'code'))
from optical_link.campaign_frontends import METHODS, decode
from optical_link.campaign_diagnostics import error_runs, paired_change
from optical_link.coding_experiments import interleave, load_verified
from optical_link.protocol import make_packet


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    """Keep verification active even if Python is invoked with optimization."""
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def checked_path(root, name):
    """Reject absolute/traversing manifest entries, including escaping symlinks."""
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts,
            f'Unsafe manifest path: {name}')
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), f'Path escapes its root: {name}')
    return path


def check_manifest(evidence):
    manifest = read(evidence / 'MANIFEST.json')
    for name, expected in manifest['files_sha256'].items():
        require(sha(checked_path(evidence, name)) == expected,
                f'Evidence hash mismatch: {name}')
    for name, expected in manifest['scientific_source_sha256'].items():
        require(sha(checked_path(PROJECT, name)) == expected,
                f'Scientific source hash mismatch: {name}')
    return len(manifest['files_sha256'])


def physical_summary(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['condition'], row['codec'], row['depth'])].append(row)
    summary = []
    for (condition, codec, depth), group in sorted(groups.items()):
        observed = [r for r in group if r['body_errors'] is not None]
        bits = sum(r['body_bits'] for r in observed)
        errors = sum(r['body_errors'] for r in observed)
        summary.append(dict(condition=condition, codec=codec, depth=depth,
                            packets=len(group), successes=sum(r['success'] for r in group),
                            errors=errors, observed_body_bits=bits,
                            ber=errors / bits if bits else None,
                            goodput_bps=sum(r['delivered_bits'] for r in group) /
                            sum(r['airtime_seconds'] for r in group)))
    return summary


def replay_receivers(campaign):
    rows = read(campaign / 'packets.json')
    expected = read(campaign / 'development_frontends.json') + read(campaign / 'main_frontends.json')
    saved = {(r['video'], r['sequence'], r['method']): r for r in expected}
    require(len(saved) == len(expected), 'Duplicate saved receiver outcome')
    cache = {}
    replayed, retained = 0, 0
    outcomes = []
    for row in rows:
        # The published secondary analysis uses Video 7 development glare,
        # then Videos 8–21. Earlier calibration has no secondary feature cache.
        if row['video'] < 7:
            continue
        video = row['video']
        if video not in cache:
            meta = read(campaign / f'features/Video{video}.json')
            path = campaign / f'features/Video{video}.npz'
            require(sha(path) == meta['feature_sha256'], f'Changed features: Video {video}')
            require(meta['video_sha256'] == row['video_sha256'], f'Wrong feature recording: {video}')
            with np.load(path, allow_pickle=False) as arrays:
                cache[video] = {key: arrays[key] for key in arrays.files}
        features = cache[video]
        times = features['times']
        if row['acquired']:
            # Use the published baseline acquisition window for every method.
            # This verifies processing, not a new independent acquisition search.
            end = row['preamble_start'] + (80 + row['body_bits']) * .2 + .4
            mask = (times >= row['preamble_start'] - .4) & (times <= end)
            window = {key: features[key][mask] for key in
                      ('original', 'patch_mean', 'tiles', 'references')}
        for method in METHODS:
            if row['acquired']:
                received = decode(times[mask], window, method, depth=row['depth'])
                replayed += 1
            else:
                received = {'failure_stage': 'acquisition_or_header'}
                retained += 1
            # Ground truth enters only here, after optical decoding.
            matched = all(received.get(key) == row[key] for key in
                          ('codec', 'sequence', 'payload_bytes'))
            truth = interleave(make_packet(bytes.fromhex(row['payload_hex']), row['codec'],
                                           row['sequence']).body_bits, row['depth'])
            raw = received.get('wire_body_bits') if matched else None
            errors = int(np.count_nonzero(raw != truth)) if raw is not None else None
            success = bool(matched and received.get('crc_ok', False) and
                           received.get('payload', b'').hex() == row['payload_hex'])
            prior = saved[(video, row['sequence'], method)]
            require((success, errors) == (prior['success'], prior['body_errors']),
                    f'Receiver mismatch: Video {video}, sequence {row["sequence"]}, {method}')
            outcomes.append(dict(prior, success=success, body_errors=errors))
        print(f'Checked Video {video}, sequence {row["sequence"]}', flush=True)
    groups = defaultdict(list)
    for row in outcomes:
        groups[(row['phase'], row['condition'], row['method'])].append(row)
    summary = []
    for (phase, condition, method), group in sorted(groups.items()):
        summary.append(dict(phase=phase, condition=condition, method=method,
                            packets=len(group), successes=sum(r['success'] for r in group),
                            body_errors=sum(r['body_errors'] or 0 for r in group),
                            observed_body_bits=sum(r['body_bits'] for r in group
                                                   if r['body_errors'] is not None)))
    require(len(outcomes) == len(expected), 'Missing receiver outcomes')
    return summary, replayed, retained


def verify(evidence, output):
    require(not output.is_relative_to(evidence), 'Output must be outside the read-only evidence directory')
    require(not output.exists(), f'Output already exists; use a new directory: {output}')
    files = check_manifest(evidence)
    data = evidence / 'data'
    campaign = data / 'analysis/physical_campaign_2026-11-08'
    rows = read(campaign / 'packets.json')
    pilot = read(campaign / 'evidence/pilot_replay.json')['packets']
    main = [r for r in rows if r['phase'] == 'main']
    require(len(rows) + len(pilot) == 82, 'Physical denominator changed')
    require(len(main) == 54 and sum(r['success'] for r in main) == 35,
            'Main results differ from the report')
    require(len(pilot) == 16 and all(r['exact_message'] and r['crc_ok'] for r in pilot)
            and sum(r['body_bit_errors'] for r in pilot) == 0
            and sum(r['body_bits'] for r in pilot) == 3840, 'Pilot summary mismatch')
    for row in rows:
        require(abs(row['airtime_seconds'] - .2 * (96 + row['body_bits'])) < 1e-8,
                'Incorrect framing cost')
    noise = []
    for condition in ('OCC_CLUSTER', 'GLARE_BODY'):
        group = [r for r in main if r['condition'] == condition]
        runs = [n for r in group for n in error_runs(r['error_indices'], r['body_bits'])]
        noise.append(dict(condition=condition, packets=len(group), runs=len(runs),
                          errors=sum(r['body_errors'] for r in group),
                          body_bits=sum(r['body_bits'] for r in group),
                          errors_in_multibit_runs=sum(n for n in runs if n >= 2)))
    for actual, saved in zip(noise, read(campaign / 'diagnostics/physical_noise_structure.json')):
        require(all(saved[key] == value for key, value in actual.items()), 'Noise summary mismatch')
    receiver_summary, replayed, retained = replay_receivers(campaign)
    print('Verifying 480,000 simulation records and replaying 720 decodes...', flush=True)
    frame, _, simulation = load_verified(PROJECT / 'code', data / 'analysis/coding_experiments_2026-10-24')
    intervals = []
    for saved in read(campaign / 'diagnostics/interleaving_duration_paired.json'):
        subset = frame[(frame.scenario_id == saved['scenario_id']) & (frame.codec == saved['codec'])]
        rebuilt = paired_change(subset, seed=saved['seed'], resamples=saved['resamples'])
        require(all(saved[key] == value for key, value in rebuilt.items()), 'Paired interval mismatch')
        intervals.append(dict(saved, **rebuilt))
    result = dict(evidence_files_verified=files, physical_transmissions=82,
                  main_recovered=35, main_packets=54, receiver_decodes_replayed=replayed,
                  shared_acquisition_failure_rows_retained=retained,
                  pilot_scope='Saved pilot summary and trace hashes checked; pilot acquisition not replayed.',
                  acquisition_scope='Six original acquisition/header failures retained across seven methods; not independent detections.',
                  paired_intervals_recomputed=len(intervals), simulation=simulation,
                  raw_video_scope='Raw video extraction and physical intervention measurements are not revalidated by cached replay.')
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('verification.json', result), ('physical_summary.json', physical_summary(rows)),
                        ('receiver_summary.json', receiver_summary), ('noise_summary.json', noise),
                        ('paired_intervals.json', intervals)]:
        (output / name).write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True, help='Extracted evidence directory containing MANIFEST.json')
    parser.add_argument('--output', type=Path, required=True, help='New output directory; never overwrites evidence')
    args = parser.parse_args()
    try:
        verify(args.evidence.resolve(), args.output.resolve())
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Verification failed: {exc}\n')


if __name__ == '__main__':
    main()
