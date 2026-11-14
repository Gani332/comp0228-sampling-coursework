"""Small notebook interface for the original LCD/phone experiment."""
from pathlib import Path
import html
import json
import time
from IPython.display import HTML, display
from .device import ports
from .physical_campaign import (DATA, PLAN, LABELS, Cue, load_sessions, next_session,
                                attempts, run_session, attach_video, save, check_freeze)

class Recorder:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.sessions=load_sessions(self.root)
        self.last_folder=None
        self._box=None
    def overview(self, phase='pilot'):
        prior=attempts(self.root)
        lines=['<table><tr><th>Video</th><th>Condition</th><th>Packets</th><th>Approx. minutes</th><th>Status</th></tr>']
        for sid,rows in self.sessions.items():
            if rows[0]['phase']!=phase:continue
            records=[r for _,r in prior if r['session_id']==sid]
            status='not recorded' if not records else records[-1]['status']
            seconds=sum(float(r['scheduled_channel_seconds'])+.2 for r in rows)+8*(len(rows)-1)+8
            cells=[sid,LABELS[rows[0]['condition']],str(len(rows)),f'{seconds/60:.1f}',status]
            lines.append('<tr>'+''.join('<td style="padding:8px">'+html.escape(c)+'</td>' for c in cells)+'</tr>')
        display(HTML(''.join(lines)+'</table>'))
    def setup(self, **settings):
        path=self.root/DATA/'setup.json'
        if settings:
            old=json.loads(path.read_text()) if path.exists() else {}
            old.update(settings);save(path,old)
        elif not path.exists():
            save(path,dict(phone_model=input('Phone model: ').strip(),
                           camera_settings=input('Video mode/FPS and exposure/focus lock (or unknown): ').strip(),
                           distance_cm=input('Approximate screen-to-phone distance in cm: ').strip(),
                           operator=input('Your name/initials: ').strip(),
                           lighting='Record actual lighting/lamp geometry before noise trials.'))
        print('Saved setup:',json.loads(path.read_text()))
        print('Keep the phone and transmitting display fixed. Include the complete flashing patch and surrounding static reference areas.')
    def _show(self,state):
        colour={'active':'#b91c1c','ready':'#92400e','done':'#166534','error':'#991b1b'}.get(state['state'],'#164e63')
        title=''
        if 'codec' in state:title=f"{state['codec']} · interleaving {'OFF' if int(state['depth'])==1 else 'ON'} · {state.get('seconds_remaining','')} s remaining"
        markup=f'<div style="background:{colour};color:white;padding:28px;font-size:30px;border-radius:10px"><small>{html.escape(title)}</small><br><b>{html.escape(state["text"])}</b></div>'
        if self._box is None:self._box=display(HTML(markup),display_id=True)
        else:self._box.update(HTML(markup))
    def record_next(self, phase='pilot', session_id=None, retake=False, port=None):
        sid=session_id or next_session(self.root,phase)
        if sid is None:
            print('This phase is complete. Keep the original videos; the next step is analysis, not more repetitions.')
            return None
        rows=self.sessions[sid]
        prior=[(p,r) for p,r in attempts(self.root) if r['session_id']==sid]
        if prior and not retake:
            folder,record=prior[-1]
            self.last_folder=folder
            print('This recording already has an attempt:', record['status'])
            print('Nothing transmitted. Attach its video, or deliberately request a retained retake.')
            print(folder)
            return folder
        check_freeze(self.root,rows[0]['phase'])
        setup_path=self.root/DATA/'setup.json'
        if not setup_path.exists():raise ValueError('Run recorder.setup() once first.')
        if port is None:
            candidates=[p['port'] for p in ports() if p['vid']==0x303A and p['pid']==0x1001]
            if len(candidates)!=1:raise ValueError('Connect the ESP32 USB cable. No unique board detected; no transmission started. You can specify port explicitly if needed.')
            port=candidates[0]
        minutes=(sum(float(r['scheduled_channel_seconds'])+.2 for r in rows)+8*(len(rows)-1)+8)/60
        print(f'Next video: {sid} | approximately {minutes:.1f} minutes | {LABELS[rows[0]["condition"]]}')
        print('ONE continuous phone video. Do not stop between packets. Keep its original filename.')
        answer=input('Start phone recording, then press Enter. Any text cancels: ')
        if answer.strip():print('Cancelled; nothing transmitted.');return None
        self._box=None
        try:
            folder=run_session(self.root,sid,port,json.loads(setup_path.read_text()),self._show,retake=retake)
            self.last_folder=folder
            print('Video finished. Session/logs:',folder)
            print('After transferring the original phone video, use recorder.attach("/path/to/video.MOV").')
            return folder
        finally:
            matches=[p for p,r in attempts(self.root) if r['session_id']==sid]
            if matches:self.last_folder=matches[-1]
    def attach(self, source, attempt_folder=None):
        folder=Path(attempt_folder) if attempt_folder else self.last_folder
        if folder is None:raise ValueError('Specify the matching attempt_folder after restarting the notebook.')
        result=attach_video(self.root,folder,source)
        print('Original video copied and hash checked:',result)
        print('Association and optical results still require analysis.')
        return result
    def _pick_and_attach(self, folder, record, source=None):
        print('Select the original video matching:',record['session_id'],'|',record['status'])
        print('Attempt:',folder.name)
        if record.get('video'):
            print('A video is already attached. Nothing overwritten.');return None
        if source is None:
            import sys,subprocess
            if sys.platform=='darwin':
                prompt=json.dumps('Original phone video for '+record['session_id']+' / '+folder.name)
                selected=subprocess.run(['osascript','-e','POSIX path of (choose file with prompt '+prompt+')'],
                                        text=True,capture_output=True)
                if selected.returncode:
                    print('No file attached. Picker cancelled or unavailable; you can supply a path instead.')
                    return None
                source=selected.stdout.strip()
            else:
                source=input('Paste original video path, or Enter to skip: ').strip().strip(chr(34)).strip(chr(39))
        if not source:return None
        return self.attach(source,attempt_folder=folder)

    def attach_next(self, source=None):
        pending=[(p,r) for p,r in attempts(self.root) if not r.get('video')]
        if not pending:
            print('All recorded attempts have a video attached.');return None
        return self._pick_and_attach(*pending[0],source=source)

    def attach_session(self, session_id, source=None, attempt_id=None):
        matches=[(p,r) for p,r in attempts(self.root) if r['session_id']==session_id
                 and (attempt_id is None or r['attempt_id']==attempt_id)]
        if not matches:
            print('No attempt exists for this section yet. Nothing attached.');return None
        if len(matches)>1 and attempt_id is None:
            print('There are retained retakes. Choose the matching attempt_id explicitly:')
            for p,r in matches:print(r['attempt_id'],r['status'],'attached' if r.get('video') else 'awaiting video')
            return None
        return self._pick_and_attach(*matches[0],source=source)

    def note_session(self, session_id, text, attempt_id=None):
        matches=[(p,r) for p,r in attempts(self.root) if r['session_id']==session_id
                 and (attempt_id is None or r['attempt_id']==attempt_id)]
        if len(matches)!=1:
            raise ValueError('Specify the matching attempt_id when there is no unique attempt.')
        if not text.strip():return
        folder,record=matches[0]
        record.setdefault('operator_note_entries',[]).append(dict(time_unix=time.time(),text=text.strip()))
        save(folder/'session.json',record)
        print('Observation saved; original evidence preserved.')

    def handover(self):
        records=attempts(self.root)
        print('Screen–phone recording handover (controller completion is NOT decode success)')
        print('Attempt folders:',len(records),'| Videos attached:',sum(bool(r.get('video')) for _,r in records))
        for phase in ('pilot','calibration','main','holdout'):
            planned=[sid for sid,rows in self.sessions.items() if rows[0]['phase']==phase]
            completed={r['session_id'] for _,r in records if r.get('phase')==phase and r['status']=='controller_completed'}
            print(phase+':',len(completed),'of',len(planned),'planned videos controller-completed')
        for folder,r in records:
            video=r.get('video')
            print(r['session_id'],'|',r['status'],'|',str(folder/video['path']) if video else 'VIDEO NOT ATTACHED')
        print('Paste this summary into chat. For analysis, also provide the original videos and these saved logs:')
        print(self.root/DATA)
        print('Printed output alone cannot establish timing, noise or decoded-message accuracy.')

    def pending_videos(self):
        for folder,r in attempts(self.root):
            if not r.get('video'):print(r['session_id'], '|', r['status'], '|', folder)
    def rehearse(self, condition='OCC_SPLIT'):
        if condition not in ('OCC_SPLIT','OCC_CLUSTER','GLARE_BODY'):
            raise ValueError('Choose OCC_SPLIT, OCC_CLUSTER or GLARE_BODY.')
        row=next(dict(rows[0]) for rows in self.sessions.values() if rows[0]['condition']==condition)
        row['events']=[dict(e) for e in row['events']]
        # Short rehearsal, unrelated to transmitter timing. No serial access, no experimental data.
        shift=row['events'][0]['start_after_START_ack_s']-3
        for e in row['events']:e['start_after_START_ack_s']-=shift
        duration=row['events'][-1]['start_after_START_ack_s']+row['events'][-1]['duration_target_s']+2
        row['scheduled_channel_seconds']=duration
        print('REHEARSAL ONLY — no hardware transmission or experimental results. Practise the card/lamp action.')
        self._box=None;cue=Cue(row,self._show);start=time.monotonic()
        while time.monotonic()-start<duration:
            cue(time.monotonic()-start);time.sleep(.03)
        self._show(dict(state='done',text='REHEARSAL FINISHED — these are target cues, not measured interference times'))


