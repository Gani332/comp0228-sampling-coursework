# Architecture and code reading order

## 1. Follow one message through the system

```text
Text -> UTF-8 bytes -> payload CRC -> error-correcting code
     -> optional body interleaving -> preamble/header/body packet
     -> Mac black/white display -> phone video
     -> timestamped brightness -> optical packet detection
     -> bit sampling -> inverse interleaving -> error correction -> payload CRC
     -> recovered bytes -> separate comparison with expected bytes for scoring
```

The receiver knows the protocol, bit duration and configured interleaving depth. It does not receive the expected payload. Detection/header failures remain failed transmissions; their missing body is not assigned zero errors.

## 2. Core implementation

Read these files in order. Each module begins with its purpose; comments near the algorithms explain timing, correction limits and failure handling.

| Order | File under `code/optical_link/` | Responsibility |
|---:|---|---|
| 1 | `protocol.py` | Bit/byte conversions, CRC, framing, repetition, Hamming and Reed–Solomon integration |
| 2 | `coding_experiments.py` | Interleaving/inverse, synthetic noise models, paired trials, success and goodput |
| 3 | `physical_campaign.py` | Validate the schedule; build actual wire packets; retain attempts and interruptions |
| 4 | `mac_campaign.py`, `screen_transmitter.py` | Display bits with deadlines and log host timing; host timestamps are not photon measurements |
| 5 | `video.py` | Read brightness using original video timestamps and fixed regions |
| 6 | `physical_campaign_receiver.py` | Current configured-duration decoder, optical acquisition and explicit failure stages |
| 7 | `campaign_frontends.py` | Frozen larger-area, reference, spatial and temporal receiver comparisons |
| 8 | `campaign_diagnostics.py` | Error runs, correction-group mappings and paired simulation intervals |
| 9 | `physical_campaign_ui.py` | Notebook controls for recording, attachment and review handover |

`receiver.py` and `receiver_layers.py` contain shared primitives and the earlier receiver implementation. The November entry points above select the configured timing and frozen processing used by the report. `_vendor/reedsolo.py` is upstream library code, not a group-authored Reed–Solomon algorithm.

## 3. Evidence to report

| Script under `code/` | Input -> output |
|---|---|
| `verify_omar_logs.py` | Imported capture logs and review traces -> verified associations and wire-bit checks |
| `analyse_campaign.py` | Audited traces, attempts and schedule -> packet outcomes, counts and manifest |
| `extract_campaign_features.py` | Raw video and audited geometry -> timestamped cached brightness features |
| `evaluate_campaign_frontends.py` | Cached features and fixed methods -> paired receiver outcomes |
| `strengthen_campaign_analysis.py` | Saved physical outcomes and simulation trials -> noise/mapping/paired diagnostics |
| `build_patch_mean_figure.py`, `build_hamming_figure.py` | Verified inputs -> explanatory report figures |
| `build_campaign_report.py` | Verified results -> numerical tables and plots, with headline-count assertions |
| `build_campaign_review.py` | Evidence -> supporting HTML review; not the final report |

The reproduction guide specifies the order and external inputs. Several historical analysis scripts use fixed study paths and can write generated outputs; run them on a working copy of the evidence, not the sole preserved archive.

## 4. Optional and historical components

- `capture.py`, `capture_cell.py`, `capture_ui.py`, `experiment.py`, `guided_retakes.py`, `receiver_study.py` and `baseline_analysis.py` support earlier physical studies. They remain available for provenance and regression coverage.
- `device.py`, `code/firmware/` and `code/vendor/LovyanGFX/` support the earlier ESP32/LCD transmitter. They are not required for Mac-screen transmission.
- `recording_provenance.py` and `code/tools/get_recordings.py` support the older published recording release. That release is not the final November dataset.
- `legacy/comparison_study/` preserves a separate collaborator implementation. Do not add its package directory to the same Python process as the final `code/` directory.

## 5. Tests and safe entry points

`code/tests/` covers correction limits, interleaving, packet acquisition, timing, receiver processing, recording association, interruption retention and provenance. Test fixtures are local to `code/tests/fixtures/`; tests do not need a hidden archive or experimental recordings.

The main notebook performs an offline walkthrough. The recording notebook starts hardware/display activity only through its explicit recording cells. Synthetic examples prove particular software behaviours; they do not substitute for the physical evidence described in the report.
