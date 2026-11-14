"""Generate report tables/figures from verified analysis, with numeric assertions."""
import os
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/comp0228-mpl')
from pathlib import Path
import re,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from analyse_campaign import PROJECT,ROOT,OUT,read,save,sha
from optical_link.physical_campaign_receiver import decode_pilot

FIG=PROJECT/'report_figures';FIG.mkdir(exist_ok=True)
plt.rcParams.update({'font.size':8,'axes.spines.top':False,'axes.spines.right':False,
    'pdf.fonttype':42,'ps.fonttype':42,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7})
ROWS=read(OUT/'packets.json');MAIN=[r for r in ROWS if r['phase']=='main']
SUMMARY=read(OUT/'summary.json');FRONT=read(OUT/'main_frontends_summary.json')
assert all(r['logs_verified'] for r in ROWS), 'Final provenance text requires verified transmitter logs'
assert len(MAIN)==54 and sum(r['success'] for r in MAIN)==35
assert sum(r['body_errors'] for r in MAIN)==96
assert sum(r['success'] for r in read(OUT/'earlier_attempt_packets.json'))==30
assert all(v['primary_exactly_preserved'] for v in (read(p) for p in (OUT/'features').glob('*.json')))

names={'none':'Uncoded','repeat3':r'Repetition $\times3$','repeat5':r'Repetition $\times5$',
       'hamming74':'Hamming','rs4':'Reed--Solomon'}
configs=[('none',1),('repeat3',1),('repeat5',1),('hamming74',1),('hamming74',8),('rs4',1),('rs4',8)]
table=[r'\begin{tabular}{@{}lrrrr@{}}\toprule',r'Code/depth & Success & Errors/bits & BER (\%) & bit/s\\\midrule']
for c,d in configs:
    r=next(r for r in SUMMARY['by_condition_code'] if r['phase']=='main' and r['condition']=='OCC_CLUSTER' and r['codec']==c and r['depth']==d)
    assert r['packets']==6
    table.append(f"{names[c]} / {d} & {r['successes']}/6 & {r['errors']}/{r['observed_body_bits']} & {100*r['conditional_ber']:.2f} & {r['goodput_bps']:.3f}"+r'\\')
table+=[r'\bottomrule\end{tabular}']
(FIG/'campaign_coding_table.tex').write_text('\n'.join(table)+'\n')

methods=['original','patch_mean','reference','spatial','combined','ewma','kalman']
labels=['Central ROI','Larger-patch mean','Reference','Spatial quartile','Combined','EWMA','Kalman']
table=[r'\begin{tabular}{@{}lrrrr@{}}\toprule',r'& \multicolumn{2}{c}{Body glare} & \multicolumn{2}{c}{Blockage}\\',
       r'Method & Success & Errors & Success & Errors\\\midrule']
for m,l in zip(methods,labels):
    glare=next(r for r in FRONT if r['condition']=='GLARE_BODY' and r['method']==m)
    block=next(r for r in FRONT if r['condition']=='OCC_CLUSTER' and r['method']==m)
    table.append(f"{l} & {glare['successes']}/12 & {glare['errors']} & {block['successes']}/42 & {block['errors']}"+r'\\')
table.append(r'\bottomrule\end{tabular}')
(FIG/'campaign_frontends_table.tex').write_text('\n'.join(table)+'\n')

fig,axes=plt.subplots(2,1,figsize=(3.45,2.9),layout='constrained')
for ax,(v,seq,title) in zip(axes,[(8,6,'Recorded glare: uncoded, Video 8')]):
    if v==19:r=next(r for r in MAIN if r['video']==19 and r['codec']=='rs4' and r['depth']==8)
    else:r=next(r for r in MAIN if r['video']==v and r['sequence']==seq)
    tr=np.load(OUT/f'evidence/Video{v}_trace.npz');t=tr['times'];y=tr['patch']
    start=r['preamble_start'];end=start+(80+r['body_bits'])*.2+.4
    window=(t>=start-.4)&(t<=end)
    d=decode_pilot(t[window],y[window],depth=r['depth'])
    assert d.get('failure_stage')==r['failure_stage'], 'Figure replay differs from audited packet'
    errors=np.array(r['error_indices']);centres=d['start_seconds']+(80+errors+.5)*.2
    origin=float(centres[0]-1);keep=(t>=origin)&(t<=centres[-1]+1)
    ax.plot(t[keep]-origin,y[keep],lw=.85,color='#17658a')
    ax.axhline(d['threshold'],ls='--',lw=.7,color='gray',label='Threshold')
    ax.scatter(centres-origin,np.interp(centres,t,y),marker='x',color='#cc5229',s=25,label='Wrong bit')
    ax.set(title=title,ylabel='Brightness',ylim=(-5,260));ax.set_xlabel('Time from window start (s)')
axes[0].legend(fontsize=6,ncol=2,loc='upper left')
noise=read(OUT/'diagnostics/physical_noise_structure.json')
xx=np.arange(1,7)
for shift,condition,colour,label in [(-.18,'OCC_CLUSTER','#17658a','Blockage: 51 runs'),(.18,'GLARE_BODY','#cc5229','Glare: 10 runs')]:
    n=next(r for r in noise if r['condition']==condition)
    counts=[n['run_histogram'].get(str(i),0) for i in xx]
    assert sum(counts)==n['runs'] and sum(x*c for x,c in zip(xx,counts))==n['errors']
    axes[1].bar(xx+shift,counts,width=.36,color=colour,label=label)
axes[1].set(xlabel='Consecutive erroneous body bits',ylabel='Number of runs',xticks=xx,ylim=(0,40))
axes[1].legend(fontsize=6,frameon=False)
fig.savefig(FIG/'campaign_noise.pdf');plt.close(fig)

