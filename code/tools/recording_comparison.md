# Recording comparison runner

Use Python 3.11+ for the complete repository test suite, with dependencies from
`code/requirements.txt`. Run from the repository root:

```sh
python3 code/tools/run_batch_comparison.py --source screen --mode both
```

**The CLI default simulation is the original controlled coding study**, delegated
unchanged to `coding_experiments.run_study`. It uses seed 20261024, 2,000 uniform
random nine-byte payloads per condition, five codes and depths 1/8. The 24 settings
cover independent flips, stationary two-state Markov burst flips and force-to-one
glare bursts. Rates are 0, .01, .025, .05, .10, .20; mean burst length is 8, with
2/4/8/16 sensitivity at occupancy .05. There are 480,000 code/depth evaluations.
Acquisition and headers are assumed correct, but framing airtime is charged.
This is a controlled code experiment, independent of recording noise, payload and
camera filters. It produces no seven-filter counterfactual results.

`--mode physical` replays actual recordings with seven processing methods.
`--mode modeled` runs only the selected simulation. `--mode both` (default) does
both. In batch, the controlled simulation runs **once**, not once per recording;
its seed and payloads do not depend on the recording list. Outputs are under
`controlled_simulation/<unique-run>/` within the batch output root, alongside
per-recording physical folders. A single-recording run stores its controlled study
in `<unique-run>/controlled_simulation/`. Files include `config.json`,
`scenarios.json`, `trials.csv.gz`, `summary.csv`, `summary.json`,
`paired_outcomes.json`, `provenance.json`, and `comparison_context.json`.
Single-run `simulation_selection.json` identifies the selected backend separately
from any physical replay metadata.

Override `--trials` or `--seed` for exploratory runs. Exact report defaults are
2,000 and 20261024. A one-trial software smoke check:

```sh
python3 code/tools/run_batch_comparison.py --source screen --mode modeled --trials 1
```

The later recording-calibrated residual simulation remains an explicit option:

```sh
python3 code/tools/run_recording_comparison.py --recording G02 --mode both --simulation residual --trials 200 --seed 20261027
python3 code/tools/run_batch_comparison.py --source screen --mode both --simulation residual
```

Residual mode defaults to 200 trials and seed 20261027, and evaluates five codes,
seven processors and depths 1/8 per trial. It is an in-sample sensitivity analysis,
not controlled Markov noise or held-out physical evidence. `--random-payload`
belongs only to residual simulation, where it uses the recording's payload length.
The controlled engine always uses its original random nine-byte payload design.
The Python `comparison_runner.run` API retains its legacy residual default for
existing callers; pass `simulation='controlled'` explicitly there. Both CLIs select
controlled by default.

Historical inputs retain their frozen registry. Screen inputs require preparation;
see [screen_camera_capture.md](screen_camera_capture.md). Batch `--source` accepts
`historical` (default), `screen`, or `all`. Outputs stay under
`data/comparison/` for historical inputs and `data/screen/` for screen inputs;
`--output` overrides the base. Every run creates a fresh directory. Existing
results and historical source hashes are not rewritten.

The following sections describe **explicit residual replay** and physical scoring.
They do not describe the original controlled simulation.

## Fixed settings and model assumptions

Historical processing uses the frozen study's alpha=1 and spatial quantile=.25.
The historical API defaults remain unchanged. Temporal methods independently
filter `patch_mean`: causal EWMA tau=.025 s (one eighth of a .2 s slot), scalar
random-walk Kalman q=160000 brightness²/s, R=P0=400 brightness². These are fixed
conservative comparators with **no tuning on evaluation recordings**. Filters
reset per packet and may delay intentional transitions. Original-ROI optical
timing remains shared by every processing method; the filters do not rescue
lost acquisition.

Residual construction alone uses logged wire bits. Dark/bright levels come
from middle-half public-preamble samples, and reference regions have constant
centres. All usable packet windows contribute moving blocks, with no selection
by decoding outcome. Joint 1.6-second blocks start at each eligible source
frame and never cross packet boundaries or large frame gaps (>2.5 times the
window's median gap). Metadata records source contributions and exclusions.
Synthetic traces retain within-block frame intervals; block joins use the
median source interval with no interpolation. Every trial creates one joint
disturbance timeline long enough for the longest code. Codes/depths share its
appropriate prefix and all processors receive identical features.

Synthetic guards, preamble and header are pristine, with filters burning in on
that prefix. Modeled optical acquisition searches only this generated public
prefix, so body disturbances cannot redirect clock acquisition. Body-only disturbances isolate processing/correction; physical
replay remains end-to-end. The first recorded packet supplies the fixed payload
and sequence. `--random-payload` selects a separately labelled robustness run
using random bytes of the same length. No early stopping is used. Synthetic
features clip to [0,255]; physical features remain untouched. Instantaneous
synthetic LCD transitions plus residual source-transition artifacts do **not**
faithfully model rolling shutter or exposure. Blocks sampled with replacement
are modeled disturbances, not independent physical observations.

## Frozen source compatibility

Before extending `receiver_layers.py`, its exact bytes and original SHA-256 were
saved in `code/optical_link/comparison_provenance/`. The five historical paths
are unchanged. Compatibility tests replay every cached manifest packet with
each historical method and compare against both that snapshot and archived
receiver outputs. No stored hashes, frozen manifests, firmware, notebook results
or historical reports were rewritten.

The existing strict `run_receiver_study.py` checker correctly rejects the
extended receiver module because its whole-file hash changed. An exact frozen
rerun requires the original git revision/worktree. The new runner records its
own source hashes and does not claim frozen-source verification.

## Verification

```sh
PYTHONPATH=code .venv/bin/python -m unittest discover -s code/tests -v
```

Use `--trials 3` for a quick modeled smoke run. All 70 noiseless combinations
must pass before using modeled results. Generated artifacts live under the
`data/comparison/comparison_results/<recording>/` for single runs and
`data/comparison/batch_results/<recording>/` for batch runs, each with a new UTC
run subdirectory. On systems without a writable Matplotlib cache, set
`MPLCONFIGDIR=/tmp/comp0228-matplotlib`.
