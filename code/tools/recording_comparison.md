# Recording comparison runner

Use Python 3.11+ for the full repository test suite, with dependencies from
`code/requirements.txt` in a local environment. The comparison runner itself also
works with Python 3.9. Run from the repository root:

```sh
.venv/bin/python code/tools/run_recording_comparison.py --recording G02 --mode both --trials 200 --seed 20261027
```

The script can also be invoked by absolute path from any working directory.

The default recording is **G02** (four retrospective packets). Physical mode
exports seven receiver-processing outcomes per packet, using the actual
transmitted codec and no interleaving. Modeled mode exports 70 configurations
per trial: five codecs, seven processors and depths 1/8. These counterfactual
results are an **in-sample sensitivity analysis**, not 70 real transmissions or
held-out camera validation. CRC is always present and success requires both
valid CRC and an exact payload match.

Only registered recordings with verified feature caches, archived timestamps,
ROI metadata and transmitter logs are supported. No movies, network downloads
or hardware are needed. `--recording` accepts a manifest ID or an exact unique
known basename; generic `recording.mov` is ambiguous. New movies require their
own manifest entry, windows, geometry, matching ground-truth logs and cache.
Original manifest video hashes are retained even where the archived movie has
been replaced with its known silent container; no replacement hash is invented.

`--mode physical`, `--mode modeled`, or `--mode both` (default) selects outputs.
`--output` changes the output base; relative paths resolve from the repository
root. Every run creates a fresh UTC timestamped child directory. Existing
results are never overwritten. By default the base is
`data/comparison/comparison_results/G02/`. Filenames identify the recording:

- `G02__physical_results.csv`, `G02__physical_comparison.png`
- `G02__modeled_trials.csv`, `G02__modeled_summary.csv`, `G02__modeled_comparison.png`
- `G02__run_metadata.json`

CSV uses UTF-8, `True`/`False` booleans and empty cells for unknown values.
Returned payload hex is retained alongside replacement-decoded UTF-8 text.
Unknown BER is empty; failed receptions contribute airtime and zero delivered
bits. Airtime includes guards, preamble, header, CRC and code redundancy.
Processing runtime is separate. Summary rows contain Wilson intervals and
paired bootstrap success differences against `patch_mean` for matching trials,
code and depth. These intervals describe model randomness, not physical
recording independence. A small trial count is a software smoke test only.

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