videos=[9,11,12,15,17,19];grid=np.empty((7,6));errors=np.empty((7,6),int)
for i,(c,d) in enumerate(configs):
    for j,v in enumerate(videos):
        r=next(r for r in MAIN if r['video']==v and r['codec']==c and r['depth']==d)
        grid[i,j]=r['success'];errors[i,j]=r['body_errors']
fig,ax=plt.subplots(figsize=(3.45,2.45),layout='constrained')
ax.imshow(grid,cmap=ListedColormap(['#f3b696','#b1d9c4']),vmin=0,vmax=1,aspect='auto')
for i in range(7):
    for j in range(6):ax.text(j,i,str(errors[i,j]),ha='center',va='center',fontsize=8)
ax.set_xticks(range(6),['R1\n12 B','R1\n8 B','R1\n4 B','R2\n4 B','R2\n12 B','R2\n8 B'])
ax.set_yticks(range(7),['Uncoded','Repeat 3','Repeat 5','Hamming / 1','Hamming / 8','RS / 1','RS / 8'])
ax.set_xticks(np.arange(-.5,6,1),minor=True);ax.set_yticks(np.arange(-.5,7,1),minor=True)
ax.grid(which='minor',color='white',linewidth=2);ax.tick_params(which='both',length=0)
fig.savefig(FIG/'campaign_packets.pdf');plt.close(fig)

sim=read(PROJECT/'data/analysis/coding_experiments_2026-10-24/summary.json')
paired=read(OUT/'diagnostics/interleaving_duration_paired.json')
fig,axes=plt.subplots(2,3,figsize=(7.05,3.65),layout='constrained')
colours=['#444444','#d55e00','#aa4499','#0072b2','#009e73']
for j,(model,title) in enumerate(zip(('iid_flip','burst_flip','glare_burst'),('Independent flips','Correlated flips','Forced-one glare'))):
    for c,col in zip(('none','repeat3','repeat5','hamming74','rs4'),colours):
        rows=sorted([r for r in sim if r['sweep']=='rate' and r['model']==model and r['codec']==c and r['depth']==1],key=lambda r:r['rate'])
        x=[r['rate'] for r in rows]
        for i,(metric,prefix) in enumerate((('success_rate','success'),('goodput_bps','goodput'))):
            if i==1 and j>0:continue
            ax=axes[i,j];ax.plot(x,[r[metric] for r in rows],marker='o',ms=2,lw=1,color=col,label=names[c].replace('--','–'))
            ax.fill_between(x,[r[prefix+'_ci_low'] for r in rows],[r[prefix+'_ci_high'] for r in rows],color=col,alpha=.13)
            ax.set_xlim(0,.2);ax.grid(alpha=.18)
    axes[0,j].set_title(title,fontsize=9);axes[0,j].set_ylim(0,1.04)
    axes[0,j].set_xlabel('Flip probability p' if j==0 else 'Bad-state occupancy ρ')
    if j==0:
        axes[1,j].set_ylim(0,2.05);axes[1,j].set_xlabel('Flip probability p')
    else:
        ax=axes[1,j]
        for c,col in zip(('none','repeat3','repeat5','hamming74','rs4'),colours):
            if c=='none':continue
            rr=sorted([r for r in paired if r['model']==model and r['codec']==c],key=lambda r:r['mean_burst_slots'])
            x=[r['mean_burst_slots'] for r in rr]
            ax.plot(x,[100*r['change'] for r in rr],marker='o',ms=2,lw=1,color=col)
            ax.fill_between(x,[100*r['ci_low'] for r in rr],[100*r['ci_high'] for r in rr],color=col,alpha=.15)
        ax.axhline(0,ls='--',color='gray',lw=.7)
        ax.set(xlabel='Mean bad-run length L (slots)',ylabel='Recovery change (pp)',xticks=[2,4,8,16],ylim=(-40,85),yticks=[-40,0,40,80])
        ax.set_title('Depth 8 − depth 1; ρ = 0.05',fontsize=7.5);ax.grid(alpha=.18)
axes[0,0].set_ylabel('Exact+CRC fraction');axes[1,0].set_ylabel('Goodput (bit/s)')
handles,legend=axes[0,0].get_legend_handles_labels();fig.legend(handles,legend,loc='outside upper center',ncol=5,fontsize=7,frameon=False)
fig.savefig(FIG/'campaign_simulation.pdf');plt.close(fig)

testlog=(OUT/'evidence/software_tests.log').read_text()
assert re.search(r'^OK$',testlog,re.M), 'Tests must pass before report generation'
count=int(re.search(r'Ran (\d+) tests',testlog).group(1))
(FIG/'campaign_test_count.tex').write_text(f'The current full suite passes {count} tests.\n')
save(OUT/'report_validation.json',dict(primary_main_packets=54,primary_successes=35,primary_errors=96,
    physical_table_rows=7,frontend_table_rows=7,simulation_curves=28,tests_passed=count,
    source_sha256={str(p.relative_to(PROJECT)):sha(p) for p in [PROJECT/'code/analyse_campaign.py',PROJECT/'code/verify_omar_logs.py',PROJECT/'code/optical_link/campaign_frontends.py',PROJECT/'code/evaluate_campaign_frontends.py',PROJECT/'code/extract_campaign_features.py',PROJECT/'code/build_campaign_report.py']},
    remote_logs_verified=all(r['logs_verified'] for r in ROWS),
    limitations=['Parallel remote collection used a placeholder release file','Manual exposure variation','Selected retakes; incomplete original raw archive','Reference occlusion in blockage clips','Acquisition-failure identities associated by capture time, not decoded headers']))
print('Figures, tables and numerical checks generated.')
