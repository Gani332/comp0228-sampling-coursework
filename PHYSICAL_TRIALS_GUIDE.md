# Record the reduced LCD-to-phone experiment

Open `Record_Physical_Trials.command` to launch `Record_Physical_Trials.ipynb`, or open the notebook directly in Jupyter. Use the original LCD-to-phone setup.

The plan contains **82 transmissions in 21 videos**, about **83 minutes of footage** including programmed gaps. Setup, transfers, pauses and retakes are additional. These are planned recordings, not completed results.

## What to do

1. Connect the LCD by USB. Fix the phone on a stand, showing the complete flashing patch and its static surroundings. Keep resolution, orientation, distance and lighting steady. Lock exposure/focus if available; otherwise record that they are automatic.
2. Run the notebook's load and setup cells once. Enter device/settings, distance and operator. Do not use Run All.
3. Work through **Videos 01–04 only** first. Run a Record cell, start one phone video, then press Enter. Leave the camera recording through every packet and gap; stop at the green STOP message. No disturbances in these four videos.
4. Transfer the original files without recompression. Use the Attach cell beneath the matching recording section. Run Handover and provide its output plus the local original-video paths for review.
5. After the clean pilot has been checked, record the three calibration sections. Follow the displayed card/lamp cues. Attach those originals and pause for noise review.
6. After timing, noise and receiver settings have been reviewed and frozen, work through the main and challenge sections. Code choice, message, packet order and interleaving are automatic. No separate recordings are needed for filters.

## Recording checklist

| Stage | Videos | Packets | Approx. footage | Your action / purpose |
|---|---:|---:|---:|---|
| Clean timing pilot | 4 | 16 | 23 min | Keep steady; short/long messages, uncoded/repeat5 and interleaving off/on expose timing problems. |
| Noise calibration | 3 | 6 | 4 min | Three short card blocks, one longer card block, then glare; each clip has uncoded and Hamming packets. Development data only. |
| Code and interleaving comparisons | 6 | 42 | 40 min | One card block per packet. Five non-interleaved codes plus interleaved Hamming/RS, randomized within each video. |
| Glare / receiver-processing comparisons | 6 | 12 | 9 min | One glare pulse per packet. Uncoded and Hamming; apply processing methods offline to the same footage. |
| Acquisition challenges | 2 | 6 | 6 min | Early glare during the preamble; uncoded, Hamming and RS. Keep every failure. |

Main card and glare videos are interspersed by message block, not collected as two separate long runs. The notebook lists their exact order and individual timings. Totals above are rounded.

Messages include RIYAADH, ADRIAN, OMAR, LARA, MANUNITED and PLEASEWORK in the six main blocks, plus CANIGETAFIRSTPLS and UCLISGREATSY in development/challenge recordings. No padding is added. Message content and length vary between blocks, not between configurations within a block.

## Disturbance setup

Use a card close to the LCD, covering the flashing patch rather than the whole camera lens. Keep its edge or a reference marker visible so actual onset/duration can be annotated. Follow BLOCK / CLEAR cues; do not count seconds yourself. Calibration includes three target 0.4-second blocks; main occlusion uses one target 1.2-second block.

For glare, fix the lamp at a marked position. Cover its beam initially, uncover at the cue, then cover again. Do not wave the lamp. Record lamp position, setting and any changes with `recorder.setup(...)` or the session's note line. Cue durations are targets, not measurements of what physically happened.

If calibration shows that a disturbance is impractical, ineffective or overwhelming, stop before main collection. We will preserve the development recordings and create a versioned continuation plan. Do not change the existing manifest once attempts exist.

## What is saved and how to recover

Every attempt gets a fresh directory under `data/physical_campaign_v1/attempts/`, with actual transmitted bits, codec/interleaving settings, sequence IDs, plan/source hashes, timing/cue logs and setup metadata. The Attach cell copies the selected original video and verifies its hash. It is tied to that section's session, not the last cell run. Video contents and optical association still need analysis verification.

Rerunning a completed Record cell displays the saved attempt without sending again. Interrupted attempts are preserved. An intentional retake uses the documented `retake=True` recovery example and retains both attempts. Never retry until success and discard the failures. If multiple attempts exist, select their matching attempt IDs explicitly when attaching files.

The Handover cell lists completed controller runs and missing originals. Controller completion is not successful optical decoding. Text output alone is insufficient for analysis: keep the videos and all attempt logs. Keep originals on the phone until copies/backups are verified.

## Analysis commitments

- Pilot and calibration are development evidence. Main/challenge transmission requires a documented `analysis_freeze.json` matching the plan hash, real pilot review and receiver settings; this is prepared after reviewing the physical footage, not bypassed now.
- Main comparisons have six message blocks. This supports scoped comparisons with uncertainty, not precise reliability claims. Acquisitions, headers and CRC failures remain outcomes.
- Interleaving-off controls are shared between code and interleaving analyses; reuse does not create independent samples. Filters use identical videos. Synthetic repetitions are not physical replications.
- Rotating sequence IDs avoid fixed ID/configuration associations but are not perfectly balanced across six blocks. CRC bits can differ between paired packets.
- The main protocol uses a fixed disturbance duration per message; longer codes therefore have a different disturbed fraction. Report useful throughput, redundancy and failures alongside errors and recovery counts.
- The held-out preamble challenge tests acquisition with frozen settings. It is not a broad validation across hardware or environments. Do not tune on its results.
- Full-video registration and receiver analysis follow the pilot. The recording notebook collects evidence; it does not yet certify decoding quality or automatically analyse every video.

The schedule generator is `code/tools/build_reduced_recording_schedule.py`; the notebook generator is `code/tools/build_recording_notebook.py`. The active schedule is `data/plans/physical_campaign_v1/schedule.csv`. Earlier local notebook versions were backed up in the author’s workspace; those backups are not required to run this branch. No Git merge is part of this change.

## Standard messages and fixed comparison counts

Each main message — RIYAADH, ADRIAN, OMAR, LARA, MANUNITED and PLEASEWORK — has exactly **nine transmissions across two videos**: seven with card occlusion and two with glare. Every relevant configuration receives all six messages. The notebook now includes a comparison matrix, a message-block table linking both videos, and messages in its recording checklist.

The seven card transmissions comprise five non-interleaved codes plus interleaved Hamming and RS. The two glare transmissions are uncoded and Hamming. Filters process the same recordings afterwards. The main study therefore has 54 transmissions; pilot, calibration and held-out challenges bring the whole plan to 82. There is no additional footage requirement for this presentation change.
