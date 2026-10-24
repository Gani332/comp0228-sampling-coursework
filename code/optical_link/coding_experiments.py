"""Controlled body-channel simulations using the project's actual packet codecs.

These are synthetic experiments, not additional physical transmissions. Framing
is assumed perfectly received but charged to airtime. Receiver functions never
receive the expected payload. Evaluation uses truth only after decoding.
"""
import csv
import gzip
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from .protocol import (CODECS, GUARD_BITS, HEADER_BITS, PREAMBLE, bits_array,
                       make_packet, parse_header, to_bits, unpack_body)

DEFAULT_CONFIG = {
    'schema': 1, 'seed': 20261024, 'trials_per_condition': 2000,
    'payload_bytes': 9, 'bit_seconds': 0.2,
    'codecs': list(CODECS), 'interleaver_depths': [1, 8],
    'models': ['iid_flip', 'burst_flip', 'glare_burst'],
    'rates': [0, 0.01, 0.025, 0.05, 0.1, 0.2],
    'mean_burst_slots': 8, 'length_sweep_rate': 0.05,
    'length_sweep_slots': [2, 4, 8, 16],
    'scope': 'Body only; ideal synchronization/header; actual framing airtime included.',
    'payload_design': 'Uniform random 9-byte payloads, shared across all conditions; sequence = trial modulo 256.',
    'pairing': 'Same payload and common prefix of the same wire-slot noise process for all codes/depths in a trial.',
    'rate_definition': 'Flip models: stationary bit-error probability. Glare: bad-state occupancy, NOT BER.',
    'interleaver': 'Write bits row-wise into an 8-row ragged matrix, read column-wise; no padding or extra symbols.',
    'selection': 'Depth 8 and all parameter ranges specified before the main simulation; no winner-based tuning.',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def interleaver_order(length, depth=8):
    """Permutation: transmitted[j] = original[order[j]]. No padding is sent."""
    if not isinstance(length, (int, np.integer)) or length < 1:
        raise ValueError('Length must be a positive integer.')
    if not isinstance(depth, (int, np.integer)) or depth < 1:
        raise ValueError('Depth must be a positive integer.')
    rows = min(depth, length)
    columns = math.ceil(length / rows)
    order = np.arange(rows * columns).reshape(rows, columns).T.ravel()
    return order[order < length]


def interleave(bits, depth=8):
    a = bits_array(bits)
    return a[interleaver_order(len(a), depth)]


def deinterleave(bits, depth=8):
    a = bits_array(bits)
    restored = np.empty_like(a)
    restored[interleaver_order(len(a), depth)] = a
    return restored


def noise_states(rng, trials, slots, model, rate, mean_burst_slots=8):
    """Generate independent trial rows, starting Markov trials in stationarity.

For a burst process, P(B->G)=1/L and P(G->B)=rho/((1-rho)*L),
giving stationary bad-state occupancy rho and geometric bad-run mean L.
The states are generated without knowing transmitted data or its coding.
"""
    if model not in ('iid_flip', 'burst_flip', 'glare_burst'):
        raise ValueError('Unknown noise model.')
    if trials < 1 or slots < 1 or not 0 <= rate < 1:
        raise ValueError('Need positive sizes and a rate in [0,1).')
    if not np.isfinite(mean_burst_slots) or mean_burst_slots < 1:
        raise ValueError('Mean burst duration must be at least one slot.')
    uniform = rng.random((trials, slots))
    if model == 'iid_flip':
        return uniform < rate
    leave_bad = 1 / mean_burst_slots
    enter_bad = rate * leave_bad / (1 - rate)
    if enter_bad > 1:
        raise ValueError('Rate and mean burst duration imply an invalid transition probability.')
    state = np.empty((trials, slots), bool)
    state[:, 0] = uniform[:, 0] < rate
    for i in range(1, slots):
        state[:, i] = np.where(state[:, i-1], uniform[:, i] >= leave_bad,
                              uniform[:, i] < enter_bad)
    return state


def disturb(sent, states, model):
    sent = bits_array(sent)
    active = np.asarray(states, bool)
    if active.shape != sent.shape:
        raise ValueError('One noise state is required per transmitted body bit.')
    if model == 'glare_burst':
        return np.where(active, 1, sent).astype(np.uint8)
    if model in ('iid_flip', 'burst_flip'):
        return sent ^ active.astype(np.uint8)
    raise ValueError('Unknown noise model.')


def receive_body(wire_bits, clean_header, depth=1):
    """Decode measured bits plus trusted protocol metadata; no expected message."""
    try:
        return unpack_body(clean_header, deinterleave(wire_bits, depth))
    except ValueError as exc:
        return {'rejected': True, 'reason': str(exc)}


def measure_trial(packet, states, model, depth=1, bit_seconds=0.2):
    """Channel -> independent decoder -> evaluation against transmitted truth."""
    if not np.isfinite(bit_seconds) or bit_seconds <= 0:
        raise ValueError('Bit duration must be positive.')
    start = GUARD_BITS + len(PREAMBLE)
    header = parse_header(packet.bits[start:start+HEADER_BITS])
    sent = interleave(packet.body_bits, depth)
    received = disturb(sent, states, model)
    decoded = receive_body(received, header, depth)
    return score_decoded(packet, sent, received, decoded, states, depth, bit_seconds)


def score_decoded(packet, sent, received, decoded, states, depth, bit_seconds):
    wrong = sent != received
    payload_errors = None
    exact = False
    if 'payload' in decoded:
        payload_errors = int(np.count_nonzero(to_bits(decoded['payload']) != to_bits(packet.payload)))
        exact = decoded['payload'] == packet.payload
    crc = bool(decoded.get('crc_ok', False))
    return {
        'body_bits': len(sent), 'active_noise_slots': int(np.count_nonzero(states)),
        'channel_errors': int(wrong.sum()),
        'zero_to_one': int(np.count_nonzero(wrong & (sent == 0))),
        'one_to_zero': int(np.count_nonzero(wrong & (sent == 1))),
        'payload_bits': len(packet.payload)*8, 'payload_errors': payload_errors,
        'decoder_rejected': int('payload' not in decoded), 'crc_ok': int(crc),
        'exact_payload': int(exact), 'success': int(crc and exact),
        'undetected_wrong_payload': int(crc and not exact),
        'airtime_seconds': len(packet.bits)*bit_seconds,
        'delivered_bits': len(packet.payload)*8*int(crc and exact),
        'buffer_bits': len(sent) if depth > 1 else 0,
        'buffer_span_seconds': len(sent)*bit_seconds if depth > 1 else 0,
    }


def scenarios(config):
    cases = []
    for model in config['models']:
        for rate in config['rates']:
            cases.append({'model': model, 'rate': rate,
                          'mean_burst_slots': config['mean_burst_slots'], 'sweep': 'rate'})
    for model in ('burst_flip', 'glare_burst'):
        if model not in config['models']:
            continue
        for length in config['length_sweep_slots']:
            if length == config['mean_burst_slots'] and config['length_sweep_rate'] in config['rates']:
                continue
            cases.append({'model': model, 'rate': config['length_sweep_rate'],
                          'mean_burst_slots': length, 'sweep': 'duration'})
    return [dict(scenario_id=i, **s) for i, s in enumerate(cases)]


def wilson(successes, n, z=1.959963984540054):
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError('Need 0 <= successes <= n and n > 0.')
    p = successes/n
    scale = 1 + z*z/n
    centre = (p + z*z/(2*n))/scale
    radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/scale
    return max(0., centre-radius), min(1., centre+radius)


def aggregate(frame, case_list):
    summaries = []
    cases = {s['scenario_id']: s for s in case_list}
    for (scenario_id, codec, depth), group in frame.groupby(['scenario_id', 'codec', 'depth'], sort=True):
        n = len(group)
        k = int(group.success.sum())
        lo, hi = wilson(k, n)
        out = group.payload_errors.notna()
        payload_bits = int(group.loc[out, 'payload_bits'].sum())
        airtime = float(group.airtime_seconds.sum())
        offered = float(group.payload_bits.sum())/airtime
        summaries.append(dict(cases[int(scenario_id)], codec=codec, depth=int(depth),
            trials=n, successes=k, failures=n-k, success_rate=k/n,
            success_ci_low=lo, success_ci_high=hi,
            channel_errors=int(group.channel_errors.sum()), channel_bits=int(group.body_bits.sum()),
            channel_ber=float(group.channel_errors.sum()/group.body_bits.sum()),
            active_fraction=float(group.active_noise_slots.sum()/group.body_bits.sum()),
            zero_to_one=int(group.zero_to_one.sum()), one_to_zero=int(group.one_to_zero.sum()),
            payload_outputs=int(out.sum()), payload_bits_with_output=payload_bits,
            payload_errors=int(group.payload_errors.sum()),
            payload_ber_with_output=float(group.payload_errors.sum()/payload_bits) if payload_bits else None,
            decoder_rejections=int(group.decoder_rejected.sum()), crc_passes=int(group.crc_ok.sum()),
            undetected_wrong_payloads=int(group.undetected_wrong_payload.sum()),
            airtime_per_packet_seconds=float(group.airtime_seconds.iloc[0]),
            goodput_bps=float(group.delivered_bits.sum()/airtime),
            goodput_ci_low=offered*lo, goodput_ci_high=offered*hi,
            offered_payload_bps=offered, buffer_bits=int(group.buffer_bits.iloc[0]),
            buffer_span_seconds=float(group.buffer_span_seconds.iloc[0])))
    return summaries


def paired_outcomes(frame):
    rows = []
    for (scenario_id, codec), group in frame.groupby(['scenario_id', 'codec']):
        pairs = group.pivot(index='trial', columns='depth', values='success')
        if 1 not in pairs or 8 not in pairs:
            continue
        a, b = pairs[1], pairs[8]
        rows.append({'scenario_id': int(scenario_id), 'codec': codec, 'pairs': len(pairs),
                     'both_success': int(((a == 1) & (b == 1)).sum()),
                     'both_fail': int(((a == 0) & (b == 0)).sum()),
                     'interleaving_rescues': int(((a == 0) & (b == 1)).sum()),
                     'interleaving_harms': int(((a == 1) & (b == 0)).sum()),
                     'success_change_percentage_points': float(100*(b-a).mean())})
    return rows


def payloads(config):
    rng = np.random.default_rng(np.random.SeedSequence([config['seed'], 0]))
    return rng.integers(0, 256, (config['trials_per_condition'], config['payload_bytes']), dtype=np.uint8)


def source_hashes(root):
    files = ['optical_link/coding_experiments.py', 'optical_link/protocol.py',
             'optical_link/_vendor/reedsolo.py']
    return {name: digest(Path(root)/name) for name in files}


def run_study(root, output, config=None):
    root, output = Path(root), Path(output)
    config = json.loads(json.dumps(DEFAULT_CONFIG if config is None else config))
    if config['trials_per_condition'] < 1 or not 1 <= config['payload_bytes'] <= 64:
        raise ValueError('Invalid simulation size.')
    if config['interleaver_depths'] != [1, 8]:
        raise ValueError('This fixed comparison requires depths 1 and 8.')
    output.mkdir(parents=True, exist_ok=False)
    cases = scenarios(config)
    save_json(output/'config.json', config)
    save_json(output/'scenarios.json', cases)
    provenance = {'started_utc': datetime.now(timezone.utc).isoformat(),
                  'source_sha256': source_hashes(root), 'numpy_version': np.__version__}
    save_json(output/'provenance.json', provenance)
    messages = payloads(config)
    packets = {codec: [make_packet(bytes(a), codec, i % 256) for i, a in enumerate(messages)]
               for codec in config['codecs']}
    max_slots = max(len(p[0].body_bits) for p in packets.values())
    count = 0
    with gzip.open(output/'trials.csv.gz', 'wt', newline='') as file:
        writer = None
        for case in cases:
            rng = np.random.default_rng(np.random.SeedSequence([config['seed'], 1, case['scenario_id']]))
            states = noise_states(rng, len(messages), max_slots, case['model'], case['rate'], case['mean_burst_slots'])
            for codec, group in packets.items():
                for depth in config['interleaver_depths']:
                    for i, packet in enumerate(group):
                        m = measure_trial(packet, states[i, :len(packet.body_bits)], case['model'], depth, config['bit_seconds'])
                        row = dict(scenario_id=case['scenario_id'], trial=i, codec=codec, depth=depth, **m)
                        if writer is None:
                            writer = csv.DictWriter(file, fieldnames=list(row))
                            writer.writeheader()
                        writer.writerow(row)
                        count += 1
            print(f"Scenario {case['scenario_id']+1}/{len(cases)}: {case['model']}, rate={case['rate']}, L={case['mean_burst_slots']} complete", flush=True)
    frame = pd.read_csv(output/'trials.csv.gz', float_precision='round_trip')
    summary = aggregate(frame, cases)
    save_json(output/'summary.json', summary)
    pd.DataFrame(summary).to_csv(output/'summary.csv', index=False)
    save_json(output/'paired_outcomes.json', paired_outcomes(frame))
    provenance.update(completed_utc=datetime.now(timezone.utc).isoformat(), rows=count,
                      trial_data_sha256=digest(output/'trials.csv.gz'),
                      config_sha256=digest(output/'config.json'), scenarios_sha256=digest(output/'scenarios.json'))
    save_json(output/'provenance.json', provenance)
    return summary


def load_verified(root, study, replay_trials=3):
    """Verify saved data, recompute summaries, replay deterministic trial subsets."""
    study = Path(study)
    provenance = json.loads((study/'provenance.json').read_text())
    if provenance['source_sha256'] != source_hashes(root):
        raise ValueError('Simulation source changed: preserve this study and create a new run.')
    for name, key in [('trials.csv.gz', 'trial_data_sha256'), ('config.json', 'config_sha256'), ('scenarios.json', 'scenarios_sha256')]:
        if digest(study/name) != provenance[key]:
            raise ValueError('Saved simulation changed: '+name)
    config = json.loads((study/'config.json').read_text())
    cases = json.loads((study/'scenarios.json').read_text())
    if cases != scenarios(config):
        raise ValueError('Scenario definition differs from the saved configuration.')
    frame = pd.read_csv(study/'trials.csv.gz', float_precision='round_trip')
    rebuilt = aggregate(frame, cases)
    if rebuilt != json.loads((study/'summary.json').read_text()):
        raise ValueError('Saved summary differs from its trial records.')
    if paired_outcomes(frame) != json.loads((study/'paired_outcomes.json').read_text()):
        raise ValueError('Paired summary differs from its trial records.')
    messages = payloads(config)
    packets = {codec: [make_packet(bytes(a), codec, i % 256) for i, a in enumerate(messages[:replay_trials])]
               for codec in config['codecs']}
    max_slots = max(len(p[0].body_bits) for p in packets.values())
    indexed = frame.set_index(['scenario_id', 'codec', 'depth', 'trial'])
    checked = 0
    for case in cases:
        rng = np.random.default_rng(np.random.SeedSequence([config['seed'], 1, case['scenario_id']]))
        # Same row-wise RNG draw prefix as the full study.
        states = noise_states(rng, min(replay_trials, len(messages)), max_slots,
                              case['model'], case['rate'], case['mean_burst_slots'])
        for codec, group in packets.items():
            for depth in config['interleaver_depths']:
                for i, packet in enumerate(group):
                    result = measure_trial(packet, states[i, :len(packet.body_bits)], case['model'], depth, config['bit_seconds'])
                    saved = indexed.loc[(case['scenario_id'], codec, depth, i)]
                    for key, value in result.items():
                        if value is None:
                            assert pd.isna(saved[key]), key
                        else:
                            assert saved[key] == value, (case, codec, depth, i, key)
                    checked += 1
    return frame, pd.DataFrame(rebuilt), {'trial_records': len(frame), 'replayed_decodes': checked,
                                        'summary_recomputed': True, 'source_and_data_hashes_verified': True}
