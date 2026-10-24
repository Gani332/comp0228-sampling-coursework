# Selected uncoded optical-link pilot — 24 October 2026

Six original phone recordings: three labelled clean and three with moving-light interference. Videos are copied byte-for-byte from the selected originals; hashes are recorded in manifest.json. The existing receiver was rerun on the saved brightness traces, and all six outcomes matched the saved receiver records. No thresholds were tuned for this export and no expected text was supplied to the decoder.

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

Reproduce the metrics from saved traces:

```sh
python tools/evaluate_pilot.py
```

To also verify the original video hashes and re-extract each trace from the movies:

```sh
python tools/evaluate_pilot.py --from-video
```

The original movies retain their audio and container data; the optical decoder uses only the first video stream.
