"""Screen timing, exact wire bits, interruption retention and notebook dispatch."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import shutil
import unittest
from optical_link import physical_campaign as c
from optical_link.mac_campaign import ScreenTransmitter
from optical_link.physical_campaign_ui import ScreenRecorder
from optical_link.protocol import make_packet

ROOT=Path(__file__).resolve().parents[2]

class Clock:
    def __init__(self):self.t=0.
    def __call__(self):return self.t
    def sleep(self, seconds):self.t+=max(seconds,1e-7)

class Renderer:
    settings={'backend':'fake'}
    def __init__(self, **kwargs):self.shown=[];self.closed=False;self.fail=False;self.delay=None
    def events(self):
        if self.fail:raise KeyboardInterrupt('Escape')
        return True
    def show(self,bit,caption='',**kwargs):
        self.shown.append((bit,caption))
        if self.delay:self.delay()
    def close(self):self.closed=True

class MacCampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        (self.root/c.PLAN).parent.mkdir(parents=True)
        shutil.copyfile(ROOT/c.PLAN,self.root/c.PLAN)
        self.clock=Clock();self.renderer=Renderer()
        self.tx=ScreenTransmitter(renderer_factory=lambda **kwargs:self.renderer,
                                  clock=self.clock,sleep=self.clock.sleep)
    def tearDown(self):self.tmp.cleanup()
    def test_every_configuration_uses_exact_planned_wire_and_slot_deadlines(self):
        group=next(rows for rows in c.load_sessions(self.root).values() if rows[0]['phase']=='main' and rows[0]['condition']=='OCC_CLUSTER')
        with self.tx:
            for row in group:
                _,packet=c.wire_packet(row)
                log=self.tx.transmit(packet,200,self.root/(row['packet_id']+'.json'))
                self.assertEqual(''.join(str(s['bit']) for s in log['slots']),''.join(map(str,packet.bits)))
                self.assertEqual(log['status'],'controller_completed')
                for i,slot in enumerate(log['slots']):
                    self.assertAlmostEqual(slot['intended_deadline']-log['host_epoch_monotonic'],.2+i*.2)
                self.assertAlmostEqual(log['host_elapsed_seconds'],.2+len(packet.bits)*.2,places=5)
        self.assertTrue(self.renderer.closed)
    def test_cues_fire_during_bits_and_use_preserved_offset(self):
        row=next(rows[0] for rows in c.load_sessions(self.root).values() if rows[0]['condition']=='OCC_SPLIT')
        _,packet=c.wire_packet(row)
        states=[]
        cue=c.Cue(row,states.append)
        with self.tx:self.tx.transmit(packet,200,on_progress=cue)
        self.assertEqual(cue.record()['events_without_active_display'],[])
        transitions=[t for t in cue.transitions if t['state'][0]=='active']
        self.assertEqual(len(transitions),3)
        self.assertTrue(all(t['cue_lateness_seconds']<.01 for t in transitions))
    def test_overrun_fails_and_keeps_log(self):
        path=self.root/'failed.json'
        with self.tx:
            self.renderer.delay=lambda:self.clock.sleep(.25)
            with self.assertRaisesRegex(RuntimeError,'overrun'):
                self.tx.transmit(make_packet('LARA','none'),200,path)
        self.assertEqual(json.loads(path.read_text())['status'],'failed_or_interrupted')
    def test_escape_keeps_partial_log(self):
        path=self.root/'escape.json'
        with self.tx:
            self.renderer.fail=True
            with self.assertRaises(KeyboardInterrupt):self.tx.transmit(make_packet('LARA','none'),200,path)
        self.assertEqual(json.loads(path.read_text())['status'],'failed_or_interrupted')
        self.assertTrue(self.renderer.closed)
    def test_session_persists_screen_metadata_and_all_packets(self):
        sid=c.next_session(self.root)
        folder=c.run_session(self.root,sid,'mac-screen',{'transmitter':'mac_screen'},self.tx.display,
                             transmitter_factory=lambda _:self.tx,sleep=self.tx.pause)
        record=json.loads((folder/'session.json').read_text())
        self.assertEqual(record['status'],'controller_completed')
        for packet in record['packets']:
            log=json.loads((folder/packet['tx_file']).read_text())
            self.assertEqual(log['transport'],'mac_screen')
            self.assertEqual(log['transmitted_bits'],packet['wire_bits'])
            self.assertTrue(log['slots'])
    def test_notebook_rerun_never_spawns_or_accesses_usb(self):
        sid=c.next_session(self.root)
        folder=self.root/c.DATA/'attempts'/'existing'
        c.save(folder/'session.json',dict(session_id=sid,status='controller_completed'))
        with patch('subprocess.Popen') as launch,patch('optical_link.physical_campaign_ui.ports') as ports:
            self.assertEqual(ScreenRecorder(self.root).record_next(session_id=sid),folder)
        launch.assert_not_called();ports.assert_not_called()
    def test_notebook_launches_child_with_no_serial_port(self):
        c.save(self.root/c.DATA/'setup.json',{'transmitter':'mac_screen'})
        with patch('importlib.util.find_spec',return_value=object()),patch('subprocess.Popen') as launch,patch.object(ScreenRecorder,'_show'),patch('optical_link.physical_campaign_ui.ports') as ports:
            launch.return_value.wait.return_value=0
            ScreenRecorder(self.root).record_next(session_id=c.next_session(self.root))
            command=launch.call_args.args[0]
            self.assertIn('optical_link.mac_campaign',command)
        ports.assert_not_called()

if __name__=='__main__':unittest.main()
