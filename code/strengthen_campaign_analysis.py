"""Post-analysis diagnostics from unchanged physical recordings and saved trials.

Reproducible figure inputs; this adds interpretation, not physical trials,
parameter tuning or a new preregistered analysis claim.
"""
from collections import Counter
import os
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/comp0228-mpl')
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image
from analyse_campaign import PROJECT,ROOT,OUT,read,save,sha
from optical_link.campaign_diagnostics import error_runs,map_errors,paired_change,duration_bounds

D=OUT/'diagnostics';D.mkdir(exist_ok=True);FIG=PROJECT/'report_figures'
rows=[r for r in read(OUT/'packets.json') if r['phase']=='main']
stats=[]
for condition in ('OCC_CLUSTER','GLARE_BODY'):
    group=[r for r in rows if r['condition']==condition];runs=[]
    for r in group:
        rr=error_runs(r['error_indices'],r['body_bits'])
        assert rr==r['error_runs'];assert sum(rr)==r['body_errors']
        runs.extend(rr)
    hist=Counter(runs);errors=sum(r['body_errors'] for r in group)
    stats.append(dict(condition=condition,packets=len(group),packets_with_errors=sum(r['body_errors']>0 for r in group),
        errors=errors,body_bits=sum(r['body_bits'] for r in group),runs=len(runs),run_histogram=dict(sorted(hist.items())),
        errors_in_multibit_runs=sum(k*v for k,v in hist.items() if k>=2),maximum_run=max(runs),
        zero_to_one=sum(r['zero_to_one'] for r in group),one_to_zero=sum(r['one_to_zero'] for r in group)))
save(D/'physical_noise_structure.json',stats)
examples=[]
for codec,width in [('hamming74',7),('rs4',8)]:
    r=next(r for r in rows if r['video']==19 and r['codec']==codec and r['depth']==8)
    m=map_errors(r['error_indices'],r['body_bits'],8,width)
    assert m['affected_groups']==r['affected_correction_groups']
    examples.append(dict(video=19,sequence=r['sequence'],codec=codec,body_bits=r['body_bits'],depth=8,
        group_width=width,success=r['success'],**m))
save(D/'worked_interleaving.json',examples)
def nums(x):return ', '.join(map(str,x))
h,r=examples
table=[r'\begin{tabular}{@{}lcc@{}}\toprule',r'Zero-based indices & Hamming & Reed--Solomon\\\midrule']
for label,key in [('Wire bit','wire_indices'),('After inverse','coded_indices'),('Word / byte','correction_groups')]:
    table.append(f'{label} & {nums(h[key])} & {nums(r[key])}'+r'\\')
table+=[r'Correction budget & 1 bit/word & 2 bytes/body\\',r'Observed outcome & Pass & Fail\\',r'\bottomrule\end{tabular}']
(FIG/'campaign_mapping_table.tex').write_text('\n'.join(table)+'\n')

study=PROJECT/'data/analysis/coding_experiments_2026-10-24'
prov=read(study/'provenance.json');assert sha(study/'trials.csv.gz')==prov['trial_data_sha256']
cases=read(study/'scenarios.json');summary=read(study/'summary.json')
frame=pd.read_csv(study/'trials.csv.gz',usecols=['scenario_id','trial','codec','depth','success'])
paired=[]
for case in cases:
    if case['model'] not in ('burst_flip','glare_burst') or case['rate']!=.05:continue
    for j,codec in enumerate(['none','repeat3','repeat5','hamming74','rs4']):
        f=frame[(frame.scenario_id==case['scenario_id'])&(frame.codec==codec)]
        result=paired_change(f,seed=20261108+case['scenario_id']*10+j)
        assert result['trials']==2000
        for depth in (1,8):
            old=next(r for r in summary if r['scenario_id']==case['scenario_id'] and r['codec']==codec and r['depth']==depth)
            assert result[f'depth{depth}_successes']==old['successes']
        paired.append(dict(**case,codec=codec,**result))
assert len(paired)==40
save(D/'interleaving_duration_paired.json',paired)
pd.DataFrame(paired).to_csv(D/'interleaving_duration_paired.csv',index=False)

