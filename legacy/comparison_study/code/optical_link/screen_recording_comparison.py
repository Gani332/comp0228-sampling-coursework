"""Sidecar-timed screen captures, separate from the historical frozen study."""
import csv
import hashlib
import json
from pathlib import Path
import re
import time
import cv2
import numpy as np
from .protocol import GUARD_BITS, PREAMBLE, make_packet
from .screen_capture_packet import prepare, identifier, save_json
from .recording_model import FEATURES

REGISTRY = Path('data/screen/prepared')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def one(folder, pattern):
    paths = list(Path(folder).glob(pattern))
    if len(paths) != 1:
        raise ValueError(f'Expected exactly one {pattern} in {folder}; found {len(paths)}.')
    return paths[0]


def box(roi, shape):
    if len(roi) != 4 or any(type(v) is not int for v in roi):
        raise ValueError('ROIs must be integer x,y,width,height.')
    x,y,w,h = roi
    if min(x,y)<0 or min(w,h)<=0 or x+w>shape[1] or y+h>shape[0]:
        raise ValueError('ROI outside stored video pixels.')
    return x,y,w,h


def crop(gray, roi):
    x,y,w,h = roi
    return gray[y:y+h,x:x+w]


def nonoverlapping(boxes):
    for i,(x,y,w,h) in enumerate(boxes):
        for a,b,c,d in boxes[i+1:]:
            if max(x,a)<min(x+w,a+c) and max(y,b)<min(y+h,b+d):
                raise ValueError('Patch and independent reference ROIs must not overlap.')


def path_in_root(root, path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(root))
    except ValueError:
        raise ValueError('Capture and transmitter inputs must be inside the repository.')


