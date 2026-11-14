"""End-to-end synthetic files; no camera/display and no historic-data mutation."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import importlib.util
import sys
import cv2
import numpy as np
from optical_link.screen_capture_packet import prepare, save_json
from optical_link.screen_recording_comparison import prepare_recording, load, resolve, digest
from optical_link.comparison_runner import run
from optical_link.protocol import GUARD_BITS


class ScreenComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.capture=self.root/'data/screen/receiver/test'
        self.tx=self.root/'data/screen/transmitter/test'
        self.capture.mkdir(parents=True);self.tx.mkdir(parents=True)
        self.plan=[prepare('HI','none',1,False),prepare('HI','repeat3',2,True)]
        entries=[]; observations=[]; starts=[]; next_start=2.
        for i,p in enumerate(self.plan,1):
            entry=p.record(i);entry.update(status='completed',filename=f'tx_{i}.json')
            save_json(self.tx/entry['filename'],entry);entries.append(entry)
            starts.append(next_start)
            observations.append(dict(sequence=i,codec=p.packet.codec,payload_bytes=2,
                                     estimated_preamble_start=next_start+GUARD_BITS*.2))
            next_start+=len(p.wire_bits)*.2+8
        save_json(self.tx/'manifest.json',dict(session_id='test',entries=entries))
        times=np.arange(.025,next_start,1/20)
        video=self.capture/'rx_test.avi'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),20,(60,40))
        self.assertTrue(writer.isOpened())
        for t in times:
            bit=0
            for start,p in zip(starts,self.plan):
                slot=int(np.floor((t-start)/.2))
                if 0<=slot<len(p.wire_bits): bit=int(p.wire_bits[slot])
            image=np.full((40,60,3),50,np.uint8)
            image[5:26,5:28]=30+180*bit
            image[5:15,40:50]=30
            image[25:35,40:50]=210
            writer.write(image)
        writer.release()
        frames=self.capture/'rx_test_frames.csv'
        with frames.open('w',newline='') as f:
            rows=csv.writer(f);rows.writerow(['frame_index','read_before_seconds','read_return_seconds'])
            rows.writerows((i,t-.001,t) for i,t in enumerate(times))
        meta=dict(status='stopped',unwritten_reads=0,capture_id='test',roi=[5,5,23,21],
                  video_dimensions=[60,40],written_frames=len(times),bit_ms=200,
                  observations=observations,checksums={p.name:digest(p) for p in (video,frames)})
        save_json(self.capture/'rx_test_capture.json',meta)

    def tearDown(self): self.tmp.cleanup()

    def prepare(self):
        return prepare_recording(self.root,self.capture,self.tx,'screen-test',[[40,5,10,10],[40,25,10,10]])

    def test_prepare_physical_and_modeled(self):
        descriptor=self.prepare()
        self.assertEqual(resolve(self.root,'screen-test'),descriptor)
        windows,meta=load(descriptor,self.root)
        self.assertEqual([w[3]['interleave_depth'] for w in windows],[1,8])
        self.assertEqual(meta['study_roi'],[5,5,23,21])
        for mode in ['physical','modeled']:
            out=run(self.root,recording='screen-test',mode=mode,trials=1,seed=2)
            result=out/('screen-test__physical_results.csv' if mode=='physical' else 'screen-test__modeled_trials.csv')
            with result.open() as f: rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),14 if mode=='physical' else 70)
            if mode=='physical':
                self.assertTrue(all(r['packet_success']=='True' for r in rows))
            else:
                self.assertTrue(any(r['packet_success']=='True' for r in rows))
                self.assertTrue(all(r['evidence_kind']=='modeled_replay' for r in rows))
            if mode=='physical':
                self.assertTrue(all(r['interleave_depth']=='8' for r in rows[7:]))
                self.assertTrue(all(float(r['channel_ber'])==0 for r in rows))
        with self.assertRaisesRegex(ValueError,'already exists'):self.prepare()

    def test_batch_routes_prepared_recordings(self):
        descriptor=self.prepare()
        tools=Path(__file__).resolve().parents[1]/'tools'
        sys.path.insert(0,str(tools))
        try:
            spec=importlib.util.spec_from_file_location('screen_batch_test',tools/'run_batch_comparison.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with patch.object(module,'ROOT',self.root), patch.object(module.run_recording_comparison,'main') as single:
                module.main(['--source','screen','--mode','physical'])
            command=single.call_args[0][0]
            self.assertEqual(Path(command[command.index('--recording')+1]).resolve(),descriptor.resolve())
            self.assertIn('data/screen/batch_results',command[command.index('--output')+1])
        finally:
            sys.path.remove(str(tools))

    def test_wire_order_used_for_model_calibration(self):
        descriptor=self.prepare()
        from optical_link.comparison_runner import modeled
        with patch('optical_link.comparison_runner.modeled',wraps=modeled) as model:
            run(self.root,recording='screen-test',mode='modeled',trials=1,seed=2)
        windows=model.call_args[0][0]
        self.assertEqual(windows[1][3]['transmitted_bits'],''.join(map(str,self.plan[1].wire_bits)))

    def test_source_mutation_rejected(self):
        descriptor=self.prepare()
        with (self.tx/'tx_1.json').open('a') as f:f.write(' ')
        with self.assertRaisesRegex(ValueError,'source changed'):load(descriptor,self.root)

    def test_mismatched_wire_rejected(self):
        p=self.tx/'manifest.json';m=json.loads(p.read_text())
        m['entries'][1]['wire_bits'][90]^=1
        save_json(p,m)
        with self.assertRaisesRegex(ValueError,'disagreement'):self.prepare()

    def test_reference_geometry_rejected(self):
        with self.assertRaisesRegex(ValueError,'overlap'):
            prepare_recording(self.root,self.capture,self.tx,'bad',[[5,5,10,10],[40,25,10,10]])


if __name__=='__main__':unittest.main()
