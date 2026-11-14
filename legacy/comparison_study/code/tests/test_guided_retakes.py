import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from optical_link.protocol import make_packet, GUARD_BITS, PREAMBLE, HEADER_BITS
from optical_link.capture import capture_plan, run_batch, batch_attempts
from optical_link.guided_retakes import (guided_retakes_plan, SingleSweepCue,
                                         record_guided_batch, cue_html)


class GuidedRetakeTests(unittest.TestCase):
    def test_exact_original_batches_and_sweep_within_message_data(self):
        new=guided_retakes_plan()['batches'];old=capture_plan()['batches']
        self.assertEqual(sum(len(b['packets']) for b in new),11)
        for a,b in zip(new,old):
            self.assertEqual(a['repeats_original_batch'],b['batch_id'])
            self.assertEqual([(p['message'],p['codec']) for p in a['packets']],[(p['message'],p['codec']) for p in b['packets']])
            for p in a['packets']:
                packet=make_packet(p['message'],p['codec']);cue=SingleSweepCue(packet,200,None)
                raw=len(packet.payload)*8
                encoded=raw*int(p['codec'][-1]) if p['codec'].startswith('repeat') else raw*7/4 if p['codec']=='hamming74' else raw
                self.assertGreater(cue.schedule['start_seconds'],cue.header_end)
                self.assertLess(cue.schedule['end_seconds'],cue.header_end+encoded*.2)

    def test_countdown_one_sweep_then_stop_and_no_second_window(self):
        states=[];cue=SingleSweepCue(make_packet('OMAR','rs4'),200,states.append)
        for t in [0,16,17,18,19,20,21,21.4,21.8,22,26,30]:cue(t)
        cue(35.4,'DONE bits=176')
        self.assertEqual([s['countdown_seconds'] for s in states if s['phase']=='countdown'],[5,4,3,2,1])
        self.assertEqual(sum(e['phase']=='sweep' for e in cue.events),1)
        self.assertTrue(all(e['seconds_after_start_ack']>=21 for e in cue.events if e['phase']=='sweep'))
        self.assertEqual([e['phase'] for e in cue.events],['steady','countdown','sweep','hold','packet_done'])
        self.assertIn('STOP',next(s['message'] for s in states if s['phase']=='hold'))
        self.assertIn('SWEEP NOW',cue_html(next(s for s in states if s['phase']=='sweep')).data)

    def test_skipped_cue_is_logged_without_requesting_late_sweep(self):
        seen=[];cue=SingleSweepCue(make_packet('OMAR','rs4'),200,seen.append)
        cue(20);cue(22.3);cue(23)
        self.assertEqual(sum(e['phase']=='sweep_cue_missed' for e in cue.events),1)
        self.assertFalse(cue.sweep_seen)
        self.assertIn('do not add a late sweep',seen[-1]['message'])

    def test_cancel_never_opens_controller(self):
        with tempfile.TemporaryDirectory() as td, patch('builtins.input',return_value='cancel'), patch('optical_link.guided_retakes.run_batch') as run, patch('optical_link.guided_retakes.ports') as ports:
            (Path(td)/'optical_link').mkdir()
            self.assertIsNone(record_guided_batch('G01',root=td))
            run.assert_not_called();ports.assert_not_called()
            self.assertEqual(batch_attempts(td),[])

    def test_new_attempt_requires_enter_and_later_retake_requires_explicit_word(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'optical_link').mkdir()
            with patch('builtins.input',return_value=''), patch('optical_link.guided_retakes.run_batch',return_value=root/'saved') as send, patch('optical_link.guided_retakes.display'):
                record_guided_batch('G01',root=root,port='fake')
                self.assertIs(send.call_args.kwargs['cue_factory'],SingleSweepCue)
                self.assertFalse(send.call_args.kwargs['retake'])
            from optical_link.capture import new_batch_attempt
            folder,r=new_batch_attempt(root,guided_retakes_plan()['batches'][0],{})
            r['status']='controller_completed';(folder/'batch.json').write_text(json.dumps(r))
            for answer,allowed in [('',False),('RETAKE',True),('cancel',False)]:
                with patch('builtins.input',return_value=answer), patch('optical_link.guided_retakes.run_batch') as send, patch('optical_link.guided_retakes.display'):
                    record_guided_batch('G01',root=root,port='fake')
                    self.assertEqual(send.called,allowed)
                    if allowed:self.assertTrue(send.call_args.kwargs['retake'])

    def test_fake_batches_log_cues_unique_ids_and_preserve_first_attempt(self):
        class FakeTX:
            identity='SIMULATED TEST CONTROLLER'
            def __init__(self,*args):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def transmit(self,packet,bit_ms,log_path,on_progress):
                log_path.parent.mkdir(parents=True,exist_ok=True)
                log_path.write_text(json.dumps({'sequence':packet.sequence}))
                for t in [0,16,17,18,19,20,21,22]:on_progress(t)
                on_progress(len(packet.bits)*.2+.2,'DONE')
        with tempfile.TemporaryDirectory() as td, patch('optical_link.capture.Transmitter',FakeTX),patch('optical_link.capture.time.sleep'):
            plan=guided_retakes_plan()
            first=run_batch(td,plan,'G01','fake',{},cue_factory=SingleSweepCue)
            original=(first/'batch.json').read_bytes()
            run_batch(td,plan,'G01','fake',{},retake=True,cue_factory=SingleSweepCue)
            for batch in ['G02','G03']:run_batch(td,plan,batch,'fake',{},cue_factory=SingleSweepCue)
            self.assertEqual((first/'batch.json').read_bytes(),original)
            rows=batch_attempts(td);packets=[p for _,r in rows for p in r['packets']]
            self.assertEqual(len(packets),14)
            self.assertEqual(len({p['sequence'] for p in packets}),14)
            for p in packets:
                self.assertEqual(p['planned_sweep_schedule']['start_seconds'],21)
                self.assertEqual(sum(e['phase']=='sweep' for e in p['cue_events']),1)


if __name__=='__main__':unittest.main()
