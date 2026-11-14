"""Human-readable analysis, rubric mapping and reproducibility handover."""
from pathlib import Path
import html,json
import pandas as pd
from analyse_campaign import PROJECT,OUT,ROOT,read,save,sha

test_count=read(OUT/'report_validation.json')['tests_passed']
f=pd.DataFrame(read(OUT/'main_frontends.json'))
main=f[f.phase=='main'];block=main[main.condition=='OCC_CLUSTER']
grid=block.pivot_table(index='method',columns=['codec','depth'],values='success',aggfunc='sum')
grid=grid.reindex(['original','patch_mean','reference','spatial','combined','ewma','kalman'])
grid.columns=[f'{c}, depth {d}' for c,d in grid.columns]
grid=grid.map(lambda x:f'{int(x)}/6')
summary=pd.DataFrame(read(OUT/'summary.json')['by_condition_code'])
summary=summary[summary.phase=='main'][['condition','codec','depth','successes','packets','errors','observed_body_bits','goodput_bps']]
summary.goodput_bps=summary.goodput_bps.round(3)
front=pd.DataFrame(read(OUT/'main_frontends_summary.json'))
front=front[front.phase=='main'][['condition','method','successes','packets','errors','goodput_bps']]
front.goodput_bps=front.goodput_bps.round(3)

questions=[
 ['1. Observe the physical link','Where does it fail, and what errors occur?','16 pilot + 6 calibration + 54 main + 6 logged acquisition-stress transmissions','Timestamped brightness; error direction/runs; failure stage','Week 1 sampling/measurement; Week 2 communication channel','Glare: 18/18 errors are 0→1. Blockage is bidirectional. Six stress packets never acquire a valid header.'],
 ['2. Compare correction and cost','Which code protects these messages efficiently?','42 blockage packets; 12 body-glare packets','Exact+CRC, conditional BER, framing-inclusive goodput','Week 2 repetition, Hamming, redundancy; researched Reed–Solomon','RS depth 1: 6/6 blockage recovery, 1.538 bit/s. Ranking is descriptive because exposures differ.'],
 ['3. Improve the measurement','Do processing methods improve the identical received signal?','Seven receiver methods replayed on the same 54 main packets; shared failure on 6 stress packets','Larger-ROI control; paired rescues AND harms; code-level breakdown','Week 1 averaging/filter assumptions; robotics estimation','Larger mean alone rescues all four body-glare failures. No added filter advantage there. Reference/combined: 33/42 blockage, with reference validity caveats.'],
 ['4. Redistribute errors','Does interleaving help each correction unit?','Reuse Hamming/RS depth-1 controls; six packets each at depth 8; controlled simulation','Errors per codeword/byte, paired model trials, goodput','Week 2 coding; Weeks 2–3 probability and limitations of pooled entropy/BER','Hamming 4/6→6/6; RS 6/6→2/6. RS failures exceed the two-byte correction budget.']]
