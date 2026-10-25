# Selected uncoded optical-link pilot — 24 October 2026

Six original phone recordings: three labelled clean and three with moving-light interference. The frozen manifest records original capture hashes. Published movies are silent derivatives with identical encoded video and timestamps; `data/recordings_manifest.json` maps their new file hashes to the original captures. The existing receiver was rerun on the saved brightness traces, and all six outcomes matched the saved receiver records. No thresholds were tuned for this export and no expected text was supplied to the decoder.

| Condition | Message | Received text | Payload errors | Payload BER | CRC | Channel time |
|---|---|---|---:|---:|---|---:|
| clean | HELLO | HELLO | 0/40 | 0.00% | pass | 30.4 s |
| clean | RIYAADH | RIYAADH | 0/56 | 0.00% | pass | 33.6 s |
| clean | MANUNITED | MANUNITED | 0/72 | 0.00% | pass | 36.8 s |
| noisy | MANUNITED | M�^]N�TED | 4/72 | 5.56% | fail | 36.8 s |
| noisy | ADRIAN | ADR�A^ | 2/48 | 4.17% | fail | 32.0 s |
| noisy | OMAR | OMAZ | 1/32 | 3.12% | fail | 28.8 s |

## Interpretation

All three selected clean packets passed CRC and matched their sent messages. All three selected noisy packets synchronized and decoded but failed CRC. A CRC-failed packet contributes zero CRC-valid delivered payload bits to goodput. The reported bit-error rates use direct comparison with the logged transmitted bits only after independent decoding.

These are selected pilot examples, not an unbiased estimate of channel performance. Message lengths, framing, ROI and interference differ across examples. Earlier synchronization/header failures and retakes also occurred; they must not disappear from the full experimental record. Future controlled comparisons should use matched messages and conditions, record every attempt, and use unique sequence IDs.

## Files and provenance

- manifest.json links each original video to its hash, ROI, extracted trace and source log names.
- ../../analysis/pilot_2026-10-24/summary.csv contains the metrics table.
- ../../analysis/pilot_2026-10-24/traces/ contains timestamped mean brightness.
- ../../analysis/pilot_2026-10-24/transmissions/ and receivers/ contain portable copies of the relevant records; absolute machine paths and serial-device identity were omitted.
- Original conditions fields are retained. Several still say interference=none; the clean/noisy dataset classification is explicitly separate, based on the user's grouping and filenames. Distance, lighting strength and interference duration were not retrospectively invented.

The transmitter record for each trial is the latest earlier log with the expected payload. Since all packets reused sequence 1, this identifies matching transmitted bits but cannot independently prove a unique physical send/record pairing. Video-to-trace links are verified by SHA-256.

The current `Coursework.ipynb` includes these six pilot packets in the full receiver study. The silent movies are optional release downloads: restore them with `python code/tools/get_recordings.py --group pilot` before using `--from-video`. Cached-trace evaluation needs no movies. From the repository root:

```sh
.venv/bin/python code/tools/evaluate_pilot.py
```

To verify the original-or-silent provenance mapping and re-extract each trace from the movies:

```sh
.venv/bin/python code/tools/evaluate_pilot.py --from-video
```

Published movies have no audio or auxiliary tracks. The optical decoder uses the preserved video stream; original source hashes remain in the frozen manifest.
