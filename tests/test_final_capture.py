import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import numpy as np

from optical_link.protocol import (make_packet, encode_body, decode_body, to_bits, to_bytes,
                                   parse_header, unpack_body, GUARD_BITS, PREAMBLE, HEADER_BITS)
from optical_link.receiver import synthetic_trace, decode_trace
from optical_link.capture import (capture_plan, load_capture_plan, new_batch_attempt, BodyCue,
                                  run_batch, batch_attempts, attach_batch_video, capture_status)


class RSTests(unittest.TestCase):
    def test_every_two_byte_position_combination_in_short_codewords(self):
        for message in [b'MANUNITED', b'ADRIAN', b'OMAR']:
            encoded = to_bytes(encode_body(to_bits(message), 'rs4'))
            for a,b in itertools.combinations(range(len(encoded)), 2):
                damaged = bytearray(encoded);damaged[a] ^= 0xa5;damaged[b] ^= 0x5a
                self.assertEqual(to_bytes(decode_body(to_bits(damaged),'rs4')),message)

    def test_full_packet_round_trip_including_crc_and_sampled_trace(self):
        for message in ['MANUNITED','ADRIAN','OMAR']:
            packet=make_packet(message,'rs4',sequence=99)
            t,y=synthetic_trace(packet,noise=8,drop_fraction=0)
            result=decode_trace(t,y)
            self.assertEqual(result['payload'],message.encode())
            self.assertTrue(result['crc_ok'])
            self.assertEqual(result['sequence'],99)
        packet=make_packet(bytes(range(64)),'rs4')
        start=GUARD_BITS+len(PREAMBLE)
        header=parse_header(packet.bits[start:start+HEADER_BITS])
        self.assertEqual(unpack_body(header,packet.body_bits)['payload'],bytes(range(64)))

    def test_over_capacity_rejects_or_crc_detects_corruption(self):
        packet=make_packet('MANUNITED','rs4',sequence=99)
        start=GUARD_BITS+len(PREAMBLE)
        header=parse_header(packet.bits[start:start+HEADER_BITS])
        rng=np.random.default_rng(31)
        for _ in range(100):
            damaged=bytearray(to_bytes(packet.body_bits))
            for i in rng.choice(len(damaged),3,replace=False):damaged[i]^=int(rng.integers(1,256))
            try: result=unpack_body(header,to_bits(damaged))
            except ValueError:continue
            self.assertFalse(result['crc_ok'])


