"""Physical webcam acquisition with authoritative host timestamp sidecars."""
import csv
import hashlib
import platform
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Thread, Event
import shutil
import time
import cv2
from .capture_start_detector import HeaderObserver, FirstPacketTimer
from .screen_capture_packet import save_json, new_session


def sha256(path):
    digest = hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def validate_video(path, expected, cv=cv2):
    capture = cv.VideoCapture(str(path))
    count = 0
    first = last = False
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            first = first or frame is not None
            last = frame is not None
            count += 1
    finally:
        capture.release()
    return dict(method='Sequential decode of every saved frame (not nominal frame-count property)',
                decoded_frames=count, expected_frames=expected, count_matches=count==expected,
                first_readable=first,last_readable=last,nonzero=path.exists() and path.stat().st_size>0)


def record_stream(camera, writer, timestamps, observer, timer, roi, control, clock=time.perf_counter,
                  queue_size=120):
    """Capture on a dedicated thread; bounded disk queue stops on sustained backlog.

    control(frame, elapsed, timer) returns stop/manual/None. All writer calls happen
    here; every successfully written frame gets exactly one timestamp row.
    """
    queue = Queue(queue_size)
    stop = Event()
    start = clock()
    stats = dict(host_capture_start_monotonic=start,successful_reads=0,written_frames=0,failed_reads=0,backlog_stops=0,
                 write_errors=0,discontinuities=0,observations=[],stop_reason=None)
    def acquire():
        index = 0
        try:
            while not stop.is_set():
                before = clock()-start
                ok, frame = camera.read()
                after = clock()-start
                if not ok:
                    stats['failed_reads'] += 1
                    stats['stop_reason'] = 'camera_read_failure'
                    break
                stats['successful_reads'] += 1
                try:
                    queue.put_nowait((index,before,after,frame.copy()))
                except Full:
                    stats['backlog_stops'] += 1
                    stats['stop_reason'] = 'disk_backlog'
                    break
                index += 1
        except Exception as exc:
            stats.update(stop_reason='camera_exception',error=str(exc))
        finally:
            stop.set()
    thread = Thread(target=acquire,daemon=True)
    thread.start()
    rows = csv.writer(timestamps)
    rows.writerow(['frame_index','read_before_seconds','read_return_seconds'])
    previous = -1
    dimensions = None
    user_stopped = False
    try:
        while thread.is_alive() or not queue.empty():
            try:
                index,before,after,frame = queue.get(timeout=.05)
            except Empty:
                # Stop remains responsive even when a camera read blocks.
                action = control(None,clock()-start,timer)
                if action == 'manual':
                    timer.arm(clock()-start,'manual_mark')
                if action == 'stop':
                    stats['stop_reason'] = 'manual_stop'
                    stop.set()
                    user_stopped = True
                    break
                if timer.expired(clock()-start):
                    stats['stop_reason'] = 'timeout_after_first'
                    stop.set()
                    break
                continue
            if after <= previous:
                raise RuntimeError('Nonmonotonic camera timestamps.')
            if previous >= 0 and after-previous > .2:
                stats['discontinuities'] += 1
            previous = after
            if frame.dtype.name != 'uint8' or frame.ndim != 3 or frame.shape[2] != 3:
                raise RuntimeError('Camera must supply uint8 BGR frames.')
            if dimensions is None:
                dimensions = frame.shape
            if frame.shape != dimensions:
                raise RuntimeError('Camera dimensions changed during recording.')
            result = writer.write(frame)
            if result is False:
                raise RuntimeError('Video writer rejected frame.')
            rows.writerow([index,before,after])
            stats['written_frames'] += 1
            if stats['written_frames'] % 30 == 0:
                timestamps.flush()
            x,y,w,h = roi
            observation = observer.feed(after,float(frame[y:y+h,x:x+w].mean()))
            now = clock()-start
            if observation:
                observation.update(validation_completed_seconds=now,
                                   analysis_latency_seconds=now-after)
                stats['observations'].append(observation)
                timer.arm(now,'optical_header',observation)
            if not user_stopped:
                action = control(frame,now,timer)
                if action == 'manual':
                    timer.arm(now,'manual_mark')
                if action == 'stop' or timer.expired(now):
                    stats['stop_reason'] = 'manual_stop' if action=='stop' else 'timeout_after_first'
                    user_stopped = True
                    stop.set()
            # Drain already acquired frames after stop, without changing timer.
    except (Exception, KeyboardInterrupt) as exc:
        stats.update(stop_reason='interrupted' if isinstance(exc,KeyboardInterrupt) else 'recording_error',error=str(exc))
        stats['write_errors'] += int(not isinstance(exc,KeyboardInterrupt))
    finally:
        stop.set()
        thread.join(timeout=2)
        stats['capture_thread_stopped'] = not thread.is_alive()
        stats['unwritten_reads'] = stats['successful_reads']-stats['written_frames']
        stats['elapsed_seconds'] = clock()-start
        stats['detector_dropped_jobs'] = observer.dropped_jobs
        timestamps.flush()
    return stats


