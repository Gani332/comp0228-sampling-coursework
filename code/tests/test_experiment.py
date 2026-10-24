import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import numpy as np
from optical_link.device import Transmitter
from optical_link.protocol import make_packet, GUARD_BITS, PREAMBLE, HEADER_BITS
from optical_link.receiver import synthetic_trace
from optical_link.experiment import (make_plan, create_attempt, CaptureCue, run_trial,
                                     score_trace, comparison_rows, attach_video, _save)


def tx_record(packet):
    return {'payload_hex':packet.payload.hex(),'sequence':packet.sequence,'codec':packet.codec,
            'bit_ms':200,'transmitted_bits':''.join(map(str,packet.bits)),
            'scheduled_channel_seconds':len(packet.bits)*.2}


class ExperimentTests(unittest.TestCase):
    def test_rerunning_transmit_cell_does_not_send_twice(self):
        source=(Path(__file__).resolve().parent/'fixtures/repetition_transmit_cell.py').read_text()
        sends=[]
        class Handle:
            def update(self,*args):pass
        namespace={'RUN_TRANSMISSION':True,'ROOT':Path('/unused'),'plan':{},'TRIAL_ID':'T01',
                   'PORT':'fake','SETUP':{},'HTML':lambda x:x,'display':lambda *a,**k:Handle(),
                   'run_trial':lambda *a,**k:sends.append(1) or Path('/unused/attempt'),
                   'attempts':lambda *a:[]}
        exec(source,namespace)
        self.assertFalse(namespace['RUN_TRANSMISSION'])
        exec(source,namespace)
        self.assertEqual(len(sends),1)

    def test_plan_balanced_and_distinct_ids(self):
        plan=make_plan();trials=plan['trials']
        self.assertEqual(len(trials),12)
        self.assertEqual(len({t['sequence'] for t in trials}),12)
        self.assertEqual((trials[0]['codec'],trials[0]['condition']),('repeat3','clean'))
        for codec in ['none','repeat3']:
            for condition in ['clean','noisy']:
                self.assertEqual(sum(t['codec']==codec and t['condition']==condition for t in trials),3)
        self.assertEqual({t['channel_seconds'] for t in trials if t['codec']=='none'},{36.800000000000004})
        self.assertEqual({t['channel_seconds'] for t in trials if t['codec']=='repeat3'},{72.0})

    def test_cue_keeps_header_clean_and_limits_window(self):
        p=make_packet('MANUNITED','repeat3')
        cue=CaptureCue(p,200,'noisy')
        header_end=.2+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS)*.2
        self.assertGreaterEqual(cue.start_seconds-header_end,1.999)
        for t in [0,cue.start_seconds-.001,cue.start_seconds+.001,cue.stop_seconds+.001]:cue(t)
        cue(cue.total_seconds,'DONE bits=360')
        self.assertEqual([e['phase'] for e in cue.events],['wait','sweep','stop','complete'])
        clean=CaptureCue(p,200,'clean')
        clean(0);clean(22);clean(72.2,'DONE')
        self.assertEqual([e['phase'] for e in clean.events],['steady','complete'])

    def test_serial_progress_is_anchored_to_start_ack(self):
        clock=[0.0]
        class SerialStub:
            def __init__(self):self.events=iter([(2,''),(0,'START bits=1 bit_ms=200'),(.5,''),(1.5,'DONE bits=1')])
            def write(self,data):return len(data)
            def flush(self):pass
            def readline(self):
                dt,line=next(self.events);clock[0]+=dt;return (line+'\n').encode()
        tx=Transmitter('unused');tx.serial=SerialStub()
        seen=[]
        with patch('optical_link.device.time.monotonic',side_effect=lambda:clock[0]):
            tx.run('SEND 200 1',seconds=60,completed='DONE',on_progress=lambda elapsed,line:seen.append(elapsed))
        self.assertEqual(seen,[0,.5,2])

    def test_repeat3_repairs_isolated_errors_in_simulated_signal(self):
        for codec in ['none','repeat3']:
            p=make_packet('MANUNITED',codec,sequence=40)
            altered=p.bits.copy()
            first=GUARD_BITS+len(PREAMBLE)+HEADER_BITS
            altered[first+np.array([0,4])]^=1
            noisy=replace(p,bits=altered)
            t,y=synthetic_trace(noisy,noise=0,drop_fraction=0,seed=8)
            metrics,_=score_trace(t,y,tx_record(p))
            self.assertEqual(metrics['body_channel_bit_errors'],2)
            self.assertEqual(metrics['payload_bit_errors'],0 if codec=='repeat3' else 2)
            self.assertEqual(metrics['crc_ok'],codec=='repeat3')

    def test_wrong_recording_is_not_counted_as_channel_failure(self):
        expected=make_packet('MANUNITED','repeat3',sequence=40)
        other=make_packet('MANUNITED','repeat3',sequence=41)
        t,y=synthetic_trace(other,noise=0,drop_fraction=0)
        metrics,_=score_trace(t,y,tx_record(expected))
        self.assertEqual(metrics['status'],'association_error')
        self.assertNotIn('payload_ber',metrics)

    def test_retries_preserve_records_and_use_new_optical_ids(self):
        with tempfile.TemporaryDirectory() as td:
            p=make_plan()
            d1,t1=create_attempt(td,p,'T01',{})
            d2,t2=create_attempt(td,p,'T01',{})
            self.assertNotEqual(d1,d2)
            self.assertNotEqual(t1['sequence'],t2['sequence'])
            self.assertTrue(t2['retake'])
            self.assertTrue((d1/'trial.json').is_file())

    def test_port_failure_is_retained(self):
        with tempfile.TemporaryDirectory() as td:
            with patch('optical_link.experiment.Transmitter') as mock:
                mock.return_value.__enter__.side_effect=OSError('No such port')
                with self.assertRaises(OSError):run_trial(td,make_plan(),'T01','fake',{})
            records=list(Path(td).glob('experiments/repetition_comparison/attempts/*/trial.json'))
            self.assertEqual(len(records),1)
            self.assertEqual(json.loads(records[0].read_text())['status'],'transmission_aborted')

    def test_same_video_cannot_be_assigned_to_two_attempts(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'example.mov';source.write_bytes(b'copy-and-hash test fixture')
            plan=make_plan()
            first,t1=create_attempt(td,plan,'T01',{})
            second,t2=create_attempt(td,plan,'T02',{})
            for folder,trial in [(first,t1),(second,t2)]:
                trial['status']='controller_completed';_save(folder/'trial.json',trial)
            attach_video(first,source)
            with self.assertRaisesRegex(ValueError,'already attached'):
                attach_video(second,source)

    def test_failed_header_is_in_packet_rate_but_not_zero_ber(self):
        p=make_packet('MANUNITED','repeat3',sequence=40)
        damaged=p.bits.copy();damaged[GUARD_BITS+len(PREAMBLE)+10]^=1
        t,y=synthetic_trace(replace(p,bits=damaged),noise=0,drop_fraction=0)
        metric,_=score_trace(t,y,tx_record(p))
        self.assertEqual(metric['status'],'decode_failed')
        self.assertIsNone(metric['payload_bit_errors'])
        with tempfile.TemporaryDirectory() as td:
            folder,trial=create_attempt(td,make_plan(),'T01',{})
            trial.update(status='controller_completed',latest_evaluation='evaluations/test')
            _save(folder/'trial.json',trial)
            _save(folder/'evaluations/test/metrics.json',metric)
            row=next(r for r in comparison_rows(td) if (r['codec'],r['condition'])==('repeat3','clean'))
            self.assertEqual(row['packet_failure_rate'],1)
            self.assertIsNone(row['payload_ber'])
            self.assertEqual(row['correct_payload_goodput_bps'],0)


if __name__=='__main__':unittest.main()
