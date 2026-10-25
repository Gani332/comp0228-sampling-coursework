# COMP0228 — Optical communication coursework

Open **[Coursework.ipynb](Coursework.ipynb)** and run from top to bottom. The full analysis runs from the included measurements: **no video download or hardware connection is needed**.

```text
Coursework.ipynb   One main notebook: system, physical results and simulations
code/             Implementation, firmware, tests and tools
data/             Logs, cached measurements, analysis results and video index
report.tex        Working IEEE report draft with embedded figures/references
README.md         Setup and reproduction instructions
```

## Start here

Clone the repository (a shallow clone keeps the download compact):

```sh
git clone --depth 1 https://github.com/Gani332/comp0228-sampling-coursework.git
cd comp0228-sampling-coursework
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements.txt
.venv/bin/python -m jupyterlab Coursework.ipynb
```

Python 3.11+ is required. FFmpeg/FFprobe is needed for raw-video extraction and the generated-video test; normal notebook execution uses the included caches. The notebook is committed without outputs to keep changes small. Running it regenerates tables and displays the included plots. It verifies the stored simulation and replays a deterministic subset; the full 480,000-decoding rerun is optional.

## Evidence and labels

| Evidence | Location under `data/` | Scope |
|---|---|---|
| Pilot | `recordings/pilot_2026-10-24/`, `analysis/pilot_2026-10-24/` | Six packets/videos: three clean, three noisy |
| Repetition trials T01/T02 | `experiments/repetition_comparison/` | Two selected packets/videos: one clean, one noisy |
| Earlier batches B01–B03 | `experiments/final_capture_v1/batches/B*/` | 11 noisy packets in three videos |
| Guided retakes G01–G03 | `experiments/final_capture_v1/batches/G*/` | 11 noisy packets in three videos |
| Receiver comparison | `analysis/receiver_layers_2026-10-24/` | Five receiver variants on the same 30 physical packets |
| Coding/interleaving study | `analysis/coding_experiments_2026-10-24/` | 480,000 synthetic decoding evaluations; not physical recordings |

The [receiver manifest](data/analysis/receiver_layers_2026-10-24/manifest.json) selects the 14 videos and 30 packets used in the report, with exact paths, hashes, transmission logs, regions and time windows. Earlier attempt records are retained for provenance but are not silently added to the selected dataset. Historical logs can contain capture-machine paths; the active notebook uses relative paths and the manifest.

**Two historical label exceptions:** the noisy ADRIAN and OMAR pilot logs retain `conditions.interference: "none"` from the original capture form. Their `dataset_condition: "noisy"` and `condition_note` record the correct interpretation. Folder, manifest and analysis labels agree that these are noisy. Pilot sequence numbers were reused, so matching transmitted bits do not independently prove a unique historical send/record pairing. See the [pilot documentation](data/recordings/pilot_2026-10-24/README.md).

## Optional silent recordings

Silent videos are distributed in the [data-v1.1.0 release](https://github.com/Gani332/comp0228-sampling-coursework/releases/tag/data-v1.1.0), **outside Git**. Four ZIPs group the pilot, repetition, earlier-batch and guided-retake footage. Each is below 1 GiB; together they are about 2.2 GiB. All 14 files contain only the video track. Audio and auxiliary tracks have been removed; encoded video packets, presentation/decode timestamps, and HDR/display parameters are unchanged. No video was re-encoded.

```sh
# List optional downloads without fetching anything:
.venv/bin/python code/tools/get_recordings.py --list

# Download only the guided retakes, restoring their exact data/ paths:
.venv/bin/python code/tools/get_recordings.py --group guided-retakes

# Or restore all 14 silent videos:
.venv/bin/python code/tools/get_recordings.py

# Check restored silent videos without downloading:
.venv/bin/python code/tools/get_recordings.py --verify-only
```

The tool verifies both archive and individual-video SHA-256 hashes, skips matching files and refuses to overwrite a different existing recording. Downloads use temporary storage and the ZIP is removed after successful extraction. If you downloaded ZIPs through the browser, add `--from-dir /path/to/downloads` to restore them without another network transfer. Exact sizes and paths are in [recordings_manifest.json](data/recordings_manifest.json); the release includes `SHA256SUMS` for manual checks.

The frozen study manifests retain the original capture-container hashes. The download manifest records both `original_sha256` and the silent file's `sha256`; [audio_removal_verification.json](data/audio_removal_verification.json) records the packet/timestamp checks. Raw-video extraction verifies this mapping and records the actual input-container hash. Existing features, receiver settings and numerical results are unchanged.

Git history has been rewritten to remove the six pilot movies from all reachable commits, and the old audio-bearing release was deleted. Anyone with an earlier clone should save their own work separately and make a fresh clone instead of merging the old history. Earlier downloads may still contain audio; discard them and use the new release. The downloader deliberately refuses to overwrite old files with different hashes.

The Git tree has no videos and approximately 33 MiB of analysis data. Backups, obsolete notebooks, local environments and notebook outputs are excluded.

## Verify and reproduce

```sh
# Run all software tests, from the repository root:
cd code
../.venv/bin/python -m unittest discover -s tests -v
cd ..

# Reproduce the six pilot outcomes from cached traces:
.venv/bin/python code/tools/evaluate_pilot.py

# Verify the saved controlled simulation without repeating the full experiment:
.venv/bin/python code/tools/audit_coding_study.py --root code --study data/analysis/coding_experiments_2026-10-24
```

Fresh studies use new output directories:

```sh
.venv/bin/python code/tools/run_receiver_study.py --root code --data-root data --study data/analysis/receiver_layers_2026-10-24 --output data/analysis/receiver_new_run
.venv/bin/python code/tools/run_coding_experiments.py --root code --output data/analysis/coding_new_run
```

Receiver re-evaluation uses the tracked feature caches. To re-extract measurements from raw videos, first restore the appropriate recordings; see `code/tools/extract_receiver_features.py --help`. The saved inputs and algorithms are frozen: preserve the original study and use a new run when changing them.

The [receiver report](data/analysis/receiver_layers_2026-10-24/report.html) and [coding/interleaving report](data/analysis/coding_experiments_2026-10-24/report.html) provide detailed outputs. Download/open HTML reports locally to view them. For Overleaf, copy `report.tex` into `main.tex` and select pdfLaTeX; no external figure or bibliography files are needed. The report is a draft with author placeholders.

## Interpretation and attribution

The implementation includes uncoded transmission, repetition ×3/×5, Hamming (7,4), Reed–Solomon with four parity bytes, reference compensation, spatial processing and bit interleaving. The transmitter uses an ESP32-S3 and LAFVIN ST7796S display; the receiver uses phone-video timestamps and brightness at a baseline of 200 ms/bit.

The 30 physical packets are selected recordings from one setup. Eight informed receiver settings, and the later recordings were previously inspected. The 30/30 combined-receiver outcome is retrospective recovery of this dataset, not proof of universal reliability. Physical disturbances are not matched across codes. Simulations use declared noise models and ideal acquisition/header reception, while charging framing airtime. Failed packets remain failures; success requires an exact message and a valid CRC, and payload BER is conditional on a returned payload.

Repetition/Hamming follow the labs. The display setup was adapted from the author's earlier robot-face firmware. LovyanGFX 1.2.32 and `reedsolo` 1.7.0 retain their licences and provenance; the Reed–Solomon algorithm is credited library code. AI assistance supported implementation and drafting. Every group member must understand and justify the submitted work. Private device-restoration material is excluded; flashing helpers require the original local backup and device checks. Presentation, live demonstration and contribution forms remain separate assessment deliverables.
