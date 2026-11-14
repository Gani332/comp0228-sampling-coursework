"""Explicit recording sections must preserve order, association and restart safety."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import ast
import contextlib
import io
import json
import shutil
import unittest
import nbformat
from optical_link import physical_campaign as c
from optical_link.physical_campaign_ui import Recorder
ROOT=Path(__file__).resolve().parents[2]

class ExpandedNotebookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        (self.root/c.PLAN).parent.mkdir(parents=True)
        shutil.copyfile(ROOT/c.PLAN,self.root/c.PLAN)
    def tearDown(self):self.tmp.cleanup()
    def saved_attempt(self,sid,aid,status='controller_completed'):
        folder=self.root/c.DATA/'attempts'/aid
        c.save(folder/'session.json',dict(session_id=sid,attempt_id=aid,status=status,phase='pilot',video=None))
        return folder
    def test_every_session_is_explicit_once_and_in_manifest_order(self):
        notebook=nbformat.read(ROOT/'Record_Physical_Trials.ipynb',as_version=4)
        nbformat.validate(notebook)
        sessions=c.load_sessions(self.root)
        records=[cell for cell in notebook.cells if cell.metadata.get('campaign_role')=='record']
        attachments=[cell for cell in notebook.cells if cell.metadata.get('campaign_role')=='attach']
        self.assertEqual([cell.metadata['session_id'] for cell in records],list(sessions))
        self.assertEqual([cell.metadata['session_id'] for cell in attachments],list(sessions))
        self.assertEqual(len(records),21)
        self.assertEqual(sum(len(group) for group in sessions.values()),82)
        for cell in records:
            call=ast.parse(cell.source).body[0].value
            keywords={k.arg:ast.literal_eval(k.value) for k in call.keywords}
            self.assertEqual(keywords['session_id'],cell.metadata['session_id'])
            self.assertEqual(keywords['phase'],sessions[keywords['session_id']][0]['phase'])
        for cell in notebook.cells:
            if cell.cell_type=='code':
                compile(cell.source,'notebook','exec')
                # This is the working recording notebook. Executing it legitimately
                # saves outputs; nbformat.validate above checks their structure.
                # Do not require deleting the user's recording evidence to pass.
        self.assertEqual(notebook.metadata['campaign_plan_sha256'],c.digest(self.root/c.PLAN))
    def test_rerunning_record_cell_does_not_prompt_or_access_usb(self):
        sid='PILOT_T1_L4';folder=self.saved_attempt(sid,'attempt1')
        r=Recorder(self.root)
        with patch('optical_link.physical_campaign_ui.ports') as ports,patch('builtins.input') as prompt,patch('optical_link.physical_campaign_ui.run_session') as run:
            self.assertEqual(r.record_next(session_id=sid),folder)
        ports.assert_not_called();prompt.assert_not_called();run.assert_not_called()
    def test_explicit_section_attaches_its_video_not_first_pending(self):
        first=self.saved_attempt('PILOT_T1_L4','attempt1')
        second=self.saved_attempt('PILOT_T1_L12','attempt2')
        video=self.root/'original.MOV';video.write_bytes(b'fixture-not-real-footage')
        r=Recorder(self.root);r.attach_session('PILOT_T1_L12',source=video)
        self.assertIsNone(json.loads((first/'session.json').read_text())['video'])
        self.assertIsNotNone(json.loads((second/'session.json').read_text())['video'])
    def test_multiple_retakes_do_not_guess_video_association(self):
        sid='PILOT_T1_L4';self.saved_attempt(sid,'attempt1');self.saved_attempt(sid,'attempt2')
        with patch.object(Recorder,'_pick_and_attach') as picker:
            self.assertIsNone(Recorder(self.root).attach_session(sid))
        picker.assert_not_called()
    def test_notes_append_and_keep_status(self):
        folder=self.saved_attempt('PILOT_T1_L4','attempt1','failed_or_interrupted')
        r=Recorder(self.root)
        r.note_session('PILOT_T1_L4','Phone stopped early.')
        r.note_session('PILOT_T1_L4','Partial video retained.')
        d=json.loads((folder/'session.json').read_text())
        self.assertEqual(d['status'],'failed_or_interrupted');self.assertEqual(len(d['operator_note_entries']),2)
    def test_handover_reports_missing_videos_not_optical_success(self):
        self.saved_attempt('PILOT_T1_L4','attempt1')
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):Recorder(self.root).handover()
        text=stream.getvalue()
        self.assertIn('VIDEO NOT ATTACHED',text)
        self.assertIn('NOT decode success',text)
        self.assertIn('pilot: 1 of 4',text)

if __name__=='__main__':unittest.main()
