"""Explicitly extract or verify cached features; never controls hardware.

Uses the frozen manifest's geometry and existing actual video timestamps.
Existing feature caches are verified and reused. No parameter fitting here.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def extract(root,study,video):
    folder=study/'features';folder.mkdir(exist_ok=True)
    out=folder/(video['id']+'.npz');metadata=out.with_suffix('.json')
    if out.exists():
        meta=json.loads(metadata.read_text())
        if (meta['feature_sha256']!=digest(out) or meta['video_sha256']!=video['sha256']
            or meta['study_roi']!=video['study_roi'] or meta['reference_rois']!=video['reference_rois']):
            raise ValueError('Existing feature cache differs; preserve and investigate: '+video['id'])
        print('Verified cache:',video['id'],flush=True);return
    if metadata.exists():raise ValueError('Orphan metadata exists; preserve and investigate.')
    source=root/video['video']
    if digest(source)!=video['sha256']:raise ValueError('Source video changed: '+video['id'])
    if video['trace_format']=='csv':t,original=np.loadtxt(root/video['trace'],delimiter=',',skiprows=1).T
    else:
        with np.load(root/video['trace']) as z:t,original=z['times'],z['brightness']
    if len(t)<40 or np.any(np.diff(t)<=0):raise ValueError('Invalid archived timestamps.')
    boxes=[video['original_roi'],video['study_roi'],*video['reference_rois']]
    for x,y,w,h in boxes:
        if min(x,y)<0 or min(w,h)<=0:raise ValueError('Invalid geometric region.')
    x0=min(b[0] for b in boxes);y0=min(b[1] for b in boxes)
    x1=max(b[0]+b[2] for b in boxes);y1=max(b[1]+b[3] for b in boxes)
    local=[(x-x0,y-y0,w,h) for x,y,w,h in boxes]
    print('Extracting:',video['id'],len(t),'frames',flush=True)
    cap=cv2.VideoCapture(str(source),cv2.CAP_FFMPEG,[cv2.CAP_PROP_N_THREADS,2])
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO,0)
    if not cap.isOpened():raise ValueError('Cannot decode video.')
    patch=[];tiles=[];refs=[];reextracted=[];saturated=[]
    try:
        while True:
            ok,img=cap.read()
            if not ok:break
            if x1>img.shape[1] or y1>img.shape[0]:raise ValueError('Region outside stored frame.')
            gray=cv2.cvtColor(img[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY)
            a,b,w,h=local[0];reextracted.append(float(gray[b:b+h,a:a+w].mean()))
            a,b,w,h=local[1];crop=gray[b:b+h,a:a+w]
            if w%5 or h%5:raise ValueError('Study patch dimensions must divide evenly into 5×5 tiles.')
            tiles.append(crop.reshape(5,h//5,5,w//5).mean(axis=(1,3)).ravel())
            patch.append(float(crop.mean()));saturated.append(float((crop>=250).mean()))
            refs.append([float(gray[b:b+h,a:a+w].mean()) for a,b,w,h in local[2:]])
    finally:cap.release()
    if len(tiles)!=len(t):raise ValueError('Decoded frames do not match archived presentation timestamps.')
    np.savez_compressed(out,times=t,original=original,original_reextracted=reextracted,
                        patch_mean=patch,tiles=tiles,references=refs,saturated_fraction=saturated)
    meta={'video_id':video['id'],'video_sha256':video['sha256'],'feature_sha256':digest(out),
          'frames':len(t),'original_roi':video['original_roi'],'study_roi':video['study_roi'],
          'reference_rois':video['reference_rois'],'grid':[5,5],
          'anchor':'archived original-ROI brightness and real frame timestamps',
          'extraction':'OpenCV BGR2GRAY, stored pixels, fixed geometry, one pass',
          'max_original_trace_difference':float(np.max(abs(np.array(reextracted)-original))),
          'maximum_frame_gap_seconds':float(max(np.diff(t)))}
    metadata.write_text(json.dumps(meta,indent=2)+'\n')
    print('Saved:',video['id'],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--cohort',choices=['development','earlier_batch_evaluation','guided_batch_evaluation'])
    args=p.parse_args();root=args.root.resolve();study=args.study.resolve()
    manifest=json.loads((study/'manifest.json').read_text())
    if args.cohort:manifest=[v for v in manifest if v['cohort']==args.cohort]
    cv2.setNumThreads(1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda v:extract(root,study,v),manifest))


if __name__=='__main__':main()