def prepare_recording(root, capture, transmitter, recording_id, reference_rois=None):
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',recording_id):
        raise ValueError('Recording ID must be 1..80 letters/digits/underscores/hyphens.')
    historical = root/'data/analysis/receiver_layers_2026-10-24/manifest.json'
    if historical.exists() and any(v['id']==recording_id for v in json.loads(historical.read_text())):
        raise ValueError('Prepared ID collides with a historical recording; use a screen-specific ID.')
    destination = root/REGISTRY/recording_id
    if destination.exists():
        raise ValueError('Prepared ID already exists; choose a fresh ID. No overwrite.')
    capture = Path(capture).resolve()
    transmitter = Path(transmitter).resolve()
    tx_path = transmitter if transmitter.is_file() else transmitter/'manifest.json'
    meta_path = one(capture,'*_capture.json')
    video_path = one(capture,'*.avi')
    frames_path = one(capture,'*_frames.csv')
    meta = json.loads(meta_path.read_text())
    manifest = json.loads(tx_path.read_text())
    if meta.get('status') != 'stopped' or meta.get('unwritten_reads') != 0:
        raise ValueError('Capture is not a finalized clean recording; partial captures require explicit review.')
    for name, expected in meta['checksums'].items():
        if Path(name).name != name or digest(capture/name) != expected:
            raise ValueError('Capture checksum mismatch: '+name)
    with frames_path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    times = np.array([float(r['read_return_seconds']) for r in rows])
    if len(times)<40 or not np.isfinite(times).all() or np.any(np.diff(times)<=0):
        raise ValueError('Invalid authoritative timestamp sidecar.')
    if any(int(r['frame_index'])!=i for i,r in enumerate(rows)) or len(rows)!=meta['written_frames']:
        raise ValueError('Frame index/count mismatch.')
    entries = manifest['entries']
    sequences = [e['sequence'] for e in entries]
    if len(set(sequences))!=len(sequences):
        raise ValueError('Transmitter sequence IDs are ambiguous.')
    packets=[]
    for entry in entries:
        if entry['status']!='completed':
            raise ValueError('All supplied transmitter entries must be completed.')
        logged_path = tx_path.parent/entry['filename']
        logged = json.loads(logged_path.read_text())
        for field in ('codec','sequence','depth','payload_hex','wire_bits','bit_ms'):
            if logged[field]!=entry[field]:
                raise ValueError('Manifest/per-packet disagreement: '+field)
        p = prepare(bytes.fromhex(entry['payload_hex']),entry['codec'],entry['sequence'],entry['depth']==8,entry['bit_ms'])
        if entry['depth'] not in (1,8) or p.wire_bits.tolist()!=entry['wire_bits']:
            raise ValueError('Wire bits do not match declared packet/depth.')
        observed=[o for o in meta['observations'] if o['sequence']==entry['sequence']]
        if len(observed)!=1:
            raise ValueError(f"Missing/ambiguous header for sequence {entry['sequence']}; explicit window review required.")
        observation=observed[0]
        if observation['codec']!=entry['codec'] or observation['payload_bytes']!=len(p.packet.payload):
            raise ValueError('Optical header disagrees with transmitter settings.')
        if entry['bit_ms']!=meta['bit_ms']:
            raise ValueError('Recorder/transmitter bit duration mismatch.')
        period=entry['bit_ms']/1000
        preamble=observation['estimated_preamble_start']
        start=preamble-GUARD_BITS*period
        end=start+len(p.wire_bits)*period
        # Nominal window gets a 4% clock margin, capped by adjacent gaps below.
        margin = .5 + .04*len(p.wire_bits)*period
        window=[max(times[0],start-.5),min(times[-1],end+margin)]
        if start < times[0]-.1 or end>times[-1]+.1:
            raise ValueError('Recording does not cover a complete planned packet.')
        packets.append(dict(id=f"seq{entry['sequence']:03d}",window=window,
                            tx=entry,tx_file=path_in_root(root,logged_path),tx_sha256=digest(logged_path)))
    ordered=sorted(packets,key=lambda p:p['window'][0])
    for a,b in zip(ordered,ordered[1:]):
        # Never include the next packet's guard/preamble in a prior search window.
        a['window'][1]=min(a['window'][1],b['window'][0]-.001)
        if a['window'][1]<=a['window'][0]:
            raise ValueError('Packet window order is invalid; review association.')
    cap=cv2.VideoCapture(str(video_path))
    features={k:[] for k in FEATURES}
    try:
        ok,image=cap.read()
        if not ok: raise ValueError('Video unreadable.')
        patch=box(meta['roi'],image.shape)
        if patch[2]<5 or patch[3]<5: raise ValueError('Patch too small for 5x5 tiles.')
        if reference_rois is None:
            print('Select TWO static reference regions outside the flashing patch. ENTER accepts each.')
            reference_rois=[]
            for i in range(2):
                title=f'Reference {i+1} of 2'
                reference_rois.append(list(map(int,cv2.selectROI(title,image,False,False))))
                cv2.destroyWindow(title)
        if len(reference_rois)<2: raise ValueError('At least two independent reference ROIs required.')
        refs=[box(list(r),image.shape) for r in reference_rois]
        nonoverlapping([patch,*refs])
        count=0
        while ok:
            if count>=len(times): raise ValueError('More video frames than timestamp rows.')
            if list(image.shape[:2][::-1])!=meta['video_dimensions']:
                raise ValueError('Stored video dimensions changed.')
            gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
            area=crop(gray,patch)
            mean=float(area.mean())
            features['original'].append(mean)
            features['patch_mean'].append(mean)
            # array_split preserves every pixel for non-divisible ROI sizes.
            features['tiles'].append([float(tile.mean()) for row in np.array_split(area,5,axis=0) for tile in np.array_split(row,5,axis=1)])
            features['references'].append([float(crop(gray,r).mean()) for r in refs])
            count+=1
            ok,image=cap.read()
        if count!=len(times): raise ValueError('Decoded video/timestamp count mismatch.')
    finally:
        cap.release()
    inputs=[video_path,frames_path,meta_path,tx_path,*[root/p['tx_file'] for p in packets]]
    descriptor=dict(schema_version=1,input_kind='screen_camera_capture',id=recording_id,
                    capture_id=meta['capture_id'],tx_session_id=manifest['session_id'],
                    association='User-selected session; sequence/codec/length headers checked. Depth comes only from transmitter manifest; payload not used for acquisition.',
                    timestamp_policy='Exact read_return_seconds from sidecar; no FPS substitution or timestamp rebasing.',
                    original_roi=list(patch),study_roi=list(patch),reference_rois=refs,grid=[5,5],
                    tile_policy='numpy.array_split, all pixels retained',bit_ms=meta['bit_ms'],
                    packets=packets,cohort='screen_camera',frames=len(times),
                    inputs={path_in_root(root,p):digest(p) for p in inputs})
    destination.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(destination/'features.npz',times=times,**{k:np.asarray(v) for k,v in features.items()})
    descriptor['feature_sha256']=digest(destination/'features.npz')
    save_json(destination/'recording.json',descriptor)
    return destination/'recording.json'


def resolve(root, recording):
    root = Path(root).resolve()
    candidate=Path(recording)
    if not candidate.is_absolute(): candidate=Path(root)/candidate
    if candidate.is_dir(): candidate=candidate/'recording.json'
    if candidate.is_file():
        data=json.loads(candidate.read_text())
        if data.get('input_kind')=='screen_camera_capture': return candidate
    registered=Path(root)/REGISTRY/recording/'recording.json'
    return registered if registered.is_file() else None