def run_camera(args, cv=cv2):
    folder = new_session(args.output,'receiver')
    stem = 'rx_'+folder.name.split('__')[0]+'__continuous__settings-in-transmitter-manifest'
    video = folder/(stem+'.avi')
    frames_path = folder/(stem+'_frames.csv')
    metadata_path = folder/(stem+'_capture.json')
    metadata = dict(schema_version=1,capture_id=folder.name,session_label=args.session_label,
                    input_kind='physical_webcam',status='initializing',camera_index=args.camera,
                    bit_ms=args.bit_ms,timeout_after_first_seconds=args.timeout_after_first_seconds,
                    timing_note='Sidecar read-return monotonic times are authoritative; not sensor exposure times. AVI is constant-FPS.',
                    timeout_note='Armed once at header validation completion, delayed by preamble/header acquisition; no waiting timeout.',
                    source_sha256={p.name:sha256(p) for p in (Path(__file__),Path(__file__).with_name('capture_start_detector.py'))},
                    audio=False,software=dict(python=platform.python_version(),opencv=cv.__version__))
    save_json(metadata_path,metadata)
    camera = writer = observer = None
    try:
        backend = {'auto':getattr(cv,'CAP_AVFOUNDATION',cv.CAP_ANY) if platform.system()=='Darwin' else cv.CAP_ANY,
                   'avfoundation':getattr(cv,'CAP_AVFOUNDATION',cv.CAP_ANY),'any':cv.CAP_ANY}[args.camera_backend]
        camera = cv.VideoCapture(args.camera,backend)
        if not camera.isOpened():
            raise RuntimeError('Camera unavailable. On macOS allow Camera access for Terminal/VS Code in System Settings > Privacy & Security > Camera; check device index.')
        requests = {}
        for name,prop,value in [('width',cv.CAP_PROP_FRAME_WIDTH,args.width),('height',cv.CAP_PROP_FRAME_HEIGHT,args.height),('fps',cv.CAP_PROP_FPS,args.fps)]:
            requests[name] = dict(requested=value,accepted=bool(camera.set(prop,value)),readback=camera.get(prop))
        metadata.update(camera_backend=camera.getBackendName(),camera_settings=requests)
        ok,frame = camera.read()
        if not ok:
            raise RuntimeError('Camera preview read failed.')
        print('Camera:',metadata['camera_backend'],requests,'Output:',folder)
        roi = tuple(map(int,cv.selectROI('Select bright patch only; ENTER accepts',frame,False,False)))
        cv.destroyWindow('Select bright patch only; ENTER accepts')
        x,y,w,h = roi
        if w<=0 or h<=0 or x<0 or y<0 or x+w>frame.shape[1] or y+h>frame.shape[0]:
            raise ValueError('Select a valid patch ROI.')
        metadata['roi'] = roi
        metadata['reference_rois'] = []
        print('Press S to start recording. Q/Escape stops. M manually arms timer (not optical evidence).')
        while True:
            cv.putText(frame,'S: START | Q: cancel',(15,30),cv.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),2)
            cv.imshow('Camera recorder',frame)
            key = cv.waitKey(1)&255
            if key in (27,ord('q')):
                metadata.update(status='cancelled',stop_reason='before_start')
                return folder
            if key==ord('s'):
                break
            ok,frame = camera.read()
            if not ok:
                raise RuntimeError('Camera preview failed.')
        height,width = frame.shape[:2]
        writer = cv.VideoWriter(str(video),cv.VideoWriter_fourcc(*'MJPG'),args.fps,(width,height))
        if not writer.isOpened():
            raise RuntimeError('MJPG/AVI writer unavailable; no silent codec fallback.')
        metadata.update(status='recording',video_codec='MJPG',video_dimensions=[width,height],nominal_writer_fps=args.fps)
        save_json(metadata_path,metadata)
        observer = HeaderObserver(args.bit_ms)
        timer = FirstPacketTimer(args.timeout_after_first_seconds)
        last_preview = [-1]
        def control(image, elapsed, timer):
            if elapsed-last_preview[0] >= .1:
                if image is not None:
                    view = image.copy()
                    state = 'WAITING FOR FIRST PACKET' if timer.armed is None else f'TIMER {max(0,timer.deadline-elapsed):.0f}s'
                    free = shutil.disk_usage(folder).free/1024**3
                    text = f'RECORDING {state} | {elapsed:.0f}s | free {free:.1f}GB' + (' LOW SPACE' if free<2 else '')
                    cv.putText(view,text,(10,25),cv.FONT_HERSHEY_SIMPLEX,.5,(0,0,255),1)
                    cv.imshow('Camera recorder',view)
                last_preview[0] = elapsed
            key = cv.waitKey(1)&255
            if key in (27,ord('q')) or cv.getWindowProperty('Camera recorder',cv.WND_PROP_VISIBLE)<1:
                return 'stop'
            if key==ord('m'):
                return 'manual'
        print('RECORDING / WAITING FOR FIRST PACKET. Storage grows indefinitely until detection or manual stop.')
        with open(frames_path,'x',newline='',encoding='utf-8') as stream:
            stats = record_stream(camera,writer,stream,observer,timer,roi,control)
        metadata.update(stats,status='stopped' if stats['stop_reason'] in ('manual_stop','timeout_after_first') and stats['unwritten_reads']==0 else 'failed',timeout_arming=vars(timer))
        with open(folder/(stem+'_header_observations.csv'),'x',newline='',encoding='utf-8') as stream:
            fields = ['estimated_preamble_start','codec','sequence','payload_bytes','validation_completed_seconds','analysis_latency_seconds']
            table = csv.DictWriter(stream,fieldnames=fields)
            table.writeheader()
            table.writerows(stats['observations'])
    except (Exception,KeyboardInterrupt) as exc:
        metadata.update(status='failed',error=str(exc) or type(exc).__name__)
    finally:
        for name, resource, method in [('camera',camera,'release'),('writer',writer,'release'),('observer',observer,'close')]:
            if resource is not None:
                try:
                    getattr(resource,method)()
                except Exception as exc:
                    metadata.setdefault('close_errors',{})[name] = str(exc)
        try:
            cv.destroyAllWindows()
        except Exception as exc:
            metadata['window_close_error'] = str(exc)
        if video.exists():
            try:
                metadata['validation'] = validate_video(video,metadata.get('written_frames',0),cv)
                metadata['checksums'] = {p.name:sha256(p) for p in folder.iterdir() if p.is_file() and p != metadata_path}
                if not all(metadata['validation'][k] for k in ('count_matches','first_readable','last_readable','nonzero')):
                    metadata['status'] = 'validation_failed'
            except Exception as exc:
                metadata.update(status='validation_failed',validation_error=str(exc))
        save_json(metadata_path,metadata)
    print('Retained capture:',folder)
    return folder
