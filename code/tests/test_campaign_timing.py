"""Configured timing is fixed before decoding; failures never trigger a clock search."""
from dataclasses import replace
from unittest.mock import patch
import unittest
import numpy as np
from optical_link.protocol import make_packet, GUARD_BITS, PREAMBLE, HEADER_BITS
from optical_link.receiver import synthetic_trace, find_preamble
from optical_link.physical_campaign_receiver import decode_pilot

class CampaignTimingTests(unittest.TestCase):
    def trace(self, packet, bit_ms=200):
        return synthetic_trace(packet,bit_ms=bit_ms,fps=30,drop_fraction=0,noise=0)

    def test_default_does_not_extrapolate_biased_preamble_clock(self):
        packet=make_packet('A7k2M9q4R6v8','none',1)
        t,y=self.trace(packet)
        sync=find_preamble(t,y)
        biased=dict(sync,period_seconds=.201)
        with patch('optical_link.physical_campaign_receiver.find_preamble',return_value=biased):
            corrected=decode_pilot(t,y)
            historical=decode_pilot(t,y,timing='estimated')
        self.assertTrue(corrected['crc_ok'])
        self.assertEqual(corrected['payload'],packet.payload)
        self.assertEqual(corrected['timing_policy'],'configured')
        self.assertEqual(corrected['period_seconds'],.2)
        self.assertEqual(corrected['estimated_period_seconds'],.201)
        self.assertFalse(historical.get('crc_ok',False))

    def test_configured_duration_is_not_hardcoded_to_200ms(self):
        packet=make_packet('A7k2M9q4R6v8','repeat5',6)
        t,y=self.trace(packet,250)
        result=decode_pilot(t,y,bit_ms=250)
        self.assertEqual(result['period_seconds'],.25)
        self.assertTrue(result['crc_ok'])
        self.assertEqual(result['payload'],packet.payload)

    def test_crc_failure_is_retained_without_fallback(self):
        packet=make_packet('A7k2M9q4','none',1)
        wire=packet.bits.copy();wire[GUARD_BITS+len(PREAMBLE)+HEADER_BITS+10]^=1
        t,y=self.trace(replace(packet,bits=wire))
        result=decode_pilot(t,y)
        self.assertFalse(result['crc_ok'])
        self.assertEqual(result['failure_stage'],'crc')
        self.assertEqual(result['timing_policy'],'configured')
        self.assertEqual(result['period_seconds'],.2)

    def test_diagnostic_is_same_policy_with_explicit_label(self):
        t,y=self.trace(make_packet('A7k2','none'))
        a=decode_pilot(t,y);b=decode_pilot(t,y,timing='nominal_diagnostic')
        np.testing.assert_array_equal(a['wire_body_bits'],b['wire_body_bits'])
        self.assertEqual(b['timing_policy'],'nominal_diagnostic')

if __name__=='__main__':unittest.main()