class ScreenRecorder(Recorder):
    """Notebook interface for the Mac display; graphics run in a child process."""
    def setup(self, **settings):
        super().setup(**settings)
        path=self.root/DATA/'setup.json'
        record=json.loads(path.read_text())
        record['transmitter']='mac_screen'
        for key,prompt in [('screen_model','Mac/display model: '),
                           ('screen_settings','Display brightness, refresh rate, True Tone/Night Shift settings: ')]:
            if not record.get(key):record[key]=input(prompt).strip() or 'unknown'
        save(path,record)
        print('Mac screen setup saved. Keep brightness fixed; disable automatic brightness, True Tone and Night Shift.')

    def record_next(self, phase='pilot', session_id=None, retake=False, port=None):
        import importlib.util, os, subprocess, sys
        sid=session_id or next_session(self.root,phase)
        if sid is None:
            print('This phase is complete. Attach the original videos for review.');return None
        rows=self.sessions[sid]
        prior=[(p,r) for p,r in attempts(self.root) if r['session_id']==sid]
        if prior and not retake:
            self.last_folder=prior[-1][0]
            print('Attempt already exists; nothing transmitted:',self.last_folder)
            return self.last_folder
        check_freeze(self.root,rows[0]['phase'])
        setup_path=self.root/DATA/'setup.json'
        if not setup_path.exists() or json.loads(setup_path.read_text()).get('transmitter')!='mac_screen':
            raise ValueError('Run recorder.setup() for this Mac first.')
        if importlib.util.find_spec('pygame') is None:
            raise RuntimeError('Install the notebook dependencies with its installation cell, then retry. pygame is missing.')
        env=os.environ.copy()
        env['PYTHONPATH']=str(self.root/'code')+os.pathsep+env.get('PYTHONPATH','')
        command=[sys.executable,'-m','optical_link.mac_campaign','--root',str(self.root),'--session',sid]
        if retake:command.append('--retake')
        print('Screen window will open. Frame the central patch and BOTH reference strips in the phone.')
        print('Start ONE phone video; click the screen window and press SPACE. ESC stops and retains the attempt.')
        print('Follow the window cues. Stop filming when the window closes and STOP appears here.')
        process=subprocess.Popen(command,cwd=self.root,env=env)
        try:
            result=process.wait()
            if result:raise RuntimeError('Screen recording interrupted. Keep the partial video and logs; use an explicit retake.')
            self._box=None
            self._show(dict(state='done',text='STOP PHONE RECORDING — this video is finished'))
        except KeyboardInterrupt:
            process.terminate()
            process.wait(timeout=10)
            raise
        finally:
            matches=[p for p,r in attempts(self.root) if r['session_id']==sid]
            if matches:self.last_folder=matches[-1]
        print('Saved attempt:',self.last_folder)
        return self.last_folder
