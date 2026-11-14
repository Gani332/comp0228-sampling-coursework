"""Verify separately imported transmitter logs without merging recording folders.

Match original capture time first, then header order and optical relative timing.
Regenerate every encoded/interleaved wire bit; check actual renderer slot logs.
Re-decode at the logged depth without changing receiver settings or acquisition.
For acquisition failures, timestamp association is explicitly not header proof.
"""
from pathlib import Path
from datetime import datetime
from zipfile import ZipFile
import copy,json
import numpy as np
from analyse_campaign import ROOT,PROJECT,OUT,read,save,sha,SESSIONS
from optical_link.physical_campaign import wire_packet
from optical_link.physical_campaign_receiver import decode_pilot
from optical_link.protocol import GUARD_BITS,PREAMBLE,HEADER_BITS

IMPORT=PROJECT/'data/imports/omar_2026-11-08/physical_campaign_mac_v1'
REVIEW=ROOT/'reviews/2026-11-08_omar_log_verification'
OLD=ROOT/'reviews/2026-11-08_videos11_21_review'

def main():
    sessions=[(p,read(p)) for p in IMPORT.glob('attempts/*/session.json')]
    plan_sha=sha(PROJECT/'data/plans/physical_campaign_v1/schedule.csv')
    matches={};timing=[];unchanged=[]
    output=OUT/'evidence/omar_verified';output.mkdir(exist_ok=True)
    for n in range(11,22):
        a=copy.deepcopy(read(OLD/f'Video{n}_audit.json'));meta=a['trace']
        probe=read(OLD/f'Video{n}_probe.json')
        created=datetime.fromisoformat(probe['format']['tags']['com.apple.quicktime.creationdate']).timestamp()
        candidates=[(p,s) for p,s in sessions if s['session_id']==a['session_id'] and s['status']=='controller_completed'
                    and -2<=s['packets'][0]['host_called_unix']-created<12]
        assert len(candidates)==1,(n,'Ambiguous capture-time match',len(candidates))
        path,session=candidates[0];assert session['plan_sha256']==plan_sha
        planned=SESSIONS[a['session_id']];expected={int(r['sequence']):r for r in planned}
        assert [int(r['sequence']) for r in planned]==[int(r['sequence']) for r in session['packets']]
        tr=np.load(OLD/f'Video{n}_trace.npz');t,y=tr['times'],tr['patch']
        before=copy.deepcopy(a['packets']);byseq={r['sequence']:r for r in a['packets']}
        offsets=[];slot_late=[];checks=[]
        for sent in session['packets']:
            tx_path=path.parent/sent['tx_file'];tx=read(tx_path)
            assert tx['status']==sent['status']=='controller_completed'
            canonical,wire=wire_packet(sent)
            encoded=''.join(map(str,wire.bits))
            assert encoded==sent['wire_bits']==tx['wire_bits']==tx['transmitted_bits']
            assert ''.join(map(str,canonical.bits))==sent['canonical_bits']==tx['canonical_bits']
            assert int(tx['interleave_depth'])==int(sent['interleave_depth'])
            assert tx['codec']==sent['codec'] and tx['payload_hex']==sent['payload_hex'] and int(tx['sequence'])==int(sent['sequence'])
            assert tx['bit_ms']==int(sent['bit_ms'])==200
            assert tx['attempt_id']==session['attempt_id'] and tx['packet_id']==sent['packet_id']
            assert len(tx['slots'])==len(encoded)
            assert [s['index'] for s in tx['slots']]==list(range(len(encoded)))
            assert ''.join(str(s['bit']) for s in tx['slots'])==encoded
            assert abs(tx['scheduled_channel_seconds']-len(encoded)*.2)<1e-8
            for key in ('codec','payload_hex','payload_bytes','interleave_depth','condition'):
                assert str(sent[key])==str(expected[int(sent['sequence'])][key]),(n,key)
            slot_late.extend(s['lateness'] for s in tx['slots'])
            # Session creation precedes the user's start; use actual per-packet start.
            predicted=tx['host_started_unix']-created+1.8
            end=tx['host_started_unix']-created+tx['host_elapsed_seconds']
            assert predicted>=0 and end<=float(probe['format']['duration'])+1,(n,predicted,end)
            r=byseq.get(int(sent['sequence']))
            if r is not None:
                assert r['codec']==sent['codec'] and r['payload_bytes']==int(sent['payload_bytes'])
                offsets.append(r['preamble_start_seconds']-predicted)
                end=r['preamble_start_seconds']+(80+r['body_bits'])*.2+.4
                mask=(t>=r['preamble_start_seconds']-.4)&(t<=end)
                d=decode_pilot(t[mask],y[mask],depth=int(sent['interleave_depth']))
                truth=wire.bits[GUARD_BITS+len(PREAMBLE)+HEADER_BITS:-GUARD_BITS]
                wrong=np.flatnonzero(d['wire_body_bits']!=truth).tolist()
                assert wrong==r['error_bit_indices']
                assert bool(d.get('crc_ok',False))==r['crc_ok']
                assert (d.get('payload',b'').hex()==sent['payload_hex'])==r['exact_message']
                assert d.get('failure_stage')==r['failure_stage']
                r['scoring_basis']='Actual imported transmitter session and renderer slots; canonical/interleaved bits verified; primary decode replayed'
            checks.append(dict(sequence=int(sent['sequence']),codec=sent['codec'],depth=int(sent['interleave_depth']),
                payload_bytes=int(sent['payload_bytes']),wire_bits=len(encoded),tx_sha256=sha(tx_path),
                predicted_preamble_seconds=predicted,header_observed=r is not None))
        if offsets:
            # Capture timestamps have one-second granularity. A fixed clock offset
            # is allowed; inconsistent relative optical/host intervals are rejected.
            assert max(abs(x) for x in offsets)<1.5,(n,offsets)
            assert np.ptp(offsets)<.15,(n,'Inconsistent packet spacing',offsets)
            assert [r['sequence'] for r in a['packets']]==[int(r['sequence']) for r in session['packets']]
        else:assert n in (20,21) and len(session['packets'])==3
        association=('Original capture timestamp, CRC-valid header order, optical packet spacing and renderer slots' if offsets
            else 'Original capture timestamp, complete renderer execution within video duration and reviewed three early-glare events; no valid optical headers, so optical packet identities remain unavailable')
        a.update(attempt_id=session['attempt_id'],association=association,
            transmitter_log_path=str(path.relative_to(PROJECT)),transmitter_log_sha256=sha(path),logs_verified=True,
            expected_packets=len(session['packets']),setup_from_transmitter_log=session['setup'],
            collection_release_status=session['analysis_freeze']['status'])
        dest=output/f'Video{n}_audit.json';save(dest,a)
        matches[meta['sha256']]=dict(video=n,attempt_id=session['attempt_id'],audit=str(dest.relative_to(PROJECT)),
            session_path=str(path.relative_to(PROJECT)),session_sha256=sha(path),association=association,
            packet_checks=checks,optical_host_offsets_seconds=offsets,
            max_renderer_slot_lateness_seconds=max(slot_late),collection_release_status=session['analysis_freeze']['status'])
        timing.extend(slot_late);unchanged.append(dict(video=n,packets=len(session['packets']),observed_headers=len(before),results_unchanged=True))
        print(f'Video {n}: {len(checks)} actual transmissions verified; {len(before)} primary decodes unchanged',flush=True)
    # The ZIP also restores one older recording and supplies an exact identity
    # check for Video14; hash in the archive without replacing current videos.
    archived=[]
    with ZipFile(ROOT/'Data/physical_campaign_mac_v1.zip') as z:
        import hashlib
        for member in z.infolist():
            if not member.filename.endswith('/original.mov'):continue
            h=hashlib.sha256()
            with z.open(member) as stream:
                for b in iter(lambda:stream.read(8*1024*1024),b''):h.update(b)
            digest=h.hexdigest();assert digest in matches
            archived.append(dict(member=member.filename,sha256=digest,video=matches[digest]['video']))
    save(OUT/'omar_log_reconciliation.json',dict(zip_sha256=sha(ROOT/'Data/physical_campaign_mac_v1.zip'),
        matches_by_video_sha256=matches,archived_raw_identities=archived,results=unchanged,
        matched_transmissions=sum(x['packets'] for x in unchanged),
        renderer_slot_lateness_seconds=dict(max=max(timing),p99=float(np.percentile(timing,99))),
        caveat='Renderer timestamps are host events, not measured optical exposure or proof of lamp/block duration.',
        attempt_inventory=[dict(attempt_id=s['attempt_id'],status=s['status'],session_id=s['session_id'],
            matched_to_reviewed_video=any(x['attempt_id']==s['attempt_id'] for x in matches.values())) for _,s in sessions]))

if __name__=='__main__':main()
