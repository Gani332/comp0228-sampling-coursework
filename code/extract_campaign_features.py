"""Extract fixed geometric features, preserving the audited PTS and original ROI.

Geometries come from pre-decoding review previews. Extraction never reads payloads.
The primary trace is copied exactly; full-patch controls isolate ROI enlargement.
"""
from pathlib import Path
import json,subprocess,re,sys,concurrent.futures
import numpy as np
from analyse_campaign import OUT,ROOT,read,save,sha

def inset(b,f):
    x,y,w,h=b
    return [int(round((x+w*(1-f)/2)/2)*2),int(round((y+h*(1-f)/2)/2)*2),int(round(w*f/2)*2),int(round(h*f/2)*2)]

def extract(n):
    dest=OUT/f'features/Video{n}.npz'
    if dest.exists():
        record=read(OUT/f'features/Video{n}.json')
        assert sha(dest)==record['feature_sha256'], 'Feature cache changed'
        assert record['video_sha256']==read(OUT/f'evidence/Video{n}_trace.json')['sha256'], 'Feature cache belongs to a different recording'
        print(f'Video{n}: verified cache',flush=True);return
    meta=read(OUT/f'evidence/Video{n}_trace.json');old=np.load(OUT/f'evidence/Video{n}_trace.npz')
    rois=meta['rois_stored_xywh'];x,y,w,h=rois['patch']
    # Reconstruct larger support from the earlier central-20% box when full
    # bounds were not recorded; rounding differs by at most several pixels.
    geom=OUT/f'evidence/Video{n}_geometry.json'
    full=read(geom).get('patch_bounds_xywh') if geom.exists() else None
    if n==7: full=[440,244,420,584]  # development preview, before secondary decoding
    patch=inset(full,.8) if full else [x-int(1.5*w),y-int(1.5*h),4*w,4*h]
    patch=[int(round(v/2)*2) for v in patch]
    regions=[patch,rois['black_reference'],rois['white_reference']]
    filters=['[0:v]split=3[s0][s1][s2]']
    for i,(x,y,w,h) in enumerate(regions):
        filters.append(f'[s{i}]crop={w}:{h}:{x}:{y},format=gray,scale=64:64:flags=area[r{i}]')
    filters.append('[r0][r1][r2]hstack=inputs=3,showinfo[out]')
    raw=ROOT/meta['video'];assert sha(raw)==meta['sha256']
    cp=subprocess.run(['ffmpeg','-hide_banner','-loglevel','info','-threads','2','-noautorotate','-i',str(raw),
        '-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[out]','-an','-fps_mode','passthrough',
        '-pix_fmt','gray','-f','rawvideo','-threads','1','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    images=np.frombuffer(cp.stdout,np.uint8).reshape(-1,64,192)
    pts=np.array([float(re.search(r'pts_time:\s*([\d.eE+-]+)',s).group(1)) for s in cp.stderr.decode(errors='replace').splitlines() if 'Parsed_showinfo' in s and 'pts_time:' in s])
    assert len(images)==len(old['times'])==len(pts)
    assert np.allclose(pts-pts[0],old['times'],atol=.00051,rtol=0)
    p=images[:,:,:64]
    tiles=np.column_stack([p[:,i*16:(i+1)*16,j*16:(j+1)*16].mean(axis=(1,2)) for i in range(4) for j in range(4)])
    refs=np.column_stack([images[:,:,k*64+j*32:k*64+(j+1)*32].mean(axis=(1,2)) for k in (1,2) for j in (0,1)])
    np.savez_compressed(dest,times=old['times'],original=old['patch'],patch_mean=p.mean(axis=(1,2)),tiles=tiles,references=refs)
    save(OUT/f'features/Video{n}.json',dict(video_sha256=meta['sha256'],feature_sha256=sha(dest),
        regions_xywh=regions,downsample='64x64 area mean, then 4x4 tiles; reference regions split into two halves',
        geometry_note='November 7 development geometry read from preview' if n==7 else 'Pre-existing full bounds, or 4x enlargement of central-20% box (rounding approximation)',
        frames=len(pts),primary_exactly_preserved=bool(np.array_equal(old['patch'],np.load(dest)['original'])),
        original_pts_verified=True))
    print(f'Video{n}: extracted {len(pts)} frames',flush=True)

if __name__=='__main__':
    nums=list(map(int,sys.argv[1:])) or list(range(7,22))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for f in concurrent.futures.as_completed([pool.submit(extract,n) for n in nums]):f.result()
