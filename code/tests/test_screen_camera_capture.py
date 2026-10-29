"""Software-only acceptance; never opens a display or camera."""
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np
from optical_link.protocol import CODECS, GUARD_BITS, PREAMBLE, HEADER_BITS
from optical_link.coding_experiments import deinterleave
from optical_link.screen_capture_packet import prepare, batch_plan, duration, new_session, positive, save_json
from optical_link.screen_transmitter import transmit, run_session
from optical_link.capture_start_detector import observe, HeaderObserver, FirstPacketTimer
from optical_link.receiver import synthetic_trace
from optical_link.camera_recorder import record_stream


class Clock:
    def __init__(self): self.now=0
    def __call__(self): return self.now
    def sleep(self,seconds): self.now+=seconds


class Renderer:
    settings = {'backend':'fake'}
    def __init__(self,**kwargs): self.frames=[]; self.closed=False
    def events(self): return True
    def show(self,bit,caption): self.frames.append(bit)
    def close(self): self.closed=True


class CaptureTests(unittest.TestCase):
    def test_json_atomic_replace_beyond_windows_path_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Keep the directory below MAX_PATH; the packet sidecar exceeds it.
            folder = Path(tmp)
            while len(str(folder)) < 210:
                folder /= 'nested_capture_folder'
            folder.mkdir(parents=True)
            target = folder / ('tx_01__seq001__msg-' + 'A'*24 + '__codec-hamming74__ilv-on-d8.json')
            self.assertGreater(len(str(target)), 260)
            readable = target
            if os.name == 'nt':
                readable = Path('\\\\?\\' + str(target.resolve()))
            try:
                for data in ({'status': 'planned'}, {'status': 'completed'}):
                    with self.subTest(data=data):
                        save_json(target, data)
                        self.assertEqual(json.loads(readable.read_text(encoding='utf-8')), data)
                self.assertFalse(any(p.name.endswith('.tmp') for p in folder.iterdir()))
            finally:
                # tempfile cleanup also needs a short/extended path on Windows.
                readable.unlink(missing_ok=True)

    def test_plan_and_permutation(self):
        plan=batch_plan('HELLO')
        self.assertEqual([(p.packet.codec,p.depth) for p in plan],[(c,d) for c in CODECS for d in (1,8)])
        self.assertEqual(len({p.packet.sequence for p in plan}),10)
        self.assertAlmostEqual(duration(plan)['channel_seconds'],sum(len(p.wire_bits)*.2 for p in plan))
        self.assertGreater(duration(batch_plan('A'*64))['recommended_timeout_after_first_seconds'],1800)
        for message in ['A','abc','hello!']:
            for codec in CODECS:
                p=prepare(message,codec,3,True)
                start=GUARD_BITS+len(PREAMBLE)+HEADER_BITS
                np.testing.assert_array_equal(p.wire_bits[:start],p.packet.bits[:start])
                np.testing.assert_array_equal(p.wire_bits[-GUARD_BITS:],p.packet.bits[-GUARD_BITS:])
                np.testing.assert_array_equal(deinterleave(p.wire_bits[start:-GUARD_BITS],8),p.packet.body_bits)
                np.testing.assert_array_equal(p.packet.bits[start:-GUARD_BITS],p.packet.body_bits)
        with self.assertRaises(ValueError): batch_plan('A',sequence=247)

    def test_absolute_slots_and_overrun(self):
        p=prepare('HI','none')
        c=Clock(); r=Renderer(); record=p.record(1)
        transmit(p,r,record,c,c.sleep)
        self.assertAlmostEqual(c.now,len(p.wire_bits)*.2)
        self.assertEqual(len(record['slots']),len(p.wire_bits))
        self.assertEqual(record['status'],'completed')
        self.assertEqual(r.frames[-1],0)
        c=Clock()
        def late(seconds): c.now+=seconds+.21
        record=p.record(1)
        with self.assertRaises(RuntimeError): transmit(p,r,record,c,late)
        self.assertEqual(record['status'],'interrupted')

    def test_one_window_abort_and_preserved_plan(self):
        class Broken(Renderer):
            def show(self,bit,caption):
                if caption=='TRANSMITTING' and len(self.frames)>8:
                    raise RuntimeError('display failure')
                super().show(bit,caption)
        c=Clock(); renderers=[]
        def factory(**kwargs):
            r=Broken(); renderers.append(r); return r
        with tempfile.TemporaryDirectory() as tmp:
            folder=new_session(tmp,'transmitter','CON/你好')
            result=run_session(batch_plan('HI'),folder,renderer_factory=factory,clock=c,sleep=c.sleep)
            self.assertEqual(len(renderers),1)
            self.assertTrue(renderers[0].closed)
            self.assertEqual(result['status'],'interrupted')
            self.assertEqual(result['entries'][0]['status'],'interrupted')
            self.assertTrue(all(e['status']=='not_sent' for e in result['entries'][1:]))
            self.assertEqual(len(list(folder.glob('tx_*.json'))),10)
            for e in result['entries']:
                self.assertIn('__codec-',e['filename'])
                self.assertIn('__ilv-',e['filename'])

    def test_detector_and_timer(self):
        p=prepare('HI','hamming74').packet
        t,y=synthetic_trace(p,drop_fraction=0,noise=1)
        end=2+(GUARD_BITS+len(PREAMBLE)+HEADER_BITS+2)*.2
        selected=t<end
        result=observe(t[selected],y[selected],200)
        self.assertIsNotNone(result)
        self.assertEqual(result['codec'],'hamming74')
        for values in [np.ones(600)*80,np.random.default_rng(2).normal(80,4,600),np.r_[np.zeros(300),[255],np.zeros(299)]]:
            self.assertIsNone(observe(np.arange(600)/30,values,200))
        timer=FirstPacketTimer(20)
        self.assertFalse(timer.expired(10000))
        timer.arm(10000,'optical_header',result)
        timer.arm(10010,'manual_mark')
        self.assertEqual(timer.deadline,10020)
        self.assertFalse(timer.expired(10019))
        self.assertTrue(timer.expired(10020))
        manual=FirstPacketTimer(10); manual.arm(2,'manual_mark')
        self.assertEqual(manual.source,'manual_mark')

    def test_bounded_observer(self):
        observer=HeaderObserver(max_samples=50)
        try:
            for i in range(400): observer.feed(i/30,80)
            self.assertLessEqual(len(observer.samples),50)
        finally: observer.close()

    def test_recording_order_and_failure(self):
        class Camera:
            def __init__(self): self.n=0
            def read(self):
                time.sleep(.002)
                self.n+=1
                return (True,np.full((10,10,3),self.n,np.uint8)) if self.n<=8 else (False,None)
        class Writer:
            def __init__(self): self.values=[]
            def write(self,frame): self.values.append(int(frame[0,0,0]))
        class Observer:
            dropped_jobs=0
            def feed(self,t,y): return None
        writer=Writer(); stream=io.StringIO()
        stats=record_stream(Camera(),writer,stream,Observer(),FirstPacketTimer(10),(0,0,5,5),lambda *args:None)
        self.assertEqual(writer.values,list(range(1,9)))
        self.assertEqual(stats['written_frames'],8)
        self.assertEqual(stats['unwritten_reads'],0)
        self.assertEqual(stats['failed_reads'],1)
        rows=list(csv.reader(io.StringIO(stream.getvalue())))[1:]
        self.assertEqual(len(rows),8)
        self.assertTrue(all(float(b[2])>float(a[2]) for a,b in zip(rows,rows[1:])))

    def test_manual_stop_timeout_and_writer_error(self):
        class Camera:
            def __init__(self): self.n=0
            def read(self):
                time.sleep(.002)
                self.n+=1
                return True,np.zeros((10,10,3),np.uint8)
        class Writer:
            def write(self,frame): return None
        class Observer:
            dropped_jobs=0
            def feed(self,t,y): return None
        for arm,expected in [(False,'manual_stop'),(True,'timeout_after_first')]:
            timer=FirstPacketTimer(.001)
            def control(frame,elapsed,timer):
                if arm:
                    timer.arm(0,'manual_mark')
                else:
                    return 'stop'
            stats=record_stream(Camera(),Writer(),io.StringIO(),Observer(),timer,(0,0,5,5),control)
            self.assertEqual(stats['stop_reason'],expected)
            self.assertEqual(stats['unwritten_reads'],0)
            self.assertTrue(stats['capture_thread_stopped'])
            self.assertEqual(timer.source,'manual_mark' if arm else None)
        class BadWriter:
            def write(self,frame): raise OSError('disk failure')
        stats=record_stream(Camera(),BadWriter(),io.StringIO(),Observer(),FirstPacketTimer(10),
                            (0,0,5,5),lambda *args:None)
        self.assertEqual(stats['stop_reason'],'recording_error')
        self.assertGreater(stats['unwritten_reads'],0)
        self.assertEqual(stats['write_errors'],1)

    def test_backlog_stops_and_is_reported(self):
        class Camera:
            def read(self): return True,np.zeros((10,10,3),np.uint8)
        class Writer:
            def write(self,frame): time.sleep(.005)
        class Observer:
            dropped_jobs=0
            def feed(self,t,y): return None
        stats=record_stream(Camera(),Writer(),io.StringIO(),Observer(),FirstPacketTimer(10),
                            (0,0,5,5),lambda *args:None,queue_size=2)
        self.assertEqual(stats['stop_reason'],'disk_backlog')
        self.assertEqual(stats['backlog_stops'],1)
        self.assertGreater(stats['unwritten_reads'],0)

    def test_validation(self):
        for value in [float('nan'),float('inf'),0,-1]:
            with self.assertRaises(ValueError): positive(value)
        for value in [199,1001,200.5]:
            with self.assertRaises(ValueError): prepare('HI','none',bit_ms=value)


if __name__=='__main__': unittest.main()
