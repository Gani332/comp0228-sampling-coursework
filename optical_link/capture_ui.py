"""Explicit-click notebook controls; creating a dashboard never opens serial."""
import html
from pathlib import Path
import ipywidgets as widgets
from IPython.display import display

from .capture import (run_batch, batch_attempts, attach_batch_video,
                      capture_status, LABELS)


class CaptureDashboard:
    def __init__(self, root, plan, port, setup):
        self.root, self.plan, self.port, self.setup = Path(root), plan, port, dict(setup)
        self.busy = False
        self.batch = widgets.Dropdown(options=[(f"{b['batch_id']} — {b['message']}", b['batch_id'])
                                               for b in plan['batches']], description='Recording:')
        self.phone = widgets.Checkbox(value=False, description='My iPhone is recording continuously', indent=False)
        self.retake = widgets.Checkbox(value=False, description='Explicit retake: retain the previous attempt', indent=False)
        self.start = widgets.Button(description='Start this recording', button_style='success', disabled=True,
                                    layout=widgets.Layout(width='230px'))
        self.next = widgets.Button(description='Prepare next recording', layout=widgets.Layout(width='230px'))
        self.details = widgets.HTML()
        self.cue = widgets.HTML('<p>Start your phone, tick the checkbox, then click Start.</p>')
        self.output = widgets.Output()
        self.saved_attempt = widgets.Dropdown(options=[], description='Attempt:', layout=widgets.Layout(width='95%'))
        self.video = widgets.Text(description='Video path:', layout=widgets.Layout(width='95%'))
        self.notes = widgets.Textarea(description='Observed:', placeholder='What actually happened during each message? Note missing/extra disturbance, movement, or retakes.',
                                      layout=widgets.Layout(width='95%', height='85px'))
        self.attach = widgets.Button(description='Save original video + notes', button_style='info', layout=widgets.Layout(width='250px'))
        self.table = widgets.HTML()
        self.batch.observe(self._selection_changed, names='value')
        self.phone.observe(lambda change:self._refresh_start(), names='value')
        self.retake.observe(lambda change:self._refresh_start(), names='value')
        self.start.on_click(self._start)
        self.next.on_click(self._next)
        self.saved_attempt.observe(self._attachment_changed, names='value')
        self.attach.on_click(self._attach)
        self._next(None)
        self._refresh()

    def _batch(self):
        return next(b for b in self.plan['batches'] if b['batch_id'] == self.batch.value)

    def _selection_changed(self, change):
        self.phone.value = False
        self.retake.value = False
        self._refresh()

    def _refresh_start(self):
        done = any(r['status']=='controller_completed' for _,r in batch_attempts(self.root,self.batch.value))
        self.start.disabled = self.busy or not self.phone.value or (done and not self.retake.value)

    def _refresh(self):
        b = self._batch()
        order = ' → '.join(LABELS[p['codec']] for p in b['packets'])
        self.details.value = (f'<p><b>{html.escape(b["message"])}</b>: {html.escape(order)}<br>'
                              f'Allow approximately {b["approx_capture_seconds"]//60} min '
                              f'{b["approx_capture_seconds"]%60} s. Save as <b>{html.escape(b["video_name"])}</b>.</p>')
        records = batch_attempts(self.root)
        selected = self.saved_attempt.value
        options = [(f'{r["batch_id"]} | {r["attempt_id"]} | {r["status"]}', str(p)) for p,r in records]
        self.saved_attempt.options = options
        if selected in [v for _,v in options]: self.saved_attempt.value = selected
        elif options: self.saved_attempt.value = options[-1][1]
        self._attachment_changed(None)
        rows = capture_status(self.root,self.plan)
        self.table.value = '<table><tr><th>Recording</th><th>Latest send</th><th>Video saved</th></tr>'+''.join(
            f'<tr><td style="padding:6px">{r["batch"]}: {r["message"]}</td><td style="padding:6px">{r["latest_status"]}</td>'
            f'<td style="padding:6px">{"Yes — decoding pending" if r["video_saved"] else "No"}</td></tr>' for r in rows)+'</table>'
        self._refresh_start()

    def _next(self, button):
        if self.busy: return
        for b in self.plan['batches']:
            if not any(r['status']=='controller_completed' for _,r in batch_attempts(self.root,b['batch_id'])):
                self.batch.value = b['batch_id']
                self.phone.value = False
                self.retake.value = False
                self._refresh()
                return
        self.cue.value = '<p><b>All three batches have completed transmission.</b> Attach their original videos below; decoding and optical-ID verification come later.</p>'
        self.phone.value = False

    def _show_cue(self, state):
        colour = {'body':'#fff3cd','complete':'#dcfce7','header':'#e7f1ff','gap':'#e7f1ff'}.get(state['phase'],'#f1f5f9')
        title = html.escape(state.get('packet', ''))
        remaining = f'<br>{state["remaining_seconds"]} seconds remaining in this message' if 'remaining_seconds' in state else ''
        self.cue.value = f'<div style="padding:20px;background:{colour};color:#111;font-size:22px"><b>{title}</b><br>{html.escape(state["message"])}{remaining}</div>'

    def _start(self, button):
        self._refresh_start()
        if self.start.disabled: return
        self.busy = True
        self.start.disabled = self.next.disabled = self.batch.disabled = True
        self.phone.disabled = self.retake.disabled = self.attach.disabled = True
        try:
            folder = run_batch(self.root,self.plan,self.batch.value,self.port,self.setup,
                               display=self._show_cue,retake=self.retake.value)
            with self.output:
                print('Saved transmission logs:',folder)
                print('After AirDrop, rename this video:',self._batch()['video_name'])
        except (Exception,KeyboardInterrupt) as exc:
            self.cue.value = '<p style="color:#a11"><b>Capture interrupted.</b> Stop the phone and keep this recording. Partial logs are retained. See the error below.</p>'
            with self.output: print(type(exc).__name__+':',exc)
        finally:
            self.busy = False
            self.next.disabled = self.batch.disabled = self.phone.disabled = self.retake.disabled = self.attach.disabled = False
            self.phone.value = False
            self.retake.value = False
            self._refresh()

    def _attachment_changed(self, change):
        if not self.saved_attempt.value: return
        import json
        r=json.loads((Path(self.saved_attempt.value)/'batch.json').read_text())
        self.video.value=str(Path.home()/'Downloads'/r['video_name'])
        self.notes.value=r.get('actual_observations','')

    def _attach(self, button):
        if self.busy: return
        try:
            if not self.saved_attempt.value: raise ValueError('Transmit a batch first.')
            target=attach_batch_video(self.saved_attempt.value,self.video.value,self.notes.value)
            with self.output:
                print('Original video copied and hash-verified:',target)
                import json
                r=json.loads((Path(self.saved_attempt.value)/'batch.json').read_text())
                if r['capture_duration_warning']: print('CHECK: video is shorter than the planned batch. It is retained; inspect completeness before using it.')
                print('Optical packet IDs, framing and decoding have not yet been verified.')
            self._refresh()
        except Exception as exc:
            with self.output: print(type(exc).__name__+':',exc)

    def show(self):
        display(widgets.VBox([self.details,self.batch,self.phone,self.retake,
                              widgets.HBox([self.start,self.next]),self.cue,self.table,
                              widgets.HTML('<hr><b>After AirDrop: attach each original video</b><p>Select its attempt, check the path, enter actual observations, and save.</p>'),
                              self.saved_attempt,self.video,self.notes,self.attach,self.output]))
        return self
