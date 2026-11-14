import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from optical_link.protocol import (make_packet, parse_header, GUARD_BITS, PREAMBLE,
                                   HEADER_BITS, checksum, to_bits)
from optical_link.coding_experiments import (DEFAULT_CONFIG, interleaver_order,
    interleave, deinterleave, noise_states, disturb, receive_body, measure_trial,
    score_decoded, wilson, aggregate, scenarios, paired_outcomes, run_study, load_verified)


class CodingExperimentTests(unittest.TestCase):
    def test_ragged_interleaving_is_lossless_without_padding(self):
        rng = np.random.default_rng(51)
        for n in [1, 7, 8, 9, 24, 88, 120, 154, 264, 440]:
            for depth in [1, 2, 8, 99]:
                data = rng.integers(0, 2, n, dtype=np.uint8)
                np.testing.assert_array_equal(np.sort(interleaver_order(n, depth)), np.arange(n))
                np.testing.assert_array_equal(deinterleave(interleave(data, depth), depth), data)
                self.assertEqual(len(interleave(data, depth)), n)

    def test_all_codes_and_depths_recover_clean_payload_and_charge_framing(self):
        for codec in DEFAULT_CONFIG['codecs']:
            packet = make_packet('MANUNITED', codec, 91)
            for depth in [1, 8]:
                result = measure_trial(packet, np.zeros(len(packet.body_bits), bool), 'iid_flip', depth)
                self.assertEqual(result['success'], 1)
                self.assertEqual(result['payload_errors'], 0)
                self.assertAlmostEqual(result['airtime_seconds'], (len(packet.body_bits)+96)*.2)
                self.assertEqual(result['buffer_bits'], len(packet.body_bits) if depth == 8 else 0)

    def test_markov_stationarity_and_transition_probabilities(self):
        s = noise_states(np.random.default_rng(51), 5000, 200, 'burst_flip', .12, 8)
        self.assertAlmostEqual(s.mean(), .12, delta=.004)
        previous, following = s[:, :-1], s[:, 1:]
        leave = np.count_nonzero(previous & ~following)/np.count_nonzero(previous)
        enter = np.count_nonzero(~previous & following)/np.count_nonzero(~previous)
        self.assertAlmostEqual(leave, 1/8, delta=.004)
        self.assertAlmostEqual(enter, .12/(.88*8), delta=.002)

    def test_noise_prefix_is_shared_across_trial_batch_sizes(self):
        for model in DEFAULT_CONFIG['models']:
            full = noise_states(np.random.default_rng(5), 50, 440, model, .05, 8)
            small = noise_states(np.random.default_rng(5), 3, 440, model, .05, 8)
            np.testing.assert_array_equal(full[:3], small)

    def test_positive_glare_never_flips_ones_down(self):
        sent = np.array([0, 1, 0, 1], dtype=np.uint8)
        actual = disturb(sent, [1, 1, 0, 0], 'glare_burst')
        np.testing.assert_array_equal(actual, [1, 1, 0, 1])
        np.testing.assert_array_equal(disturb(sent, [1]*4, 'burst_flip'), 1-sent)

    def test_interleaving_rescues_a_burst_across_hamming_words(self):
        packet = make_packet('MANUNITED', 'hamming74', 23)
        burst = np.arange(len(packet.body_bits)) < 8
        plain = measure_trial(packet, burst, 'burst_flip', 1)
        spread = measure_trial(packet, burst, 'burst_flip', 8)
        self.assertEqual(plain['channel_errors'], spread['channel_errors'])
        self.assertEqual(plain['success'], 0)
        self.assertEqual(spread['success'], 1)

    def test_bit_interleaving_can_harm_byte_symbol_rs(self):
        packet = make_packet('MANUNITED', 'rs4', 23)
        burst = np.arange(len(packet.body_bits)) < 16
        self.assertEqual(measure_trial(packet, burst, 'burst_flip', 1)['success'], 1)
        self.assertEqual(measure_trial(packet, burst, 'burst_flip', 8)['success'], 0)
        self.assertGreater(np.count_nonzero(deinterleave(burst, 8).reshape(-1, 8).sum(axis=1)), 2)

    def test_uncoded_permutation_does_not_correct_symmetric_errors(self):
        packet = make_packet('MANUNITED', 'none', 23)
        for error in [0, 5, len(packet.body_bits)-1]:
            state = np.arange(len(packet.body_bits)) == error
            for depth in [1, 8]:
                self.assertEqual(measure_trial(packet, state, 'iid_flip', depth)['success'], 0)

    def test_crc_valid_wrong_payload_is_not_counted_as_delivered(self):
        packet = make_packet('MANUNITED', 'none', 23)
        offset = GUARD_BITS + len(PREAMBLE)
        header = parse_header(packet.bits[offset:offset+HEADER_BITS])
        changed = b'ABCDEFGHI'
        replacement = to_bits(changed + checksum(header['header'] + changed))
        decoded = receive_body(replacement, header, 1)
        self.assertTrue(decoded['crc_ok'])
        row = score_decoded(packet, packet.body_bits, replacement, decoded,
                            packet.body_bits != replacement, 1, .2)
        self.assertEqual(row['undetected_wrong_payload'], 1)
        self.assertEqual(row['success'], 0)
        self.assertEqual(row['delivered_bits'], 0)

    def test_failed_decodes_remain_in_rate_and_success_denominators(self):
        packet = make_packet('MANUNITED', 'rs4', 23)
        clean = measure_trial(packet, np.zeros(len(packet.body_bits), bool), 'iid_flip')
        broken = dict(clean, payload_errors=None, decoder_rejected=1, success=0,
                      crc_ok=0, exact_payload=0, delivered_bits=0)
        frame = pd.DataFrame([dict(scenario_id=0, trial=i, codec='rs4', depth=1, **r)
                              for i, r in enumerate([clean, broken])])
        result = aggregate(frame, [{'scenario_id': 0, 'model': 'iid_flip', 'rate': .1,
                                  'mean_burst_slots': 8, 'sweep': 'rate'}])[0]
        self.assertEqual(result['trials'], 2)
        self.assertEqual(result['payload_outputs'], 1)
        self.assertEqual(result['success_rate'], .5)
        self.assertAlmostEqual(result['goodput_bps'], 72/(2*clean['airtime_seconds']))

    def test_binomial_intervals_do_not_claim_certainty_at_boundaries(self):
        lo, hi = wilson(0, 2000)
        self.assertAlmostEqual(lo, 0)
        self.assertGreater(hi, 0)
        lo, hi = wilson(2000, 2000)
        self.assertLess(lo, 1)
        self.assertAlmostEqual(hi, 1)

    def test_invalid_noise_and_interleaver_inputs_fail(self):
        with self.assertRaises(ValueError): interleaver_order(0, 8)
        with self.assertRaises(ValueError): interleaver_order(88, 0)
        with self.assertRaises(ValueError): noise_states(np.random.default_rng(1), 2, 8, 'bad', .1)
        with self.assertRaises(ValueError): noise_states(np.random.default_rng(1), 2, 8, 'burst_flip', .9, 1)
        with self.assertRaises(ValueError): disturb([0, 1], [1], 'iid_flip')

    def test_small_study_replays_and_rejects_tampered_artifacts(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        config.update(trials_per_condition=4, rates=[0, .1], length_sweep_slots=[])
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'study'
            summary = run_study(root, output, config)
            frame, _, check = load_verified(root, output, replay_trials=2)
            self.assertEqual(len(summary), 60)
            self.assertEqual(len(frame), 240)
            self.assertEqual(check['replayed_decodes'], 120)
            self.assertEqual(sum(r['pairs'] for r in paired_outcomes(frame)), 120)
            with self.assertRaises(FileExistsError): run_study(root, output, config)
            with (output/'config.json').open('a') as f: f.write(' ')
            with self.assertRaisesRegex(ValueError, 'Saved simulation changed'):
                load_verified(root, output)


if __name__ == '__main__':
    unittest.main()