source=ROOT/'reviews/2026-11-07_video8_review/audit.json'
brackets=read(source)['visual_review']['onset_end_visual_bounds_seconds']
annotations=[]
for seq,b in zip((6,2),brackets):
    annotations.append(dict(video=8,sequence=seq,condition='GLARE_BODY',**b,
        duration_bounds_seconds=duration_bounds(b['onset'],b['end']),target_seconds=1.2,
        reference_status='Both visible and unblocked in inspected event frames; black reference illuminated',
        method='Previously reviewed coarse visual brackets from approximately 5 fps contact sheets; no confidence-interval interpretation',
        audit_sha256=sha(source)))
annotations.append(dict(video=19,sequence=4,condition='OCC_CLUSTER',
    reference_status='Black strip visibly occluded in event-5 contact sheet; do not assume valid common-mode reference',
    duration_bounds_seconds=None,method='Visual coverage check only; no precise duration assigned',
    audit_sha256=sha(ROOT/'reviews/2026-11-08_retakes11_12_19_review/Video19_event5.jpg')))
save(D/'exposure_annotations.json',dict(scope='Illustrative existing visual evidence, not a cohort-wide exposure survey or a basis for excluding packets',events=annotations))

# Scientific annotation of an unaltered recorded frame using the stored ROI geometry.
# Stored video is 1920x1080; clockwise orientation gives upright camera coordinates.
raw=Image.open(D/'setup_frame_native.png');assert raw.size==(1920,1080)
picture=np.rot90(np.asarray(raw),-1)
geom=read(OUT/'features/Video19.json');primary=read(OUT/'evidence/Video19_trace.json')['rois_stored_xywh']['patch']
def upright(box):
    x,y,w,h=box;return [1080-y-h,x,h,w]
plt.rcParams.update({'font.size':8,'pdf.fonttype':42,'ps.fonttype':42})
fig,ax=plt.subplots(figsize=(3.45,2.15),layout='constrained')
ax.imshow(picture);ax.set(xlim=(0,1080),ylim=(1050,365));ax.axis('off')
regions=[geom['regions_xywh'][0],primary,*geom['regions_xywh'][1:]]
colours=['#ffb000','#21c8ff','#fb6280','#fb6280']
for box,col in zip(regions,colours):
    x,y,w,h=upright(box);ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor=col,lw=1.2))
x,y,w,h=upright(regions[0])
for j in range(1,4):
    ax.plot([x+j*w/4]*2,[y,y+h],color=colours[0],lw=.45,alpha=.65)
    ax.plot([x,x+w],[y+j*h/4]*2,color=colours[0],lw=.45,alpha=.65)
for label,xy,where,col in [
    ('Black reference',(104,700),(120,420),colours[2]),
    ('Central ROI',(537,705),(540,450),colours[1]),
    ('White reference',(968,700),(925,420),colours[3]),
    ('Larger patch: 4 × 4 tiles',(765,855),(620,990),colours[0])]:
    ax.annotate(label,xy=xy,xytext=where,ha='center',va='center',fontsize=6.8,color='black',
        bbox=dict(boxstyle='round,pad=.2',fc='white',ec='none',alpha=.95),
        arrowprops=dict(arrowstyle='->',color=col,lw=1.0))
fig.savefig(FIG/'campaign_setup.pdf');fig.savefig(D/'campaign_setup.png',dpi=200);plt.close(fig)
save(D/'validation.json',dict(physical_packets=54,errors=96,run_counts=[s['runs'] for s in stats],
    paired_conditions=40,trials_per_condition=2000,bootstrap_resamples=20000,
    inference='Pointwise paired percentile bootstrap, conditional on each simulated channel; physical statistics descriptive',
    setup_frame=dict(video=19,requested_time_seconds=10,video_sha256=read(OUT/'evidence/Video19_trace.json')['sha256'],
        frame_sha256=sha(D/'setup_frame_native.png'),processing='Clockwise display rotation, display-region crop, geometric overlays; no scene alteration'),
    source_sha256={str(p.relative_to(PROJECT)):sha(p) for p in [PROJECT/'code/strengthen_campaign_analysis.py',PROJECT/'code/optical_link/campaign_diagnostics.py']},
    limitations=['Run length is not physical disturbance duration','Exposure brackets cover two illustrative glare events only','No main-outcome decoder retuning']))
print('Physical runs, worked mappings, paired burst-duration effects, exposure brackets and setup figure generated.')
