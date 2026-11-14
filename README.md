# COMP0228: screen-to-camera optical communication

Text is encoded into black/white flashes on a Mac display. A phone records the flashes; the receiver locates each packet, reads its bits, reverses any interleaving and applies error correction. The final study investigates glare, blockage, receiver processing and coding trade-offs.

## 1. Choose your starting point

| Goal | Start here | Requires recorded data? |
|---|---|---|
| Read the final findings | [report.pdf](report.pdf) | No |
| Understand and exercise the implementation | [Coursework.ipynb](Coursework.ipynb) | No; synthetic examples are explicitly labelled |
| Record a new physical experiment | [Record_Physical_Trials.ipynb](Record_Physical_Trials.ipynb), then [recording guide](docs/RECORDING_GUIDE.md) | No existing recordings; Mac display and phone required |
| Understand the code | [architecture and reading order](docs/ARCHITECTURE.md) | No |
| Run software checks | Commands below | No recordings or historical archive |
| Reproduce the reported results | [reproduction guide](docs/REPRODUCING_RESULTS.md) | Yes: separately supplied evidence |
| Edit the report | [report.tex](report.tex) and [report_figures/](report_figures/) | No, unless regenerating figures |

## 2. Install and verify

Use Python 3.11 or later. Run commands from this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements.txt
PYTHONPATH=code .venv/bin/python -m unittest discover -s code/tests -v
.venv/bin/python -m jupyterlab Coursework.ipynb
```

FFmpeg and FFprobe must be on PATH for raw-video extraction and the generated-video regression test. The other tests use synthetic traces, temporary files and mocked devices. No test starts a real transmitter. The recording workflow additionally needs:

```sh
.venv/bin/python -m pip install -r code/requirements-screen-camera.txt
.venv/bin/python -m jupyterlab Record_Physical_Trials.ipynb
```

On a Mac, `Record_Physical_Trials.command` performs dependency setup and opens the recording notebook. Follow its cells individually; do **not** Run All in a recording notebook.

## 3. Project layout

```text
README.md                       Start here
Coursework.ipynb                 Offline explanation and synthetic examples
Record_Physical_Trials.ipynb     Fresh, numbered physical recording workflow
Record_Physical_Trials.command   Mac launcher
code/
  optical_link/                 Packet format, codecs, transmitter and receivers
  tests/                        Offline tests and explicit test fixtures
  tools/                        Recording-plan and simulation command-line tools
  *_campaign*.py                November evidence extraction/analysis/report tools
  firmware/, vendor/            Optional earlier ESP32/LCD implementation and licences
data/plans/                     Small, fixed experimental configuration only
  physical_campaign_v1/         21 sessions / 82 planned transmissions
report.tex, report.pdf           Final report source and rendered PDF
report_figures/                  Required report figures and numerical table inputs
docs/                           Architecture, recording and reproduction guides
legacy/comparison_study/         Preserved collaborator comparison implementation
COMP0228_Report_Overleaf.zip     Complete report-source upload bundle
```

Recorded datasets, generated analysis, notebook outputs, environments, caches and historical backups are excluded from Git and the submission ZIP. The small schedule in `data/plans/` is **configuration**, not measured results; it is required by the recorder and tests. Nothing in the clean project silently downloads recordings.

## 4. How the final evidence is organised

The report uses the **November campaign**, not the older 30-packet October study:

| Stage | Physical transmissions | Purpose |
|---|---:|---|
| Clean pilot | 16 | Establish timing and clean decoding |
| Disturbance calibration | 6 | Develop the disturbance and receiver settings |
| Main blockage | 42 | Five codes plus two interleaved configurations, three lengths, two rounds |
| Main body glare | 12 | Uncoded/Hamming, three lengths, two rounds |
| Early-glare acquisition challenge | 6 | Retain failures before body correction |
| **Total across 21 videos** | **82** | Reprocessing does not add independent transmissions |

The separate controlled study contains 480,000 simulated decodes. They test mechanisms under declared noise models; they are not extra physical observations. Receiver methods use identical recorded frames. Physical transmissions under different codes experienced different manual disturbances, so they do not establish a controlled causal ranking.

## 5. Report, evidence and attribution

The PDF is six pages including references. Upload `COMP0228_Report_Overleaf.zip` to Overleaf, or compile `report.tex` using Tectonic or pdfLaTeX (twice). Keep `report_figures/` beside the source. The report and interpretive discussion are edited by hand; numerical builders do not regenerate the prose.

Read [reproduction instructions](docs/REPRODUCING_RESULTS.md) before running analysis: the source-only repository cannot reproduce empirical results without the evidence package. A new recording run must not overwrite the frozen study.

Repetition and Hamming follow the module's coding conventions. Reed–Solomon uses the credited, vendored `reedsolo` 1.7.0 implementation; see its [provenance and licence](code/optical_link/_vendor/README.txt). The optional LCD firmware uses [LovyanGFX](code/vendor/LovyanGFX/license.txt). Retain third-party copyright notices. AI assistance is acknowledged in the report.

The [historical comparison snapshot](legacy/comparison_study/README.md) preserves collaborators' earlier work separately, including its original receiver variant. It is not the implementation used to produce the final November report. The presentation, brief live demonstration, code submission and individual contribution forms remain separate deliverables.
