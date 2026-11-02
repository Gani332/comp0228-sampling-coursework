"""Offline tests of actual wire order, capture evidence and failure preservation."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import shutil
import unittest
import numpy as np
from optical_link import physical_campaign as c
from optical_link.protocol import GUARD_BITS,PREAMBLE,HEADER_BITS,parse_header,unpack_body
from optical_link.coding_experiments import deinterleave
from optical_link.receiver import synthetic_trace
from optical_link.physical_campaign_receiver import decode_pilot

ROOT=Path(__file__).resolve().parents[2]
class FakeTX:
    calls=[]
    fail_at=None
    def __init__(self,port):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def light(self,white):pass
    def transmit(self,packet,bit_ms,log_path,on_progress):
        self.calls.append(packet.bits.copy())
        on_progress(0,'START')
        if self.fail_at==len(self.calls):raise IOError('USB interrupted')
        on_progress(len(packet.bits)*bit_ms/1000+.2,'DONE')
        c.save(log_path,dict(transmitted_bits=''.join(map(str,packet.bits)),status='controller_completed'))

class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/c.PLAN).parent.mkdir(parents=True)
        shutil.copyfile(ROOT/c.PLAN,self.root/c.PLAN)
        FakeTX.calls=[];FakeTX.fail_at=None
    def tearDown(self):self.tmp.cleanup()
    def run_pilot(self,sid=None,**kwargs):
        return c.run_session(self.root,sid or c.next_session(self.root),'fake',{'phone':'test'},
                             transmitter_factory=FakeTX,sleep=lambda _:None,**kwargs)
    def test_manifest_balanced_and_no_duplicate_id(self):
        sessions=c.load_sessions(self.root);rows=[r for group in sessions.values() for r in group]
        self.assertEqual(len(rows),82)
        self.assertEqual(len({r['packet_id'] for r in rows}),82)
        self.assertEqual(len(sessions),21)
        for phase,count in [('pilot',16),('calibration',6),('main',54),('holdout',6)]:
            self.assertEqual(sum(r['phase']==phase for r in rows),count)
        main=[r for r in rows if r['phase']=='main']
        expected={(codec,'1') for codec in ('none','repeat3','repeat5','hamming74','rs4')}|{('hamming74','8'),('rs4','8')}
        for codec,depth in expected:
            self.assertEqual(sum(r['condition']=='OCC_CLUSTER' and r['codec']==codec and r['interleave_depth']==depth for r in main),6)
        for codec in ('none','hamming74'):
            self.assertEqual(sum(r['condition']=='GLARE_BODY' and r['codec']==codec for r in main),6)
        self.assertTrue(all(r['condition']=='GLARE_PREAMBLE' for r in rows if r['phase']=='holdout'))
    def test_calibration_is_development_and_needs_no_freeze(self):
        sid=c.next_session(self.root,'calibration')
        folder=self.run_pilot(sid=sid)
        log=json.loads((folder/'session.json').read_text())
        self.assertEqual(log['phase'],'calibration')
        self.assertNotIn('analysis_freeze',log)
        self.assertTrue(all(r['evidence_role']=='development_only' for r in log['packets']))
    def test_wire_order_and_independent_decode_every_configuration(self):
        group=next(rows for rows in c.load_sessions(self.root).values() if rows[0]['phase']=='main')
        first=GUARD_BITS+len(PREAMBLE)+HEADER_BITS
        for row in group:
            original,wire=c.wire_packet(row)
            np.testing.assert_array_equal(wire.bits[:first],original.bits[:first])
            np.testing.assert_array_equal(wire.bits[-GUARD_BITS:],original.bits[-GUARD_BITS:])
            h=parse_header(original.bits[GUARD_BITS+len(PREAMBLE):first])
            restored=deinterleave(wire.bits[first:-GUARD_BITS],int(row['interleave_depth']))
            decoded=unpack_body(h,restored)
            self.assertTrue(decoded['crc_ok']);self.assertEqual(decoded['payload'],original.payload)
            t,y=synthetic_trace(wire,seed=8,drop_fraction=0,noise=0)
            rx=decode_pilot(t,y,depth=int(row['interleave_depth']))
            self.assertTrue(rx.get('crc_ok'),rx);self.assertEqual(rx['payload'],original.payload)
    def test_run_logs_actual_wire_and_next_session(self):
        sid=c.next_session(self.root);folder=self.run_pilot()
        log=json.loads((folder/'session.json').read_text())
        self.assertEqual(log['status'],'controller_completed')
        self.assertNotEqual(c.next_session(self.root),sid)
        self.assertEqual(len(FakeTX.calls),4)
        for entry,bits in zip(log['packets'],FakeTX.calls):
            tx=json.loads((folder/entry['tx_file']).read_text())
            self.assertEqual(tx['transmitted_bits'],''.join(map(str,bits)))
            self.assertEqual(tx['wire_bits'],entry['wire_bits'])
            self.assertEqual(tx['interleave_depth'],entry['interleave_depth'])
            self.assertEqual(tx['_condition'],'CLEAN')
    def test_failure_keeps_sent_failed_and_unsent_and_blocks_silent_retry(self):
        FakeTX.fail_at=2
        with self.assertRaises(IOError):self.run_pilot()
        folder,log=c.attempts(self.root)[0]
        self.assertEqual([r['status'] for r in log['packets']],['controller_completed','failed_or_interrupted','not_started','not_started'])
        with self.assertRaisesRegex(ValueError,'unfinished'):c.next_session(self.root)
        FakeTX.calls=[];FakeTX.fail_at=None
        new=self.run_pilot(sid=log['session_id'],retake=True)
        self.assertNotEqual(new,folder);self.assertTrue(folder.exists())
    def test_repeated_completed_session_requires_explicit_retake(self):
        sid=c.next_session(self.root);self.run_pilot()
        with self.assertRaisesRegex(ValueError,'Attempt already'):self.run_pilot(sid=sid)
    def test_main_is_not_released_by_software_success(self):
        sid=c.next_session(self.root,'main')
        with self.assertRaisesRegex(ValueError,'Pilot review'):self.run_pilot(sid=sid)
        self.assertEqual(FakeTX.calls,[])
    def test_cues_clear_between_actions_and_record_lateness(self):
        row=next(rows[0] for rows in c.load_sessions(self.root).values() if rows[0]['condition']=='OCC_SPLIT')
        row=dict(row,events=[dict(start_after_START_ack_s=3.,duration_target_s=.4,kind='full_patch_occlusion'),dict(start_after_START_ack_s=5.,duration_target_s=.4,kind='full_patch_occlusion')])
        shown=[];cue=c.Cue(row,shown.append)
        cue(0,'START');cue(3.05);cue(3.45)
        self.assertEqual(shown[-2]['state'],'active')
        self.assertIn('CLEAR',shown[-1]['text'])
        self.assertAlmostEqual(cue.transitions[-2]['cue_lateness_seconds'],.05)
        cue(6,'DONE');self.assertEqual(cue.record()['events_without_active_display'],[1])
    def test_video_copy_preserves_source_and_rejects_reuse(self):
        first=self.run_pilot();second=self.run_pilot()
        video=self.root/'phone.MOV';video.write_bytes(b'test-placeholder-not-a-real-video')
        copy=c.attach_video(self.root,first,video)
        self.assertEqual(copy.read_bytes(),video.read_bytes())
        self.assertEqual(json.loads((first/'session.json').read_text())['video']['raw_video_validation'],'pending')
        with self.assertRaisesRegex(ValueError,'already assigned'):c.attach_video(self.root,second,video)
        with self.assertRaisesRegex(ValueError,'already attached'):c.attach_video(self.root,first,video)
    def test_cancel_never_opens_serial(self):
        from optical_link.physical_campaign_ui import Recorder
        c.save(self.root/c.DATA/'setup.json',{'phone':'test'})
        r=Recorder(self.root)
        with patch('builtins.input',return_value='cancel'),patch('optical_link.physical_campaign_ui.run_session') as run:
            self.assertIsNone(r.record_next(port='fake'))
        run.assert_not_called()
    def test_corrupt_schedule_rejected_before_transmission(self):
        p=self.root/c.PLAN;p.write_text(p.read_text().replace('PILOT_T1_L4_seq','PILOT_T1_L4_seq',1).replace(',144,',',145,',1))
        with self.assertRaisesRegex(ValueError,'length mismatch'):c.load_sessions(self.root)


class PickerTests(unittest.TestCase):
    def test_picker_cancel_does_not_attach(self):
        from optical_link.physical_campaign_ui import Recorder
        from types import SimpleNamespace
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/c.PLAN).parent.mkdir(parents=True)
            shutil.copyfile(ROOT/c.PLAN,root/c.PLAN)
            folder=root/c.DATA/'attempts'/'test';folder.mkdir(parents=True)
            c.save(folder/'session.json',dict(session_id='PILOT_T1_L4',status='controller_completed',video=None))
            r=Recorder(root)
            with patch('sys.platform','darwin'),patch('subprocess.run',return_value=SimpleNamespace(returncode=1)) as picker,patch.object(r,'attach') as attach:
                self.assertIsNone(r.attach_next())
            picker.assert_called_once();attach.assert_not_called()

class BalancedSequenceTests(unittest.TestCase):
    def test_sequence_ids_are_not_fixed_to_code_or_interleaving(self):
        sessions=c.load_sessions(ROOT)
        main=[r for group in sessions.values() for r in group if r['phase']=='main']
        configs={(r['codec'],r['interleave_depth']) for r in main if r['condition']=='OCC_CLUSTER'}
        for codec,depth in configs:
            ids=[int(r['sequence']) for r in main if r['codec']==codec and r['interleave_depth']==depth and r['condition']=='OCC_CLUSTER']
            self.assertEqual(len(set(ids)),6)
        for block in range(1,7):
            group=[r for r in main if int(r['block'])==block]
            self.assertEqual(len({r['payload_hex'] for r in group}),1)
            self.assertEqual(len(group),9)
            for r in group:
                self.assertEqual(bytes.fromhex(r['payload_hex']).decode(),r['payload_utf8'])

if __name__=='__main__':unittest.main()
