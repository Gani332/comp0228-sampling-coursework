"""Persistent pygame renderer. Swap times are host observations, not photon times."""
from pathlib import Path
import hashlib
import math
import platform
import subprocess
import time
from .screen_capture_packet import save_json, slug, duration


class PygameRenderer:
    def __init__(self, fullscreen=False, monitor=0):
        import pygame
        self.pg = pygame
        pygame.init()
        try:
            self.window = pygame.display.set_mode((1000, 720), pygame.FULLSCREEN if fullscreen else 0, display=monitor)
            w, h = self.window.get_size()
            self.patch = pygame.Rect(w//4, h//4, w//2, h//2)
            self.references = [(w//16, h//3, w//8, h//3), (13*w//16, h//3, w//8, h//3)]
            self.font = pygame.font.Font(None, 28)
            self.settings = dict(backend='pygame', resolution=[w,h], patch=list(self.patch),
                                 references=self.references, fullscreen=fullscreen, monitor=monitor)
            self.last = None
        except BaseException:
            pygame.quit()
            raise

    def events(self):
        for event in self.pg.event.get():
            if event.type == self.pg.QUIT or (event.type == self.pg.KEYDOWN and event.key == self.pg.K_ESCAPE):
                raise KeyboardInterrupt('Window closed / Escape')
            if event.type == self.pg.KEYDOWN and event.key == self.pg.K_SPACE:
                return True
        return False

    def show(self, bit, caption='SPACE: begin countdown | ESC: stop', force=False):
        key = (bit, caption)
        if key == self.last and not force:
            return
        self.window.fill((80,80,80))
        self.pg.draw.rect(self.window, (255*bit,)*3, self.patch)
        for rect, level in zip(self.references, (0,255)):
            self.pg.draw.rect(self.window, (level,)*3, rect)
        self.window.blit(self.font.render(caption, True, (255,255,255)), (20,20))
        self.pg.display.flip()
        self.last = key

    def close(self):
        self.pg.quit()


def wait_until(deadline, renderer, clock=time.perf_counter, sleep=time.sleep):
    while clock() < deadline:
        renderer.events()
        sleep(min(.005, max(0, deadline-clock())))
    renderer.events()


def transmit(prepared, renderer, record, clock=time.perf_counter, sleep=time.sleep):
    """Same core for single and batch; never catch up after a full-slot overrun."""
    period = prepared.bit_ms/1000
    start = clock()
    record.update(status='transmitting', host_start=start)
    try:
        for index, bit in enumerate(prepared.wire_bits):
            deadline = start + index*period
            wait_until(deadline, renderer, clock, sleep)
            request = clock()
            row = dict(index=index, bit=int(bit), intended_deadline=deadline,
                       request=request, lateness=request-deadline, completion=None)
            record['slots'].append(row)
            if request-deadline >= period:
                raise RuntimeError('Full-slot scheduling overrun; aborting.')
            renderer.show(int(bit), 'TRANSMITTING')
            row['completion'] = clock()
            if row['completion']-deadline >= period:
                raise RuntimeError('Full-slot display overrun; aborting.')
        wait_until(start+len(prepared.wire_bits)*period, renderer, clock, sleep)
        record['status'] = 'completed'
    except BaseException as exc:
        record.update(status='interrupted', error=str(exc) or type(exc).__name__)
        raise
    finally:
        record['host_end'] = clock()
        try:
            renderer.show(0, 'STOPPED')
        except Exception:
            pass


def run_session(plan, folder, gap=8, countdown=5, session_label=None, renderer_factory=PygameRenderer,
                fullscreen=False, monitor=0, clock=time.perf_counter, sleep=time.sleep):
    entries = [p.record(i) for i,p in enumerate(plan,1)]
    for e in entries:
        e['filename'] = f"tx_{e['ordinal']:02d}__seq{e['sequence']:03d}__{slug(e['payload_utf8'])}__codec-{e['codec']}__ilv-{'on-d8' if e['interleaving'] else 'off'}.json"
    try:
        revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=Path(__file__).resolve().parents[2], text=True).strip()
    except Exception:
        revision = None
    manifest = dict(schema_version=1, session_id=folder.name, session_label=session_label,
                    source_revision=revision, software=platform.python_version(), status='planned',
                    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                   (Path(__file__), Path(__file__).with_name('screen_capture_packet.py'))},
                    timing_note='Host swap observations, not optical photon times.',
                    interleaving_note='Depth is absent from header; retain manifest.',
                    estimate=duration(plan,gap,countdown), entries=entries)
    def persist():
        for e in entries:
            save_json(folder/e['filename'], dict(e,session_id=folder.name,rendering=manifest.get('rendering')))
        save_json(folder/'manifest.json', manifest)
    persist()
    renderer = None
    try:
        renderer = renderer_factory(fullscreen=fullscreen, monitor=monitor)
        manifest['rendering'] = renderer.settings
        manifest['rendering']['pygame_version'] = getattr(getattr(renderer, 'pg', None), '__version__', None)
        persist()
        renderer.show(1, 'CALIBRATION: select camera ROI; SPACE starts countdown')
        while not renderer.events():
            sleep(.01)
        for remaining in range(math.ceil(countdown),0,-1):
            renderer.show(0, f'Starts in {remaining}')
            wait_until(clock()+min(1,countdown),renderer,clock,sleep)
            countdown -= min(1,countdown)
        for i,p in enumerate(plan):
            renderer.show(0, 'TRANSMITTING')
            try:
                transmit(p,renderer,entries[i],clock,sleep)
            finally:
                persist()
            if i+1 < len(plan):
                renderer.show(0, 'BLACK GAP')
                wait_until(clock()+gap,renderer,clock,sleep)
        manifest['status'] = 'completed'
    except BaseException as exc:
        manifest.update(status='interrupted',error=str(exc) or type(exc).__name__)
    finally:
        if renderer:
            try:
                renderer.show(0,'STOPPED')
            except Exception:
                pass
            try:
                renderer.close()
            except Exception as exc:
                manifest.update(status='interrupted', close_error=str(exc))
        persist()
    return manifest
