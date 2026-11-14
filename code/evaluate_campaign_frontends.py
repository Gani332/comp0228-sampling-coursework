"""Replay frozen front ends on identical videos; preserve failed acquisitions.

Run development first (argument 'development'), then 'main'. No parameter search.
Reference variants are stress tests on blockage, not evidence of valid references.
"""
import sys
import numpy as np
import pandas as pd
from analyse_campaign import OUT,read,save,summarize,sha
from optical_link.campaign_frontends import decode,METHODS
from optical_link.protocol import make_packet
from optical_link.coding_experiments import interleave

def run(stage):
    if stage=='main':assert (OUT/'development_frontends.json').exists(),'Validate development before main'
    rows=[r for r in read(OUT/'packets.json') if (r['video']==7 if stage=='development' else r['video']>=8)]
    output=[];verified=set()
    for r in rows:
        if r['video'] not in verified:
            metadata=read(OUT/f"features/Video{r['video']}.json")
            assert metadata['feature_sha256']==sha(OUT/f"features/Video{r['video']}.npz"), 'Feature data changed'
            assert metadata['video_sha256']==r['video_sha256'], 'Wrong recording features'
            verified.add(r['video'])
        f=np.load(OUT/f"features/Video{r['video']}.npz");t=f['times']
        if r['acquired']:
            end=r['preamble_start']+(80+r['body_bits'])*.2+.4
            mask=(t>=r['preamble_start']-.4)&(t<=end)
            features={k:f[k][mask] for k in ('original','patch_mean','tiles','references')}
        for method in METHODS:
            if r['acquired']:d=decode(t[mask],features,method,depth=r['depth'])
            else:d={'failure_stage':'acquisition_or_header'}
            matched=all(d.get(k)==r[k] for k in ('codec','sequence','payload_bytes'))
            truth=interleave(make_packet(bytes.fromhex(r['payload_hex']),r['codec'],r['sequence']).body_bits,r['depth'])
            raw=d.get('wire_body_bits') if matched else None
            errors=int(np.count_nonzero(raw!=truth)) if raw is not None else None
            ok=bool(matched and d.get('crc_ok',False) and d.get('payload',b'').hex()==r['payload_hex'])
            row=dict(r,method=method,success=ok,crc_ok=bool(d.get('crc_ok',False)),
                exact_message=d.get('payload',b'').hex()==r['payload_hex'],
                failure_stage=d.get('failure_stage'),body_errors=errors,delivered_bits=8*r['payload_bytes']*ok,
                acquisition_shared=True,header_matches=matched,
                reference_assumption='stress_test_occluded_references' if r['condition'].startswith('OCC') and method in ('reference','combined') else 'standard')
            # Drop primary-only error details rather than misleadingly retaining them.
            for key in ('error_indices','error_runs','zero_to_one','one_to_zero','max_errors_per_correction_group','affected_correction_groups','correction_group_errors'):row.pop(key,None)
            if method=='original':
                assert row['success']==r['success'] and errors==r['body_errors'],('Primary mismatch',r['video'],r['sequence'])
            output.append(row)
        print(f"Video {r['video']} packet {r['sequence']} completed",flush=True)
    save(OUT/f'{stage}_frontends.json',output)
    pd.DataFrame(output).to_csv(OUT/f'{stage}_frontends.csv',index=False)
    summary=summarize(output,['phase','condition','method'])
    save(OUT/f'{stage}_frontends_summary.json',summary)
    pd.DataFrame(summary).to_csv(OUT/f'{stage}_frontends_summary.csv',index=False)
    # Paired changes are descriptive, with the same physical denominator.
    paired=[]
    for condition in sorted({r['condition'] for r in output}):
        base={(r['video'],r['sequence']):r for r in output if r['condition']==condition and r['method']=='original'}
        for method in METHODS:
            variant=[r for r in output if r['condition']==condition and r['method']==method]
            paired.append(dict(condition=condition,method=method,n=len(variant),
                rescued=sum(r['success'] and not base[r['video'],r['sequence']]['success'] for r in variant),
                harmed=sum(not r['success'] and base[r['video'],r['sequence']]['success'] for r in variant)))
    save(OUT/f'{stage}_paired_frontends.json',paired)

if __name__=='__main__':run(sys.argv[1])
