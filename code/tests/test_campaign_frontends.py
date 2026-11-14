import unittest
from dataclasses import replace
import numpy as np
from optical_link.protocol import make_packet,GUARD_BITS,PREAMBLE,HEADER_BITS
from optical_link.receiver import synthetic_trace
from optical_link.coding_experiments import interleave
from optical_link.campaign_frontends import decode,METHODS
from optical_link.physical_campaign_receiver import decode_pilot

def features(y):
    return dict(original=y,patch_mean=y.copy(),tiles=np.tile(y[:,None],(1,16)),
                references=np.tile([30.,30.,220.,220.],(len(y),1)))

class CampaignFrontendsTests(unittest.TestCase):
    def test_clean_codes_depths_and_layers(self):
        for code in ('none','repeat3','repeat5','hamming74','rs4'):
            for depth in (1,8):
                p=make_packet('A7k2',code,7);bits=p.bits.copy();first=GUARD_BITS+len(PREAMBLE)+HEADER_BITS
                bits[first:-GUARD_BITS]=interleave(bits[first:-GUARD_BITS],depth)
                t,y=synthetic_trace(replace(p,bits=bits),noise=0,drop_fraction=0)
                for method in METHODS:
                    d=decode(t,features(y),method,depth=depth)
                    self.assertTrue(d.get('crc_ok'),(code,depth,method,d.get('failure_reason')))
                    self.assertEqual(d['payload'],p.payload)
                    self.assertEqual(d['period_seconds'],.2)

    def test_original_exactly_matches_frozen_receiver(self):
        p=make_packet('A7k2','none');t,y=synthetic_trace(p,noise=6,drop_fraction=0)
        a=decode_pilot(t,y);b=decode(t,features(y))
        np.testing.assert_array_equal(a['wire_body_bits'],b['wire_body_bits'])
        self.assertEqual(a['start_seconds'],b['start_seconds'])

    def test_unobservable_preamble_is_not_recovered_by_truth(self):
        t=np.arange(0,30,1/30);y=np.full(len(t),50.)
        for method in METHODS:self.assertEqual(decode(t,features(y),method)['failure_stage'],'acquisition')

    def test_common_illumination_is_corrected_but_uniform_occlusion_is_not(self):
        p=make_packet('A7k2','none');t,y=synthetic_trace(p,noise=0,drop_fraction=0)
        f=features(y);bad=(t>24)&(t<25)
        for key in f:f[key][bad]+=140
        self.assertFalse(decode(t,f,'original').get('crc_ok',False))
        self.assertTrue(decode(t,f,'reference').get('crc_ok',False))
        for key in ('original','patch_mean','tiles'):f[key][bad]=0
        self.assertFalse(decode(t,f,'spatial').get('crc_ok',False))

    def test_sampling_gap_is_not_interpolated(self):
        p=make_packet('A7k2','none');t,y=synthetic_trace(p,noise=0,drop_fraction=0)
        keep=abs(t-23.9)>.2
        for method in METHODS:
            d=decode(t[keep],features(y[keep]),method)
            self.assertEqual(d['failure_stage'],'body_sampling')

if __name__=='__main__':unittest.main()
