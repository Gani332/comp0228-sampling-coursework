"""Descriptive physical diagnostics and paired Monte Carlo uncertainty.

No decoder selection or parameter fitting. Physical runs are counted within
packets; model confidence intervals resample paired trials, never physical bits.
"""
import numpy as np
from .coding_experiments import interleaver_order

def error_runs(indices, length):
    ix=np.asarray(indices,dtype=int)
    if length<1 or np.any(ix<0) or np.any(ix>=length) or len(np.unique(ix))!=len(ix):
        raise ValueError('Need unique, in-range error positions')
    if not len(ix):return []
    ix=np.sort(ix);groups=np.split(ix,np.flatnonzero(np.diff(ix)>1)+1)
    return [len(g) for g in groups]

def map_errors(indices, length, depth, group_width):
    error_runs(indices,length)
    if group_width<1 or length%group_width:raise ValueError('Incomplete correction groups')
    coded=interleaver_order(length,depth)[np.asarray(indices,dtype=int)]
    groups=coded//group_width
    return dict(wire_indices=list(map(int,indices)),coded_indices=coded.tolist(),
                correction_groups=groups.tolist(),affected_groups=len(np.unique(groups)),
                maximum_errors_per_group=int(np.bincount(groups).max()) if len(groups) else 0)

def paired_change(frame, *, seed=20261108, resamples=20000):
    """Percentile bootstrap of depth-8 minus depth-1 exact+CRC success.

Each pair shares a payload/noise trial. Multinomial sampling of {-1,0,1}
counts is exactly the nonparametric paired bootstrap for the mean difference.
The interval is pointwise and conditional on the model, not simultaneous.
"""
    wide=frame.pivot(index='trial',columns='depth',values='success')
    if set(wide.columns)!={1,8} or wide.isna().any().any() or len(wide)<2:
        raise ValueError('Complete pairs at depths 1 and 8 required')
    a=wide[1].to_numpy();b=wide[8].to_numpy()
    if not np.isin(a,[0,1]).all() or not np.isin(b,[0,1]).all():raise ValueError('Binary outcomes required')
    d=b-a;n=len(d);counts=np.array([(d==-1).sum(),(d==0).sum(),(d==1).sum()])
    draws=np.random.default_rng(seed).multinomial(n,counts/n,size=resamples)
    means=(draws[:,2]-draws[:,0])/n
    low,high=np.quantile(means,[.025,.975])
    return dict(trials=n,depth1_successes=int(a.sum()),depth8_successes=int(b.sum()),
                harmed=int(counts[0]),unchanged=int(counts[1]),rescued=int(counts[2]),
                change=float(d.mean()),ci_low=float(low),ci_high=float(high),
                seed=seed,resamples=resamples)

def duration_bounds(onset, end):
    if len(onset)!=2 or len(end)!=2 or onset[0]>onset[1] or end[0]>end[1] or end[0]<onset[1]:
        raise ValueError('Ordered, nonoverlapping time brackets required')
    return [end[0]-onset[1],end[1]-onset[0]]
