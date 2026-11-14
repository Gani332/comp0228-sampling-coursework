import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from optical_link.comparison_runner import (STUDY, load_cache, resolve_recording, physical,
    modeled, aggregate, run, write_csv, recording_slug, tx_for)
from optical_link.receiver_layers import METHODS, COMPARISON_METHODS, decode_features, decode_comparison
from optical_link.recording_model import calibrate
from optical_link.protocol import CODECS, make_packet
from optical_link.coding_experiments import interleave, deinterleave

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    packet = make_packet('HI', 'none', 42)
    t = np.arange(0, len(packet.bits)*.2, 1/30)
    slot = np.minimum((t/.2).astype(int), len(packet.bits)-1)
    y = 30+180*packet.bits[slot].astype(float)
    f = dict(original=y.copy(), patch_mean=y.copy(), tiles=np.repeat(y[:,None],25,axis=1),
             references=np.tile([30.,40.,50.,60.],(len(t),1)))
    return [('test', t, f, tx_for(packet))]


class ComparisonTests(unittest.TestCase):
    def test_noiseless_grid_and_pairing(self):
        windows = fixture()
        model = calibrate(windows)
        packets = [make_packet('HI', c, 42) for c in CODECS]
        t, residual = model.timeline(np.random.default_rng(2), max(len(p.bits) for p in packets)*.2)
        self.assertGreater(t[-1], max(len(p.bits) for p in packets)*.2-.1)
        for p in packets:
            keep = t < len(p.bits)*.2
            for depth in (1,8):
                f = model.features(p,depth,t[keep],residual[keep],disturbed=False)
                before = {k:a.copy() for k,a in f.items()}
                for method in COMPARISON_METHODS:
                    rx = decode_comparison(t[keep], f, method, depth=depth)
                    self.assertTrue(rx.get('crc_ok'), (p.codec,depth,method,rx.get('failure_reason')))
                    self.assertEqual(rx['payload'],p.payload)
                for k in f: np.testing.assert_array_equal(f[k],before[k])

    def test_archived_compatibility_all_caches(self):
        # All historical retained recordings, five methods; not coding study's 480k decodes.
        original = ROOT/'code/optical_link/comparison_provenance/receiver_layers_original.py'
        info = json.loads(original.with_name('snapshot.json').read_text())
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),info['sha256'])
        config = json.loads((ROOT/STUDY/'frozen_config.json').read_text())
        self.assertEqual(info['sha256'],config['receiver_source_sha256'])
        spec = importlib.util.spec_from_file_location('optical_link._comparison_original', original)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for video in json.loads((ROOT/STUDY/'manifest.json').read_text()):
            windows,_ = load_cache(ROOT,video)
            for pid,t,f,tx in windows:
                for method in METHODS:
                    old = module.decode_features(t,f,method,quantile=.25)
                    new = decode_comparison(t,f,method)
                    for key in ('body_bits','decoded_bits','payload','crc_ok','failure_stage','sequence'):
                        if key in old: np.testing.assert_equal(new[key],old[key],err_msg=pid+' '+method+' '+key)
                    archived = json.loads((ROOT/STUDY/'results'/method/(pid+'_receiver.json')).read_text())
                    for key in ('body_bits','decoded_bits','crc_ok','failure_stage'):
                        if key in archived: np.testing.assert_equal(new[key],archived[key],err_msg=pid+' '+method+' archived '+key)
                    if 'payload' in archived:
                        self.assertEqual(new['payload'].hex(),archived['payload'])

    def test_physical_and_modeled_counts_determinism(self):
        identity = dict(recording_id='test', evidence_kind='physical_replay')
        rows = physical(fixture(),identity)
        self.assertEqual(len(rows),7)
        self.assertTrue(all(r['actual_codec']=='none' and r['interleave_depth']==1 for r in rows))
        identity['evidence_kind']='modeled_replay'
        a,meta = modeled(fixture(),identity,2,42)
        b,_ = modeled(fixture(),identity,2,42)
        for rows in (a,b):
            for row in rows: row.pop('processing_seconds')
        self.assertEqual(a,b)
        summary = aggregate([dict(r,processing_seconds=0) for r in a])
        self.assertEqual(len(summary),70)
        self.assertTrue(all(r['trials_attempted']==2 for r in summary))
        self.assertTrue(all(r['success_rate']==1 for r in summary))
        self.assertTrue(all(r['goodput_bps']==r['total_correct_delivered_bits']/r['total_airtime_seconds'] for r in summary))

    def test_ragged_interleave(self):
        for n in (1,7,16,37):
            for depth in (1,8,100):
                a = np.arange(n)%2
                np.testing.assert_array_equal(deinterleave(interleave(a,depth),depth),a)

    def test_resolver_and_missing_cache(self):
        with self.assertRaisesRegex(ValueError,'ambiguous'): resolve_recording(ROOT,'recording.mov')
        with self.assertRaisesRegex(ValueError,'unregistered'): resolve_recording(ROOT,'unknown.MOV')
        video,_ = resolve_recording(ROOT,'G02')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'cache'): load_cache(Path(folder),video)
        self.assertEqual(recording_slug('../a strange!'), 'a_strange')

    def test_null_boolean_unicode_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'rows.csv'
            write_csv(p,[dict(payload='你好',ber=None,crc=False)])
            with p.open() as f: row=next(csv.DictReader(f))
            self.assertEqual(row,dict(payload='你好',ber='',crc='False'))

    def test_end_to_end_new_directories_and_png(self):
        with tempfile.TemporaryDirectory() as folder:
            a=run(ROOT,mode='physical',output=folder,trials=1)
            b=run(ROOT,mode='physical',output=folder,trials=1)
            self.assertNotEqual(a,b)
            with (a/'G02__physical_results.csv').open() as f: self.assertEqual(len(list(csv.DictReader(f))),28)
            self.assertGreater((a/'G02__physical_comparison.png').stat().st_size,1000)
            self.assertTrue((a/'G02__run_metadata.json').exists())

    def test_optical_errors_correct_before_crc_and_interleaving_before_fec(self):
        from optical_link.protocol import GUARD_BITS, PREAMBLE, HEADER_BITS
        model = calibrate(fixture())
        first = GUARD_BITS+len(PREAMBLE)+HEADER_BITS
        for codec, errors, success in [('none',1,False),('repeat3',1,True),('repeat5',2,True),('hamming74',1,True),('rs4',16,True)]:
            p = make_packet('HI', codec, 42)
            for depth in (1,8):
                # Correctable errors are defined before permutation. Flip measured
                # wire slots after permutation, so restoration must precede FEC.
                error = np.zeros(len(p.body_bits),np.uint8); error[:errors]=1
                wire_error = interleave(error,depth)
                t = np.arange(0,len(p.bits)*.2,1/30)
                f = model.features(p,depth,t,np.zeros((len(t),len(model.low))),disturbed=False)
                slot = (t/.2).astype(int)-first
                valid = (slot>=0)&(slot<len(error))
                flip = np.zeros(len(t),bool); flip[valid]=wire_error[slot[valid]].astype(bool)
                f['original'][flip] = model.low[0]+model.high[0]-f['original'][flip]
                rx = decode_comparison(t,f,'original',depth=depth)
                self.assertEqual(bool(rx.get('crc_ok')),success,(codec,depth,rx.get('failure_reason')))
                if success: self.assertEqual(rx['payload'],p.payload)

    def test_longest_body_tail_and_clean_prefix(self):
        from optical_link.protocol import GUARD_BITS, PREAMBLE, HEADER_BITS
        model = calibrate(fixture())
        packet = make_packet('HI','repeat5',42)
        t = np.arange(0,len(packet.bits)*.2,1/30)
        residual = np.ones((len(t),len(model.low)))*3
        clean = model.features(packet,1,t,residual,disturbed=False)
        noisy = model.features(packet,1,t,residual)
        first = (GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*.2
        end = (len(packet.bits)-GUARD_BITS)*.2
        body = (t>=first)&(t<end)
        np.testing.assert_array_equal(noisy['original'][~body],clean['original'][~body])
        np.testing.assert_allclose(noisy['original'][body]-clean['original'][body],3)
        self.assertGreater(t[body][-1],end-.05)

    def test_corrupt_cache_and_bad_configuration_abort(self):
        import shutil
        video,_ = resolve_recording(ROOT,'G02')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/STUDY/'features'; target.mkdir(parents=True)
            shutil.copy(ROOT/STUDY/'features/G02.json',target/'G02.json')
            (target/'G02.npz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'SHA-256'): load_cache(Path(folder),video)
        _,t,f,_ = fixture()[0]
        with self.assertRaises(ValueError): decode_comparison(t,f,'ewma',filter_parameters={'tau_seconds':-1})
        with self.assertRaises(ValueError): decode_comparison(t,f,'invalid')
        with self.assertRaises(ValueError): decode_comparison(t,f,depth=0)

    def test_modeled_clock_uses_clean_prefix_only(self):
        from optical_link.protocol import GUARD_BITS, PREAMBLE, HEADER_BITS
        model=calibrate(fixture())
        p=make_packet('HI','repeat5',42)
        t=np.arange(0,len(p.bits)*.2,1/30)
        prefix=(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*.2
        f=model.features(p,1,t,np.zeros((len(t),len(model.low))))
        clean=decode_comparison(t,f,'original',acquisition_end_seconds=prefix)
        f['original'][t>=prefix]=255
        for method in COMPARISON_METHODS:
            rx=decode_comparison(t,f,method,acquisition_end_seconds=prefix)
            self.assertEqual(rx['start_seconds'],clean['start_seconds'])
            self.assertEqual(rx['period_seconds'],clean['period_seconds'])