rubric=[
 ['Physical noisy channel','Strong evidence','21 current videos fingerprinted; real screen-to-camera link; retained failures','The channel works, but six preamble-stress attempts fail before body decoding.'],
 ['Correct core codes','Strong evidence','Repetition 3/5, Hamming(7,4), RS4; unit tests and end-to-end replay',f'{test_count} tests pass. Tests support correctness, not a proof of zero bugs.'],
 ['Organised, justified experiments','Structured with material limits','Fixed length/message blocks, two rounds, stage separation, larger-ROI control, preserved retake sensitivity','Manual exposures vary; setup/content confounds remain. Do not describe the physical code comparison as fully controlled.'],
 ['Automation and replicability','Transmitter logs reconciled','Hashes, actual PTS, saved configurations, reproducible feature/packet tables and generated figures','Omar’s imported session/renderer logs verify the previously provisional settings. Acquisition-stress association uses capture time; no valid optical headers are available.'],
 ['Professional statistics and presentation','Strong evidence','Counts, individual packet outcomes, conditional BER, goodput, model-only confidence intervals','No pseudoreplication: 2,000 synthetic trials do not become 2,000 physical recordings.'],
 ['High-standard extensions and insight','Substantive analysis','Seven-method ablation; physical interleaving plus 480,000 controlled trials; correction-unit explanation','Do not claim a new coding algorithm, universal filter superiority or a published research breakthrough.'],
 ['Self-critical conclusions','Explicitly addressed','35/54 selected vs 30/54 earliest completed sensitivity; reference occlusion; acquisition failures','Report uncertainty as part of the finding rather than hiding weak trials.'],
 ['Module and wider context','Addressed','Weeks 1–3, Lab 2, Hamming/Reed–Solomon/Gilbert/Kalman and PixNet references','The report explains relevant concepts instead of adding unrelated advanced methods.'],
 ['Professional delivery and individual understanding','Still requires the group','Six-page report draft, source, analysis and Overleaf bundle prepared','Each author must review/explain it; live presentation/demo, contribution forms and interviews remain separate deliverables.']]
