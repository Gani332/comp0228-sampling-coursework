# Reproducing the final report

## 1. What the clean source package can do by itself

The tests, main notebook's synthetic demonstrations, experiment schedule, fresh recording workflow and report compilation work without the original experimental dataset. The package intentionally excludes recordings, feature arrays, transmitter logs and saved simulation trials.

The report's retained figures and tables are presentation artifacts. They are not a replacement for the raw and intermediate evidence needed to regenerate them.

## 2. Where the original evidence is preserved

In the group's local coursework directory, cleanup moved the original `optical_link/data/` to `../supporting_evidence/data/`. Historical backups and the old Git checkout are under `../supporting_evidence/workspace_archive/`. The original November videos remain in `../Data/`, and the collection reviews remain in `../reviews/`.

These are local paths, not files available from a Git clone. Anyone reproducing empirical results needs a separately transferred evidence package from the group. Do not claim that cloning this repository supplies those results.

| Input under the restored `data/` | Use |
|---|---|
| `plans/physical_campaign_v1/` | Frozen schedule; already included with source |
| `physical_campaign_mac_v1/` | Setup, attempts, transmitted bits and analysis freeze |
| `imports/omar_2026-11-08/` | Reconciled remote transmitter logs |
| `analysis/physical_campaign_2026-11-08/` | Selected packet outcomes, caches, traces, diagnostics and provenance |
| `analysis/coding_experiments_2026-10-24/` | Saved 480,000-trial controlled simulation and seeds |

Keep the preserved evidence unchanged. For replay, make a separate working copy of this project and copy the corresponding evidence directories into its `data/` folder. Preserve the dataset's original relative paths and hashes. If starting from the local preserved full dataset, copy its contents into that working copy; this also includes older evidence and may take several gigabytes.

## 3. Replay from cached measurements

From the working copy's project root, after restoring the data and installing requirements:

```sh
.venv/bin/python code/evaluate_campaign_frontends.py development
.venv/bin/python code/evaluate_campaign_frontends.py main
.venv/bin/python code/strengthen_campaign_analysis.py
.venv/bin/python code/build_patch_mean_figure.py
.venv/bin/python code/build_hamming_figure.py
.venv/bin/python code/build_campaign_report.py
```

Run the patch-mean figure builder **after** `strengthen_campaign_analysis.py`, which otherwise writes the earlier setup figure. The figure builders write into `report_figures/`. Prose in `report.tex` and `campaign_frontends_discussion.tex` is maintained separately and must be reviewed if numerical inputs change.

To verify the saved controlled simulation without rerunning all trials:

```sh
PYTHONPATH=code .venv/bin/python -c "from pathlib import Path; from optical_link.coding_experiments import load_verified; print(load_verified(Path('code'), Path('data/analysis/coding_experiments_2026-10-24'))[2])"
```

## 4. Re-extract from recordings or run a new simulation

Fresh video extraction additionally needs FFmpeg/FFprobe, the original `../Data/` videos and the corresponding `../reviews/` audits at their original relative locations. See the preserved dataset's `analysis/physical_campaign_2026-11-08/REPRODUCE.txt` for reconciliation and extraction order. This path-dependent historical reconstruction is distinct from cached replay.

A new synthetic study does not require recordings. It must use a new output directory:

```sh
.venv/bin/python code/tools/run_coding_experiments.py --root code --output data/analysis/new_simulation --trials 2000
```

The default produces 240 conditions × 2,000 trials. A smaller trial count is useful for checking execution, but its results are not the reported experiment. Never overwrite the frozen trial records or describe synthetic trials as new physical data.

## 5. Build the report

```sh
tectonic report.tex
# Alternatively, with a LaTeX installation:
pdflatex -interaction=nonstopmode -halt-on-error report.tex
pdflatex -interaction=nonstopmode -halt-on-error report.tex
```

The supplied PDF and Overleaf bundle were checked as six pages. No empirical data is needed for compilation because all required figure/table inputs are included.
