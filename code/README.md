# Code entry points

Read [the architecture guide](../docs/ARCHITECTURE.md) for the ordered transmitter → channel → receiver → analysis map.

- **Current implementation:** `optical_link/`; current camera receiver is `physical_campaign_receiver.py`, processing variants are `campaign_frontends.py`.
- **Current physical collection:** run the root `Record_Physical_Trials.ipynb`, backed by `physical_campaign.py`, `mac_campaign.py` and `physical_campaign_ui.py`.
- **Current evidence pipeline:** the root-level Python files in this directory; see [reproduction requirements and order](../docs/REPRODUCING_RESULTS.md).
- **Tests:** `tests/`, including local fixtures. Run from the project root with `PYTHONPATH=code .venv/bin/python -m unittest discover -s code/tests -v`.
- **New controlled simulation:** `tools/run_coding_experiments.py --help`.
- **Optional old hardware:** `firmware/` and `vendor/`; not required for the Mac-screen experiment. Vendor licences remain intact.

The scientific source used for the final report is preserved unchanged during repository cleanup. Documentation, notebooks and self-contained test plumbing are separate from those frozen algorithms.
