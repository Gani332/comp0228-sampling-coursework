# Reproducing the final report

## 1. Use the code and companion evidence together

The submission separates source code from experimental evidence:

- `COMP0228_Code.zip`: implementation, tests, notebooks, report source and figure/table inputs.
- `COMP0228_Evidence.zip`: recorded brightness caches, packet outcomes, transmitter logs, simulation trials/seeds, provenance and two supporting exposure-review snapshots.
- `COMP0228_Report.pdf`: the six-page report.

Raw videos are excluded from both ZIPs. They are not needed for cached receiver replay or verification of the saved simulation. They are required to independently re-extract the original brightness measurements and assess the physical disturbances.

## 2. Verify without changing the evidence

Extract the ZIPs into sibling directories:

```text
workspace/
  project/         contents of COMP0228_Code.zip
  evidence/        contents of COMP0228_Evidence.zip, including MANIFEST.json
```

From `project/`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements.txt
.venv/bin/python code/tools/verify_submission_evidence.py --evidence ../evidence --output ../verification
```

Use a new output directory each time. The verifier reads the evidence without writing into it and:

1. Checks every packaged evidence file and the relevant scientific sources against SHA-256 hashes.
2. Recalculates physical packet totals, coding goodput and error-run counts.
3. Replays **392 receiver decodes**: seven methods on the 54 acquired main packets and two development-glare packets. It compares recovery and raw bit errors with the saved results.
4. Retains the six acquisition/header failures across the seven methods, without claiming to re-detect them or count them as independent attempts.
5. Checks all **480,000 simulation records**, rebuilds summaries and replays **720 simulated decodes**.
6. Recomputes **40 paired bootstrap intervals**, using the saved seeds and 20,000 resamples per interval.

The new output directory contains `verification.json` and regenerated physical, receiver, noise and interval summaries. The command exits with an error if a checked hash or outcome differs. Original source hashes and historical verification logs remain unchanged; they describe the frozen study rather than a new run.

The 16 clean pilot outcomes and corresponding trace hashes are checked, but the verifier does not replay pilot acquisition. Cached receiver replay uses the published baseline acquisition windows. This checks the analysis conditional on those measurements and windows; it is not an independent audit of extraction geometry, camera exposure or physical disturbance timing.

## 3. Regenerate the report's figures and tables

Use a disposable working copy. From `project/`, restore the companion data and the two review inputs at the paths used by the historical builders:

```sh
cp -R ../evidence/data/. data/
mkdir -p ../reviews
cp -R ../evidence/review_inputs/. ../reviews/
.venv/bin/python code/evaluate_campaign_frontends.py development
.venv/bin/python code/evaluate_campaign_frontends.py main
.venv/bin/python code/strengthen_campaign_analysis.py
.venv/bin/python code/build_patch_mean_figure.py
.venv/bin/python code/build_hamming_figure.py
.venv/bin/python code/build_campaign_report.py
```

These scripts write outputs into the working copy. Run `build_patch_mean_figure.py` after `strengthen_campaign_analysis.py`, which writes the earlier setup illustration. `report.tex` and `report_figures/campaign_frontends_discussion.tex` are editorially maintained; their interpretation must be reviewed if the dataset changes.

The two supplied review inputs support the exposure annotations. They do not replace the complete original video audit. Compiling the supplied report without regenerating figures needs no empirical dataset:

```sh
tectonic report.tex
# Alternatively, run pdfLaTeX twice:
pdflatex -interaction=nonstopmode -halt-on-error report.tex
pdflatex -interaction=nonstopmode -halt-on-error report.tex
```

## 4. Re-extraction and new experiments

Full video re-extraction additionally requires FFmpeg/FFprobe, the original `../Data/` videos and complete corresponding `../reviews/` audits. The evidence's historical `data/analysis/physical_campaign_2026-11-08/REPRODUCE.txt` describes that original reconstruction. Those originals are preserved locally outside the clean project in `Data/`, `reviews/` and `supporting_evidence/`; they are not part of a Git clone.

A new synthetic study needs no recordings and must use a new output directory:

```sh
.venv/bin/python code/tools/run_coding_experiments.py --root code --output data/analysis/new_simulation --trials 2000
```

The default produces 240 conditions × 2,000 trials. A smaller trial count checks execution but does not reproduce the reported experiment. More simulated trials are not more physical observations. New physical collection should use a fresh project/data directory so historical attempt logs cannot be mistaken for new transmissions.
