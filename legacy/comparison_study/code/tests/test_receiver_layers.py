import unittest
import dataclasses
import numpy as np
from optical_link.protocol import make_packet,GUARD_BITS,PREAMBLE,HEADER_BITS
from optical_link.receiver import synthetic_trace
from optical_link.receiver_layers import decode_features,METHODS
from optical_link.baseline_analysis import assess_received,receive_diagnostic


def fixture(codec='none'):
    p=make_packet('HI',codec,sequence=80)
    t,y=synthetic_trace(p,noise=0,drop_fraction=0)
    # Static tile gradients test per-tile preamble normalization.
    tiles=y[:,None]+np.linspace(-10,10,25)[None,:]
    f={'original':y.copy(),'patch_mean':tiles.mean(axis=1),'tiles':tiles,
       'references':np.tile(np.array([30.,40.,50.,60.]),(len(t),1))}
    tx={'payload_hex':p.payload.hex(),'transmitted_bits':''.join(map(str,p.bits)),
        'codec':p.codec,'sequence':p.sequence,'scheduled_channel_seconds':len(p.bits)*.2}
    return p,t,f,tx


class ReceiverLayerTests(unittest.TestCase):
    def test_original_is_exactly_the_unchanged_receiver(self):
        p,t,f,tx=fixture('rs4')
        a=receive_diagnostic(t,f['original']);b=decode_features(t,f,'original')
        np.testing.assert_array_equal(a['body_bits'],b['body_bits'])
        self.assertEqual(a['payload'],b['payload']);self.assertEqual(a['period_seconds'],b['period_seconds'])

    def test_all_layers_decode_clean_signals_for_all_codes(self):
        for code in ['none','repeat3','repeat5','hamming74','rs4']:
            p,t,f,tx=fixture(code)
            for method in METHODS:
                r=decode_features(t,f,method)
                self.assertTrue(r['crc_ok'],(code,method,r))
                self.assertEqual(r['payload'],p.payload)

    def test_reference_cancels_shared_illumination_without_sent_bits(self):
        p,t,f,tx=fixture()
        first=GUARD_BITS+len(PREAMBLE)+HEADER_BITS
        start=2.015+first*.2
        disturbance=((t>start)&(t<start+1.8)).astype(float)*150
        f['original']+=disturbance;f['patch_mean']+=disturbance
        f['tiles']+=disturbance[:,None];f['references']+=disturbance[:,None]
        self.assertGreater(assess_received(decode_features(t,f,'patch_mean'),tx)['body_channel_bit_errors'],0)
        for method in ['reference','combined']:
            m=assess_received(decode_features(t,f,method,alpha=1),tx)
            self.assertEqual(m['body_channel_bit_errors'],0)
            self.assertFalse(m['packet_failed'])

    def test_spatial_rejects_local_glare_and_combined_handles_shared_shift(self):
        p,t,f,tx=fixture()
        start=2.015+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*.2
        bad=(t>start)&(t<start+1.8)
        f['tiles'][bad,:9]+=400
        f['patch_mean']=f['tiles'].mean(axis=1);f['original']=f['patch_mean'].copy()
        self.assertGreater(assess_received(decode_features(t,f,'patch_mean'),tx)['body_channel_bit_errors'],0)
        self.assertEqual(assess_received(decode_features(t,f,'spatial'),tx)['body_channel_bit_errors'],0)
        f['tiles'][bad]+=150;f['patch_mean']=f['tiles'].mean(axis=1);f['original']=f['patch_mean'].copy();f['references'][bad]+=150
        self.assertFalse(assess_received(decode_features(t,f,'combined'),tx)['packet_failed'])

    def test_uniform_unreferenced_saturation_is_not_magically_recovered(self):
        p,t,f,tx=fixture()
        start=2.015+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*.2
        bad=(t>start)&(t<start+1.8)
        f['tiles'][bad]=255;f['patch_mean'][bad]=255;f['original'][bad]=255
        for method in ['spatial','combined']:
            self.assertTrue(assess_received(decode_features(t,f,method),tx)['packet_failed'])

    def test_missing_samples_are_failures_not_interpolated_bits(self):
        p,t,f,tx=fixture()
        centre=2.015+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS+5.5)*.2
        keep=abs(t-centre)>.12
        r=decode_features(t[keep],{k:v[keep] for k,v in f.items()},'combined')
        self.assertEqual(r['failure_stage'],'body_sampling')
        m=assess_received(r,tx);self.assertTrue(m['packet_failed']);self.assertIsNone(m['payload_ber'])

    def test_header_and_acquisition_failures_are_preserved(self):
        p,t,f,tx=fixture()
        constant={k:np.full_like(v,40.) for k,v in f.items()}
        r=decode_features(t,constant,'combined');self.assertEqual(r['failure_stage'],'acquisition')
        self.assertTrue(assess_received(r,tx)['packet_failed'])

    def test_invalid_feature_shapes_and_gains_are_rejected(self):
        p,t,f,tx=fixture()
        for alpha in [-1,float('nan'),3]:
            r=decode_features(t,f,'reference',alpha=alpha);self.assertEqual(r['failure_stage'],'calibration')
        bad=dict(f,references=np.zeros((len(t)-1,4)))
        self.assertEqual(decode_features(t,bad,'combined')['failure_stage'],'calibration')

    def test_failed_outputs_stay_in_goodput_but_not_zero_payload_ber(self):
        from optical_link.receiver_study import summarize
        p,t,f,tx=fixture();good=assess_received(decode_features(t,f,'original'),tx)
        good.update(condition='clean',channel_seconds_including_overhead=1.)
        bad=dict(good,condition='noisy',packet_failed=True,status='decode_failed',
                 payload_bit_errors=None,body_channel_bit_errors=None,
                 channel_seconds_including_overhead=9.,correct_delivered_bits=0)
        s=summarize([good,bad])
        self.assertEqual(s['failures'],1)
        self.assertEqual(s['payload_outputs'],1)
        self.assertEqual(s['payload_bits_with_output'],16)
        self.assertEqual(s['goodput_bps'],1.6)

    def test_shared_clock_is_identical_across_processing_layers(self):
        p,t,f,tx=fixture('hamming74')
        results=[decode_features(t,f,m) for m in METHODS]
        self.assertEqual(len({r['start_seconds'] for r in results}),1)
        self.assertEqual(len({r['period_seconds'] for r in results}),1)


if __name__=='__main__':unittest.main()