def load(descriptor_path, root):
    path=Path(descriptor_path)
    d=json.loads(path.read_text())
    if d.get('input_kind')!='screen_camera_capture': raise ValueError('Not a prepared screen capture.')
    for name,expected in d['inputs'].items():
        if digest(Path(root)/name)!=expected: raise ValueError('Prepared source changed: '+name)
    feature=path.parent/'features.npz'
    if digest(feature)!=d['feature_sha256']: raise ValueError('Feature cache changed.')
    with np.load(feature,allow_pickle=False) as z:
        times=z['times'].copy(); f={k:z[k].copy() for k in FEATURES}
    if len(times)!=d['frames'] or not np.isfinite(times).all() or np.any(np.diff(times)<=0):
        raise ValueError('Invalid cached frame times.')
    if any(len(a)!=len(times) or not np.isfinite(a).all() for a in f.values()):
        raise ValueError('Invalid cached features.')
    windows=[]
    for p in d['packets']:
        entry=p['tx']
        logged=json.loads((Path(root)/p['tx_file']).read_text())
        for field in ('codec','sequence','depth','payload_hex','wire_bits','bit_ms'):
            if logged[field]!=entry[field]: raise ValueError('Prepared settings disagree with raw transmitter log.')
        original=make_packet(bytes.fromhex(entry['payload_hex']),entry['codec'],entry['sequence'])
        expected=prepare(original.payload,original.codec,original.sequence,entry['depth']==8,entry['bit_ms'])
        if entry['wire_bits']!=expected.wire_bits.tolist(): raise ValueError('Invalid cached wire packet.')
        tx=dict(payload_hex=entry['payload_hex'],codec=entry['codec'],sequence=entry['sequence'],
                transmitted_bits=''.join(map(str,original.bits)),wire_bits=entry['wire_bits'],
                interleave_depth=entry['depth'],bit_ms=entry['bit_ms'],
                scheduled_channel_seconds=len(original.bits)*entry['bit_ms']/1000)
        keep=(times>=p['window'][0])&(times<=p['window'][1])
        if keep.sum()<40: raise ValueError('Insufficient packet samples.')
        windows.append((p['id'],times[keep],{k:a[keep] for k,a in f.items()},tx))
    return windows,d


def run(root, descriptor, mode, output, seed, trials, random_payload):
    from .comparison_runner import score, modeled, aggregate, write_csv, plot_physical, plot_modeled
    from .receiver_layers import decode_comparison, COMPARISON_METHODS
    windows,d=load(descriptor,root)
    if mode in ('modeled','both') and d['bit_ms']!=200:
        raise ValueError('Modeled replay currently requires 200 ms. Use --mode physical for other durations.')
    base=Path(root)/output if output else Path(root)/'data/screen/comparison_results'/d['id']
    out=base/identifier();out.mkdir(parents=True,exist_ok=False)
    identity=dict(recording_id=d['id'],safe_recording_slug=d['id'],seed=seed,model_source_id=d['id'],
                  mode=mode,feature_sha256=d['feature_sha256'],cohort='screen_camera',
                  input_kind='sidecar-timed screen capture',source_config_sidecar=d['id']+'__run_metadata.json')
    if mode in ('physical','both'):
        rows=[]
        for pid,t,f,tx in windows:
            for method in COMPARISON_METHODS:
                start=time.perf_counter()
                rx=decode_comparison(t,f,method,bit_ms=tx['bit_ms'],depth=tx['interleave_depth'])
                row=score(rx,tx,identity=dict(identity,packet_id=pid,trial=None,evidence_kind='physical_replay'),
                          method=method,depth=tx['interleave_depth'],elapsed=time.perf_counter()-start)
                row['bit_seconds']=tx['bit_ms']/1000
                rows.append(row)
        write_csv(out/(d['id']+'__physical_results.csv'),rows)
        for depth, label in ((1, 'off'), (8, 'on')):
            subset = [r for r in rows if r['interleave_depth'] == depth]
            if subset:
                write_csv(out/(d['id']+f'__physical_results__interleaving_{label}.csv'),subset)
        plot_physical(out/(d['id']+'__physical_comparison.png'),rows)
        print(f'Physical replay: {len(rows)} rows, {len(windows)} packets.',flush=True)
    metadata=dict(simulation='residual' if mode in ('modeled','both') else None,prepared_recording=str(descriptor),prepared_sha256=digest(descriptor),source=d,mode=mode,
                  seed=seed,trials=trials,channel_ber_order='Compare canonical body after inverse permutation; mismatch count invariant under shared permutation.',
                  evidence='Physical replay and modeled sensitivity are separate; headers alone do not prove payload recovery.',
                  source_hashes={p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('comparison_runner.py'),Path(__file__).with_name('receiver_layers.py'),Path(__file__).with_name('recording_model.py')]})
    if mode in ('modeled','both'):
        # Residual calibration must subtract the actual transmitted wire order.
        model_windows=[(pid,t,f,dict(tx,transmitted_bits=''.join(map(str,tx['wire_bits'])))) for pid,t,f,tx in windows]
        rows,model=modeled(model_windows,dict(identity,evidence_kind='modeled_replay'),trials,seed,random_payload=random_payload)
        summary=aggregate(rows)
        write_csv(out/(d['id']+'__modeled_trials.csv'),rows)
        write_csv(out/(d['id']+'__modeled_summary.csv'),summary)
        plot_modeled(out/(d['id']+'__modeled_comparison.png'),summary)
        metadata['model']=model
    save_json(out/(d['id']+'__run_metadata.json'),metadata)
    return out
