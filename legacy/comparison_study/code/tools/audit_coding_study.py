"""Independent mathematical and data-integrity checks on the completed study."""
import argparse
import json
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--study', type=Path, required=True)
args = parser.parse_args()
root, study = args.root.resolve(), args.study.resolve()
sys.path.insert(0, str(root))
from optical_link.coding_experiments import (load_verified, payloads, noise_states,
    make_packet, disturb, interleave, receive_body, save_json)
from optical_link.protocol import GUARD_BITS, PREAMBLE, HEADER_BITS, parse_header, checksum, to_bytes

frame, summary, check = load_verified(root, study)
config = json.loads((study/'config.json').read_text())
assert len(frame) == len(summary)*config['trials_per_condition']
assert not frame.duplicated(['scenario_id', 'codec', 'depth', 'trial']).any()
assert (frame.groupby(['scenario_id', 'codec', 'depth']).size() == config['trials_per_condition']).all()
assert (summary[summary.rate == 0].successes == config['trials_per_condition']).all()
cases = pd.DataFrame(json.loads((study/'scenarios.json').read_text()))
joined = frame.merge(cases, on='scenario_id')
for (scenario, codec), group in joined[joined.model != 'glare_burst'].groupby(['scenario_id', 'codec']):
    pivot = group.pivot(index='trial', columns='depth', values='channel_errors')
    assert (pivot[1] == pivot[8]).all()
assert (joined.loc[joined.model == 'glare_burst', 'one_to_zero'] == 0).all()

# Analytic exact protected-body recovery probabilities under independent flips.
# No empirical result is used to fit these predictions.
raw_bits = (config['payload_bytes']+2)*8
analytic = []
for _, row in summary[summary.model == 'iid_flip'].iterrows():
    p, codec = row.rate, row.codec
    if codec == 'none':
        expected = (1-p)**raw_bits
    elif codec.startswith('repeat'):
        r = int(codec[-1])
        bit_success = sum(math.comb(r, k)*p**k*(1-p)**(r-k) for k in range(r//2+1))
        expected = bit_success**raw_bits
    elif codec == 'hamming74':
        expected = ((1-p)**7 + 7*p*(1-p)**6)**(raw_bits//4)
    else:
        byte_error = 1-(1-p)**8
        symbols = config['payload_bytes']+6
        expected = sum(math.comb(symbols, k)*byte_error**k*(1-byte_error)**(symbols-k) for k in range(3))
    expected = min(1., max(0., expected))
    se = math.sqrt(expected*(1-expected)/row.trials)
    # Diagnostic tolerance, not a confidence interval or a significance test.
    assert abs(row.success_rate-expected) <= 6*se + 3/row.trials, row
    analytic.append(dict(codec=codec, depth=int(row.depth), p=p,
                         analytic_success=expected, observed_success=row.success_rate,
                         difference_percentage_points=100*(row.success_rate-expected)))
save_json(study/'iid_analytic_check.json', analytic)

# Noise occupancy is checked using independent trial means, not treating
# correlated slots within a burst as independent Bernoulli observations.
for _, group in joined[joined.depth == 1].groupby(['scenario_id', 'codec']):
    occupancy = group.active_noise_slots/group.body_bits
    p = group.rate.iloc[0]
    assert abs(occupancy.mean()-p) <= 6*occupancy.std(ddof=1)/math.sqrt(len(group)) + 3/len(group)

messages = payloads(config)
max_slots = max(len(make_packet(bytes(messages[0]), codec, 0).body_bits) for codec in config['codecs'])
collision_cases = []
for _, row in joined[joined.undetected_wrong_payload == 1].iterrows():
    case = cases[cases.scenario_id == row.scenario_id].iloc[0]
    rng = np.random.default_rng(np.random.SeedSequence([config['seed'], 1, int(row.scenario_id)]))
    states = noise_states(rng, int(row.trial)+1, max_slots, case.model, case.rate, case.mean_burst_slots)[-1]
    packet = make_packet(bytes(messages[int(row.trial)]), row.codec, int(row.trial)%256)
    start = GUARD_BITS+len(PREAMBLE)
    header = parse_header(packet.bits[start:start+HEADER_BITS])
    wire = interleave(packet.body_bits, int(row.depth))
    decoded = receive_body(disturb(wire, states[:len(wire)], case.model), header, int(row.depth))
    received_crc = to_bytes(decoded['decoded_bits'])[-2:]
    assert decoded['crc_ok'] and decoded['payload'] != packet.payload
    assert received_crc == checksum(header['header']+decoded['payload'])
    collision_cases.append(dict(scenario_id=int(row.scenario_id), trial=int(row.trial),
        model=case.model, rate=case.rate, codec=row.codec, depth=int(row.depth),
        original_payload_hex=packet.payload.hex(), decoded_payload_hex=decoded['payload'].hex(),
        received_crc_hex=received_crc.hex(), recomputed_crc_hex=checksum(header['header']+decoded['payload']).hex(),
        payload_bit_errors=int(row.payload_errors), counted_as_success=False))
save_json(study/'crc_collision_cases.json', collision_cases)
check.update(complete_condition_counts=True, duplicate_trials=0,
    identical_symmetric_noise_per_pair=True, glare_direction_checked=True,
    clean_control_conditions=int((summary.rate == 0).sum()), analytic_iid_conditions_checked=len(analytic),
    noise_occupancy_checked_with_trial_level_variance=True,
    crc_valid_wrong_payload_events_replayed=len(collision_cases))
save_json(study/'independent_audit.json', check)
print(json.dumps(check, indent=2))
