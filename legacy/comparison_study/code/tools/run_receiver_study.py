"""Evaluate frozen receiver layers on every retained physical packet.

No hardware actions. Output directory must be new. Source/geometry integrity
checks prevent silently changing a frozen configuration during replay.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True,help='Source directory containing optical_link/')
    parser.add_argument('--data-root',type=Path,help='Data directory; defaults to sibling data/ in the current layout')
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve();study=args.study.resolve()
    data_root = args.data_root.resolve() if args.data_root else (root.parent/'data' if (root.parent/'data').is_dir() else root)
    sys.path.insert(0,str(root))
    from optical_link.receiver_study import evaluate,summarize,save_json
    from optical_link.receiver_layers import METHODS
    config=json.loads((study/'frozen_config.json').read_text())
    for path,expected in [(study/'manifest.json',config['geometry_manifest_sha256']),
                          (root/'optical_link/receiver_layers.py',config['receiver_source_sha256'])]:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Frozen source or geometry changed: '+str(path))
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    all_rows=[];summary=[]
    for method in METHODS:
        rows=evaluate(data_root,study,method,alpha=config['reference_alpha'],
                      quantile=config['spatial_quantile'],save_to=out/method)
        all_rows.extend(rows)
        for cohort in ['development','earlier_batch_evaluation','guided_batch_evaluation','all']:
            selected=rows if cohort=='all' else [r for r in rows if r['cohort']==cohort]
            s=dict(method=method,cohort=cohort,**summarize(selected));summary.append(s)
            print(method,cohort,'success',str(s['successes'])+'/'+str(s['packets']),
                  'channel errors',s['channel_errors'],'payload outputs',s['payload_outputs'],flush=True)
    save_json(out/'all_results.json',all_rows);save_json(out/'summary.json',summary)
    fields=['trial_id','video_id','cohort','condition','method','codec','message','sequence','status',
            'received_text','body_channel_bit_errors','body_channel_bits','body_channel_ber',
            'payload_bit_errors','payload_bits','payload_ber','crc_ok','exact_payload_match',
            'packet_failed','failure_stage','reason','channel_seconds_including_overhead',
            'correct_delivered_bits','correct_payload_goodput_bps','alpha','quantile']
    with (out/'all_results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(all_rows)
    # Paired outcomes compare the same physical packet; they are not new trials.
    paired=[]
    ids=list(dict.fromkeys(r['trial_id'] for r in all_rows))
    for id in ids:
        cases={r['method']:r for r in all_rows if r['trial_id']==id}
        reference=cases['patch_mean']
        row={'trial_id':id,'cohort':reference['cohort'],'message':reference['message'],'codec':reference['codec']}
        for method,m in cases.items():
            row[method+'_success']=not m['packet_failed']
            row[method+'_channel_errors']=m['body_channel_bit_errors']
        paired.append(row)
    save_json(out/'paired_results.json',paired)
    save_json(out/'frozen_config_used.json',config)
    print('Saved physical receiver comparison:',out,flush=True)


if __name__=='__main__':main()
