import dataclasses
import unittest
import numpy as np
from optical_link.protocol import make_packet, GUARD_BITS, PREAMBLE, HEADER_BITS
from optical_link.receiver import synthetic_trace, decode_trace
try:
    from optical_link.baseline_analysis import receive_diagnostic, assess_received, error_structure
except ModuleNotFoundError:
    from baseline_analysis import receive_diagnostic, assess_received, error_structure


def transmission(packet):
    return {'payload_hex':packet.payload.hex(), 'transmitted_bits':''.join(map(str,packet.bits)),
            'codec':packet.codec, 'sequence':packet.sequence,
            'scheduled_channel_seconds':len(packet.bits)*.2}


class BaselineAnalysisTests(unittest.TestCase):
    def test_existing_decoder_equivalence_all_methods(self):
        for code in ['none','repeat3','repeat5','hamming74','rs4']:
            p=make_packet('ADRIAN',code,sequence=70)
            t,y=synthetic_trace(p,drop_fraction=0)
            old=decode_trace(t,y)
            new=receive_diagnostic(t,y)
            np.testing.assert_array_equal(old['body_bits'],new['body_bits'])
            self.assertEqual(old['payload'],new['payload'])
            m=assess_received(new,transmission(p))
            self.assertFalse(m['packet_failed'])
            self.assertEqual(m['payload_bit_errors'],0)

    def test_rs_rejection_retains_raw_errors_without_inventing_payload(self):
        p=make_packet('ADRIAN','rs4',sequence=71)
        damaged=p.bits.copy()
        first=GUARD_BITS+len(PREAMBLE)+HEADER_BITS
        damaged[first:first+24]^=1  # Three damaged symbols; exceeds two-symbol guarantee.
        t,y=synthetic_trace(dataclasses.replace(p,bits=damaged),drop_fraction=0,noise=0)
        r=receive_diagnostic(t,y)
        m=assess_received(r,transmission(p))
        self.assertEqual(m['body_channel_bit_errors'],24)
        self.assertEqual(m['damaged_rs_bytes'],3)
        self.assertEqual(m['failure_stage'],'fec')
        self.assertIsNone(m['payload_bit_errors'])
        self.assertTrue(m['packet_failed'])
        self.assertEqual(m['correct_payload_goodput_bps'],0)

    def test_mismatched_logs_never_count_channel_errors(self):
        p=make_packet('HI','none',sequence=9)
        t,y=synthetic_trace(p,drop_fraction=0)
        tx=transmission(p); tx['sequence']=10
        m=assess_received(receive_diagnostic(t,y),tx)
        self.assertEqual(m['status'],'association_error')
        self.assertIsNone(m['body_channel_bit_errors'])

    def test_hamming_miscorrection_uses_same_payload_denominator(self):
        p=make_packet('HI','hamming74',sequence=72)
        damaged=p.bits.copy();first=GUARD_BITS+len(PREAMBLE)+HEADER_BITS
        damaged[first:first+2]^=1  # Two parity errors can induce a data-bit error.
        t,y=synthetic_trace(dataclasses.replace(p,bits=damaged),drop_fraction=0,noise=0)
        m=assess_received(receive_diagnostic(t,y),transmission(p))
        self.assertEqual(m['systematic_payload_errors_before_correction'],0)
        self.assertEqual(m['payload_bit_errors'],1)
        self.assertFalse(m['crc_ok'])

    def test_no_signal_failure_is_not_zero_ber(self):
        p=make_packet('HI')
        t,y=synthetic_trace(p,drop_fraction=0)
        m=assess_received(receive_diagnostic(t,np.full_like(y,40)),transmission(p))
        self.assertEqual(m['failure_stage'],'acquisition')
        self.assertIsNone(m['body_channel_ber'])
        self.assertTrue(m['packet_failed'])

    def test_consecutive_runs_and_repetition_blocks_are_distinct(self):
        sent=np.zeros(12,dtype=np.uint8); rx=sent.copy(); rx[[2,3,4,9]]=1
        result=error_structure(sent,rx,'repeat3')
        self.assertEqual(result['consecutive_error_runs'],[{'start':2,'length':3},{'start':9,'length':1}])
        self.assertEqual(result['errors_per_code_block'],[1,2,0,1])
        self.assertEqual(result['blocks_exceeding_guaranteed_correction'],1)


if __name__=='__main__': unittest.main()
