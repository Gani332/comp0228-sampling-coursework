# COMP0228 — Optical communication coursework

Open **[Coursework.ipynb](Coursework.ipynb)**. It is the single active notebook; Run All performs no hardware transmission.

```text
Coursework.ipynb   Source walkthrough and runnable examples
code/             Implementation, transmitter firmware, tests and tools
data/             Six previously published pilot recordings and records
README.md         Setup and scope
```

The implementation covers uncoded transmission, repetition ×3/×5, Hamming (7,4), Reed–Solomon with four parity bytes, illumination compensation, spatial receiver processing and bit interleaving. Controlled simulations compare independent flips, correlated flips and positive glare, including useful rate, decoder failures, uncertainty and analytical checks.

**Publication scope:** notebook outputs, later recordings, saved analysis studies, private archives, device backups and compiled firmware are excluded. The six pilot movies and their measurements were already public and remain included. This repository does not publish the later physical or simulation results.

## Setup and use

Python 3.11+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements.txt
.venv/bin/python -m jupyterlab Coursework.ipynb
```

Install FFmpeg/FFprobe separately for raw-video extraction and the generated-video pipeline test. Normal pilot evaluation uses cached traces.

The notebook runs protocol examples, checks the public pilot and demonstrates interleaving. Cells that require the omitted local study folders are skipped explicitly. Supplying those folders under `data/analysis/` enables their analysis; keep them untracked. The full synthetic experiment is an optional notebook action or a CLI command below.

## Verify and reproduce

```sh
cd code
../.venv/bin/python -m unittest discover -s tests -v
```

From the repository root:

```sh
.venv/bin/python code/tools/evaluate_pilot.py
.venv/bin/python code/tools/run_coding_experiments.py --root code --output data/analysis/coding_new_run
.venv/bin/python code/tools/audit_coding_study.py --root code --study data/analysis/coding_new_run
```

The synthetic study uses declared models and is not a fitted camera-channel model. Headers and synchronization are assumed correct; framing still counts toward airtime. Each new run needs a new output folder. Failed decodes remain failures; payload BER is conditional on a returned payload. A correct-delivery score requires an exact message as well as CRC validity.

## Physical channel and attribution

The transmitter is an ESP32-S3 driving a LAFVIN ST7796S display. Each bit lasts 200 ms at the baseline setting; the receiver uses phone-video timestamps and pixel brightness. Firmware source is under `code/firmware/optical_tx/`. Build helpers require the appropriate local Arduino installation; flashing requires the original device's private backup and identity checks, which are not distributed.

Repetition and Hamming conventions follow the lab. The screen setup was adapted from the author's earlier robot-face firmware. LovyanGFX 1.2.32 and `reedsolo` 1.7.0 retain their licences and provenance. The Reed–Solomon algorithm is credited library code; this project integrates and evaluates it. AI assistance was used, and the group must understand and justify all submitted work.

The [pilot documentation](data/recordings/pilot_2026-10-24/README.md) explains selection, incomplete capture conditions and log association. These six examples are not an unbiased estimate of real-channel reliability. The coursework report, presentation/live demonstration and contribution forms are separate deliverables.