class CaptureTests(unittest.TestCase):
    def test_plain_cell_cancel_never_starts_hardware(self):
        from optical_link.capture_cell import record_batch_cell
        with tempfile.TemporaryDirectory() as td, patch('builtins.input',return_value='cancel'), patch('optical_link.capture_cell.run_batch') as send:
            (Path(td)/'optical_link').mkdir()
            self.assertIsNone(record_batch_cell('B01',root=td,port='fake'))
            send.assert_not_called()
            self.assertEqual(batch_attempts(td),[])

    def test_plain_cell_completed_batch_does_not_prompt_or_send(self):
        from optical_link.capture_cell import record_batch_cell
        with tempfile.TemporaryDirectory() as td, patch('builtins.input') as prompt, patch('optical_link.capture_cell.run_batch') as send:
            (Path(td)/'optical_link').mkdir()
            plan=load_capture_plan(td);folder,r=new_batch_attempt(td,plan['batches'][0],{})
            r['status']='controller_completed';(folder/'batch.json').write_text(json.dumps(r))
            self.assertEqual(record_batch_cell('B01',root=td,port='fake'),folder.resolve())
            prompt.assert_not_called();send.assert_not_called()

    def test_plain_cell_enter_runs_selected_batch_and_shows_sweep_cue(self):
        from optical_link.capture_cell import record_batch_cell
        def fake_send(root,plan,batch_id,port,setup,display,retake):
            self.assertEqual(batch_id,'B02')
            display({'phase':'body','message':'body','remaining_seconds':20})
            display({'phase':'complete','message':'BATCH FINISHED'})
            return root/'saved'
        with tempfile.TemporaryDirectory() as td, patch('builtins.input',return_value=''), patch('optical_link.capture_cell.run_batch',side_effect=fake_send) as send, patch('optical_link.capture_cell.display') as shown:
            (Path(td)/'optical_link').mkdir()
            record_batch_cell('B02',root=td,port='fake')
            send.assert_called_once()
            self.assertTrue(any('DO A LIGHT SWEEP NOW' in c.args[0].data for c in shown.return_value.update.call_args_list))

    def test_plan_fills_exactly_missing_cases(self):
        plan=capture_plan();new={(p['message'],p['codec']) for b in plan['batches'] for p in b['packets']}
        existing={('MANUNITED','none'),('ADRIAN','none'),('OMAR','none'),('MANUNITED','repeat3')}
        self.assertEqual(len(new),11);self.assertFalse(new & existing)
        self.assertEqual(new|existing,{(m,c) for m in ['MANUNITED','ADRIAN','OMAR'] for c in ['none','repeat3','repeat5','hamming74','rs4']})
        self.assertAlmostEqual(sum(b['channel_seconds'] for b in plan['batches']),607.6)

    def test_retake_preserves_records_and_reserves_all_ids(self):
        with tempfile.TemporaryDirectory() as td:
            plan=load_capture_plan(td);b=plan['batches'][0]
            first,r1=new_batch_attempt(td,b,{})
            r1['status']='controller_completed';(first/'batch.json').write_text(json.dumps(r1))
            with self.assertRaisesRegex(ValueError,'already completed'):new_batch_attempt(td,b,{})
            second,r2=new_batch_attempt(td,b,{},retake=True)
            self.assertNotEqual(first,second)
            self.assertFalse({p['sequence'] for p in r1['packets']} & {p['sequence'] for p in r2['packets']})
            self.assertTrue((first/'batch.json').exists())

    def test_body_cue_is_flexible_and_protects_header_and_guard(self):
        packet=make_packet('OMAR','rs4');seen=[];cue=BodyCue(packet,200,seen.append)
        for t in [0,17.8,18.4,23,29,33.9]:cue(t)
        cue(35.4,'DONE bits=176')
        self.assertEqual([r['phase'] for r in cue.events],['header','body','ending','packet_done'])
        self.assertTrue(any('when you choose' in r['message'] for r in seen))

    def test_partial_failure_logs_finished_current_and_unsent_packets(self):
        class FakeTX:
            identity='fake controller'
            def __init__(self,*a):self.n=0
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def transmit(self,packet,bit_ms,log_path,on_progress):
                self.n+=1;on_progress(0,'START')
                if self.n==2:raise KeyboardInterrupt()
                on_progress(len(packet.bits)*.2+.2,'DONE')
        with tempfile.TemporaryDirectory() as td, patch('optical_link.capture.Transmitter',FakeTX), patch('optical_link.capture.time.sleep'):
            plan=load_capture_plan(td)
            with self.assertRaises(KeyboardInterrupt):run_batch(td,plan,'B01','fake',{})
            records=batch_attempts(td);self.assertEqual(len(records),1)
            r=records[0][1];self.assertEqual(r['status'],'interrupted')
            self.assertEqual([p['status'] for p in r['packets']],['controller_completed','failed_or_interrupted','not_started'])
            self.assertIn('KeyboardInterrupt',r['error'])
            self.assertTrue(r['packets'][1]['cue_events'])

    def test_all_three_batches_finish_with_eleven_unique_transmission_logs(self):
        class FakeTX:
            identity='simulated controller for software tests only'
            def __init__(self,*a):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def transmit(self,packet,bit_ms,log_path,on_progress):
                log_path.parent.mkdir(parents=True,exist_ok=True)
                log_path.write_text(json.dumps({'sequence':packet.sequence,'codec':packet.codec}))
                for t,line in [(0,'START'),(19,''),(len(packet.bits)*.2+.2,'DONE')]:on_progress(t,line)
        with tempfile.TemporaryDirectory() as td, patch('optical_link.capture.Transmitter',FakeTX), patch('optical_link.capture.time.sleep'):
            plan=load_capture_plan(td)
            for b in plan['batches']:run_batch(td,plan,b['batch_id'],'fake',{})
            records=batch_attempts(td)
            self.assertEqual(len(records),3)
            packets=[p for _,r in records for p in r['packets']]
            self.assertEqual(len(packets),11)
            self.assertEqual(len({p['sequence'] for p in packets}),11)
            for folder,r in records:
                self.assertEqual(r['status'],'controller_completed')
                for p in r['packets']:
                    self.assertTrue((folder/p['tx_log']).is_file())
                    self.assertTrue(any(e['phase']=='body' for e in p['cue_events']))

    def test_video_copy_preserves_original_and_rejects_reuse_or_replacement(self):
        meta=json.dumps({'streams':[{'width':1920,'height':1080}],'format':{'duration':'240'}}).encode()
        with tempfile.TemporaryDirectory() as td, patch('optical_link.capture.subprocess.check_output',return_value=meta):
            plan=load_capture_plan(td);first,r=new_batch_attempt(td,plan['batches'][0],{})
            r['status']='controller_completed'
            for p in r['packets']:p['status']='controller_completed'
            (first/'batch.json').write_text(json.dumps(r))
            source=Path(td)/'original.mov';source.write_bytes(b'original video fixture')
            dest=attach_batch_video(first,source,'Two passes during the body.')
            self.assertEqual(source.read_bytes(),dest.read_bytes())
            self.assertTrue(capture_status(td,plan)[0]['video_saved'])
            second,r2=new_batch_attempt(td,plan['batches'][1],{})
            r2['packets'][0]['status']='controller_completed';(second/'batch.json').write_text(json.dumps(r2))
            with self.assertRaisesRegex(ValueError,'already attached'):attach_batch_video(second,source)
            source.write_bytes(b'different video')
            with self.assertRaisesRegex(ValueError,'different video'):attach_batch_video(first,source)

    def test_dashboard_load_never_transmits_and_finished_batch_needs_retake(self):
        from optical_link.capture_ui import CaptureDashboard
        with tempfile.TemporaryDirectory() as td, patch('optical_link.capture_ui.run_batch') as transmit:
            plan=load_capture_plan(td);dashboard=CaptureDashboard(td,plan,'fake',{})
            self.assertFalse(transmit.called);self.assertTrue(dashboard.start.disabled)
            dashboard.start.click();self.assertFalse(transmit.called)
            first,r=new_batch_attempt(td,plan['batches'][0],{})
            r['status']='controller_completed';(first/'batch.json').write_text(json.dumps(r))
            dashboard.phone.value=True;self.assertTrue(dashboard.start.disabled)
            dashboard.retake.value=True;self.assertFalse(dashboard.start.disabled)
            dashboard._next(None)
            self.assertEqual(dashboard.batch.value,'B02');self.assertFalse(dashboard.phone.value)
            self.assertFalse(transmit.called)


if __name__=='__main__':unittest.main()