def table(rows,cols):return pd.DataFrame(rows,columns=cols).to_html(index=False,escape=True,border=0)
body='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>COMP0228 — analysis and marking review</title><style>
body{font:16px/1.55 system-ui,sans-serif;color:#182a36;background:#f4f7f9;margin:0}main{max-width:1250px;margin:auto;background:white;padding:38px}h1{font-size:30px;line-height:1.2}h2{font-size:23px;margin-top:35px}p{max-width:1000px}.note{border-left:5px solid #b4781d;background:#fff6e5;padding:14px 20px}.result{border-left:5px solid #208465;background:#edf7f1;padding:14px 20px}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}th{background:#153c53;color:white;text-align:left;padding:10px}td{vertical-align:top;border-bottom:1px solid #dce3e8;padding:10px}tr:nth-child(even) td{background:#f5f8fa}a{color:#075e91}code{background:#f2f4f7;padding:2px 4px}.scroll{overflow-x:auto}small{color:#526674}@media print{main{padding:0}body{background:white}table{font-size:10px}tr{break-inside:avoid}h2{break-after:avoid}}</style><main>
<p><small>COMP0228 · 8 November 2026 · Current Mac-screen campaign</small></p>
<h1>Analysis completed; a six-page evidence-led report draft</h1>
<p><a href="report.pdf">Open the report PDF</a> · <a href="report.tex">LaTeX source</a> · <a href="COMP0228_Report_Overleaf.zip">Overleaf bundle</a> · <a href="data/analysis/physical_campaign_2026-11-08/packets.csv">Primary packet data</a></p>
<div class="note"><strong>Submission status:</strong> the available recordings and receiver comparisons are analysed. Omar’s transmitter logs have now been matched and checked; the numerical findings are unchanged. Group review remains before submission. The 90–100 rubric is the target, not a guaranteed assessment. The draft is not a claim that all experimental weaknesses have disappeared.</div>
<h2>What the evidence actually says</h2><div class="result">
<ul><li><strong>Physical baseline:</strong> 35/54 selected main packets recover exactly; all 54 acquire. Six additional acquisition-stress attempts yield no valid headers.</li>
<li><strong>Interleaving depends on the code:</strong> Hamming 4/6 → 6/6; Reed–Solomon 6/6 → 2/6 under blockage. The RS failures affect too many byte symbols.</li>
<li><strong>The simple control matters:</strong> a larger patch average already changes glare recovery from 8/12 to 12/12. More elaborate filters add no recovery on that subset.</li>
<li><strong>Blockage remains difficult:</strong> reference/combined processing gives 33/42, compared with 27/42 centrally. Covered references limit the causal explanation.</li>
<li><strong>Retakes change the result:</strong> earliest available completed versions give 30/54; replacements give 35/54. Neither is an independent random reliability sample.</li></ul></div>
<h2>Four distinct analysis questions</h2>'''
body+=table(questions,['Question','Purpose','Evidence','Measurement','Teaching connection','Finding'])
body+='<p>The four questions organise the argument; they do not create four independent datasets. Receiver methods reuse identical recordings, and interleaving reuses existing depth-1 controls. Counts are never added as new physical trials.</p><h2>Strict review against the 90–100 descriptors</h2>'
body+=table(rubric,['Criterion','Assessment','Evidence in this revision','Boundary / remaining action'])
body+='<p>Sources: <a href="../COMP0228_CW1_markingScheme.pdf">actual marking scheme</a> and <a href="../COMP0228_coursework1.pdf">coursework brief</a>. The brief requires a 4–6-page PDF, code, contribution forms and a live presentation/demo; each person must be able to explain the work.</p><h2>Physical code results</h2><div class="scroll">'+summary.to_html(index=False,border=0)+'</div>'
body+='<p>Every code/depth cell has six main blockage observations. Glare contains only uncoded and Hamming at depth one. BER denominators include only acquired bodies; acquisition failures never receive an invented zero BER. Goodput charges failed packets and framing, but excludes user setup, interpacket gaps and offline decoding.</p><h2>Receiver × code: all blockage comparisons</h2><div class="scroll">'+grid.to_html(border=0)+'</div>'
body+='<p>Each cell is exact+CRC success out of the same six packets for that code. For example, enlarging the ROI improves the aggregate but reduces ordinary Hamming from 4/6 to 3/6. Combined processing reaches 5/6. This is why aggregate success is insufficient.</p><h2>Receiver totals, with raw errors and useful rate</h2><div class="scroll">'+front.to_html(index=False,border=0)+'</div>'
body+='''<h2>What changed in the report, section by section</h2>'''
body+=table([
 ['Abstract + introduction','Lead with measured findings and four research questions; replace stale 30-packet-only narrative.'],
 ['System + correctness','Describe the Mac transmitter, iPhone setups, configured timing, frame timestamps, coding and deinterleaving order.'],
 ['Experimental design','State the 82-attempt stage structure, payload controls, exact success/BER/goodput definitions, retakes and provenance.'],
 ['Physical results','Show individual outcomes, error direction, correction-group limits and recovery–airtime trade-offs.'],
 ['Receiver extension','Add the support-size control, paired rescues/harms and filters with/without each code.'],
 ['Interleaving + simulation','Connect physical symbol errors to model results; separate Monte Carlo uncertainty from physical diversity.'],
 ['Evaluation + conclusion','State what generalises, the limits of inference and how this relates to sampling, coding and estimation.']
 ],['Section','Revision'])
body+='''<h2>Exactly what is still needed</h2>
<ol>
<li><strong>Group review:</strong> confirm author names, explain each method and check that the stated setup matches what was used. Missing settings should remain unknown, not guessed.</li>
<li><strong>Presentation and contribution deliverables:</strong> prepare and rehearse the live demo; complete individual contribution forms. These are not replaced by the report.</li></ol>
<p>No new recordings are requested for this analysis. The log-verification gap is closed. Manual exposure variation and the parallel collection procedure remain documented limitations.</p>
<h2>Omar’s log verification</h2><p>The archive contains 15 attempts: 11 match the reviewed Videos 11–21, including three earlier recordings subsequently replaced; four are additional attempts. Across the matched recordings, 49 transmissions were checked, including 43 acquired packets whose decodes are unchanged and six acquisition failures. The current cohort gains actual-log verification for 28 previously provisional transmissions. The original videos and local recording folders were not overwritten.</p><p>His setup log identifies an iPhone 15 Pro, approximately 30 cm from a MacBook Air, using a fixed-position second-phone flashlight for glare. The release file was explicitly a placeholder for parallel collection; these recordings were not released by a local pilot review. This does not change the fixed analysis settings or numerical outcomes.</p><p><a href="data/analysis/physical_campaign_2026-11-08/omar_log_reconciliation.json">Full reconciliation record</a></p><h2>Reproducibility</h2><p>All 21 current video hashes were checked. The primary timing source and plan remain fixed. The current suite passes 120 tests. The saved simulation summaries were recomputed from 480,000 records and 720 decodes replayed. The new front ends pass clean-code/depth checks and reproduce the frozen primary outcomes exactly.</p>
<p><a href="data/analysis/physical_campaign_2026-11-08/REPRODUCE.txt">Commands and file guide</a> · <a href="data/analysis/physical_campaign_2026-11-08/manifest.json">Recording manifest</a> · <a href="data/analysis/physical_campaign_2026-11-08/report_validation.json">Numerical checks</a></p>
</main></html>'''
details = """<h2>Four evidence improvements added after the strict review</h2>
<table><thead><tr><th>Improvement</th><th>Evidence now shown</th><th>Interpretation boundary</th></tr></thead><tbody>
<tr><td>Annotated setup</td><td><a href="report_figures/campaign_setup.pdf">Actual camera frame with central ROI, enlarged patch tiles and reference regions.</a></td><td>Uses the existing geometry; no receiver retuning.</td></tr>
<tr><td>Worked interleaving example</td><td>Video 19: Hamming wire errors 50,52 map to coded bits 42,78 in words 6,11. RS errors 43,44,45,47 map to bits 47,61,75,103 in bytes 5,7,9,12.</td><td>Actual inverse mapping within each packet. The two packets had separate physical disturbances.</td></tr>
<tr><td>Full error-run distribution</td><td><a href="report_figures/campaign_noise.pdf">51 blockage runs and 10 glare runs.</a> Multi-bit runs contain 44/78 blockage errors and 14/18 glare errors.</td><td>Run lengths are descriptive; error-free packets remain in success denominators. Runs are not physical exposure durations.</td></tr>
<tr><td>Interleaving across burst lengths</td><td><a href="report_figures/campaign_simulation.pdf">Paired depth-8 minus depth-1 recovery curves.</a> Hamming gains 39.0 percentage points at L=4 under correlated flips, compared with 11.7 at L=16. RS remains worse throughout the tested range.</td><td>Fixed 5% bad-state occupancy. Increasing burst length also reduces arrival frequency. Pointwise paired bootstrap intervals quantify model uncertainty only.</td></tr>
</tbody></table>
<p><strong>Physical exposure evidence:</strong> existing visual brackets put Video 8's two glare durations at 0.8–1.6 s and 1.8–2.2 s against a 1.2 s target. The second clearly exceeds the target. These are bounded visual estimates, not confidence intervals or a complete exposure survey. A reviewed Video 19 blockage frame also covers the black reference strip.</p>
<p><a href="data/analysis/physical_campaign_2026-11-08/diagnostics/interleaving_duration_paired.csv">Paired simulation results</a> · <a href="data/analysis/physical_campaign_2026-11-08/diagnostics/physical_noise_structure.json">Noise statistics</a> · <a href="data/analysis/physical_campaign_2026-11-08/diagnostics/exposure_annotations.json">Exposure annotations and scope</a></p>
<p>These additions strengthen the evidence and explanation. They do not remove unequal physical disturbances, small grouped samples or setup/content confounding. Group review, live demonstration and individual understanding remain essential to the assessment.</p>
"""
body=body.replace('<h2>Four distinct analysis questions</h2>', details+'<h2>Four distinct analysis questions</h2>')
body=body.replace('The current suite passes 120 tests.',f'The current suite passes {test_count} tests.')
(PROJECT/'Analysis_and_marking_review.html').write_text(body)
save(OUT/'rubric_mapping.json',[dict(zip(['criterion','assessment','evidence','boundary'],r)) for r in rubric])
print('Analysis_and_marking_review.html generated')
