"""Original video -> one brightness measurement per presentation timestamp.

OpenCV rotation is disabled so preview and ROI use the same stored pixel grid.
FFprobe supplies timestamps: average phone FPS is never used as a clock.
"""
import hashlib
import json
import subprocess
from pathlib import Path
import cv2
import numpy as np


def preview(path, frame=0):
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, image = cap.read()
        if not ok:
            raise ValueError('Cannot read that video frame.')
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()


def extract_trace(path, roi):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if len(roi) != 4 or any(not isinstance(x, (int, np.integer)) for x in roi):
        raise ValueError('ROI must be integer (x, y, width, height).')
    x, y, w, h = map(int, roi)
    if min(x, y) < 0 or min(w, h) <= 0:
        raise ValueError('ROI must have nonnegative origin and positive dimensions.')
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
           '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    frames = json.loads(result.stdout).get('frames', [])
    if not frames or any('best_effort_timestamp_time' not in f for f in frames):
        raise ValueError('Video lacks usable per-frame timestamps. Keep the original file.')
    t = np.array([float(f['best_effort_timestamp_time']) for f in frames])
    if np.any(np.diff(t) <= 0):
        raise ValueError('Non-monotonic video timestamps; do not silently substitute average FPS.')
    t -= t[0]
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
    values = []
    try:
        while True:
            ok, image = cap.read()
            if not ok:
                break
            if x+w > image.shape[1] or y+h > image.shape[0]:
                raise ValueError('ROI extends outside the stored video frame.')
            crop = cv2.cvtColor(image[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
            values.append(float(crop.mean()))
    finally:
        cap.release()
    if len(values) != len(t):
        raise ValueError(f'Frame/timestamp mismatch: {len(values)} decoded vs {len(t)} timestamps.')
    if len(t) < 2:
        raise ValueError('Video is too short.')
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            digest.update(chunk)
    meta = {'video': str(path), 'video_sha256': digest.hexdigest(), 'roi_xywh': list(roi),
            'frames': len(t), 'duration_seconds': float(t[-1]),
            'median_frame_interval_seconds': float(np.median(np.diff(t))),
            'max_frame_gap_seconds': float(np.max(np.diff(t))),
            'rotation': 'stored pixels, autorotation disabled', 'data_kind': 'physical_video'}
    return t, np.array(values), meta


def save_trace(times, values, metadata, prefix):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    # Unique attempt prefixes in the notebook preserve failures as well as successes.
    with prefix.with_suffix('.csv').open('x') as f:
        np.savetxt(f, np.column_stack([times, values]), delimiter=',',
                   header='time_seconds,mean_brightness', comments='')
    with prefix.with_suffix('.json').open('x') as f:
        json.dump(metadata, f, indent=2)
