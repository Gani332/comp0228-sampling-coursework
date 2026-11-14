# Recording a new Mac-screen experiment

## 1. Prepare

Open `Record_Physical_Trials.ipynb` from the project root, or double-click `Record_Physical_Trials.command` on a Mac. Install Python 3.11+ first. The notebook contains one labelled section per planned video and starts from a fresh experiment state.

Use a fixed Mac display and a supported phone recording mode. Keep the full flashing patch and both static reference strips visible. Fix brightness, distance, orientation and room lighting; disable automatic display brightness and colour adjustments. Record camera settings honestly, including automatic exposure/focus if they cannot be locked.

Do not restore the completed campaign's attempt logs into a new collection folder. Existing completion records describe earlier transmissions, not the new run.

## 2. Work through the stages

| Stage | Videos | Packets | Action |
|---|---:|---:|---|
| Clean pilot | 1–4 | 16 | Record with no disturbance; review timing before proceeding |
| Calibration | 5–7 | 6 | Develop split blockage, clustered blockage and body glare |
| Main comparisons | 8–19 | 54 | Follow the planned messages, code order and disturbance cues |
| Acquisition challenge | 20–21 | 6 | Apply early glare during packet detection; retain failures |

The three payloads are `A7k2`, `A7k2M9q4` and `A7k2M9q4R6v8` (4, 8 and 12 bytes). Main configurations receive every length in two rounds. The schedule remains exactly the one used by the report; creating a different experiment requires a separately versioned schedule and receiver review.

## 3. Record one video

1. Run dependencies, Load recorder and Setup. Enter the actual device and capture settings.
2. Run that video's Record cell; start phone recording and press SPACE in the signal window.
3. Follow the displayed cue. A cue is a target, not a measurement of disturbance duration.
4. Stop recording when the window closes and the notebook indicates completion.
5. Transfer the original video without recompression. Use the matching session's Attach cell.
6. Retain interruptions and failures. A deliberate retake uses a new attempt (`retake=True`).

Do not Run All. After a kernel restart, rerun Load recorder and Setup to recover the new experiment's saved progress.

## 4. Review before main collection

Pilot and calibration are development data. Verify acquisition, bit timing and noise effects before freezing settings for the main comparison. Main/challenge transmission checks for the documented `analysis_freeze.json`; the clean repository deliberately does not ship an approval for new hardware or a new collection.

The original report used a configured 200 ms bit duration and optical preamble acquisition. Do not choose timing, regions or interleaving depth by trying alternatives until the expected message appears. Expected text belongs only in scoring after decoding.

## 5. Preserve the evidence

New logs and recordings are written under ignored `data/physical_campaign_mac_v1/`. They contain setup, sequence IDs, exact transmitted bits, interleaving depth, host display times, cues and video associations. Host timing does not directly measure light emission or camera exposure. A completed transmitter status does not imply successful reception.

Keep original videos, attempt logs and the schedule together outside the code submission. Never remove failed packets simply because they weaken a result.
