# COMP0228 Sampling Coursework

Optical communication coursework for **Sampling, Compression and Data Analysis** at UCL.

The current prototype sends a message through a flashing LCD patch, records it with a phone camera, and reconstructs the message from the video. It supports an uncoded baseline, repetition coding (3 and 5 repetitions), Hamming(7,4), and byte-symbol Reed–Solomon with four parity bytes.

```text
Message → packet + optional error correction → ESP32/LCD flashes
                                                      ↓
Recovered message ← independent video decoder ← phone recording
```

## Start with the notebook

Open **[Optical_Link_Guided.ipynb](Optical_Link_Guided.ipynb)** and work through it from top to bottom:

1. Check the controller and display.
2. Encode a short message such as `HI`.
3. Record the transmission with a phone.
4. Select the flashing patch in the video and recover the bits.
5. Compare the independently received bits with the saved transmission log.

Hardware actions default to disabled. The initial software demonstration uses synthetic data and is labelled accordingly. The six explicitly shared pilot recordings are included in `recordings/pilot_2026-10-24/`. New recordings and per-attempt outputs remain local unless deliberately added to Git.

### Python setup

Use Python 3.11 or a compatible Python environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m jupyterlab Optical_Link_Guided.ipynb
```

Install **FFmpeg/FFprobe** separately and make `ffprobe` available on your PATH. On macOS, the included `Open Optical Link.command` launcher uses this project's `.venv`, or the existing Week 2 Lab 2 environment when present.

## Remaining physical recordings

Open **[Final_Recordings.ipynb](Final_Recordings.ipynb)**, or double-click `Open Final Recordings.command` on the original Mac. The notebook has three plain recording cells: MANUNITED, ADRIAN and OMAR. Run a cell, start your iPhone, then press Enter at its text prompt. Each cell waits for this confirmation before opening serial; typing cancel skips it. Follow the approximate sweep cue, and keep filming through all methods and the eight-second pauses. No widget panel or setup cell is required.

| Batch | Message | Methods | Channel time |
|---|---|---|---:|
| B01 | MANUNITED | repeat5, hamming74, rs4 | 200.4 s |
| B02 | ADRIAN | rs4, repeat3, hamming74, repeat5 | 220.8 s |
| B03 | OMAR | hamming74, repeat5, rs4, repeat3 | 186.4 s |

This fills 11 missing method/message cases while reusing the original three noisy uncoded messages and the locally recorded noisy repeat3 MANUNITED message. These are three message cases, not identical-condition repeats or a statistically powered reliability study. Historical capture conditions are not proved identical.

Keep lighting steady for each header, introduce comparable physical disturbance anywhere during each body, and return to steady lighting between messages. Exact sweep timing is flexible. Every batch/retake gets fresh packet IDs and retained logs. The notebook is recording-only. AirDrop the original videos with their existing iPhone names; file organisation, optical-ID association and analysis are handled separately. Logs and videos stay in ignored `experiments/final_capture_v1/`.

The capture notebook intentionally does not score the new videos. Later analysis must segment the multi-packet recordings and independently decode/verify each optical ID. Saved host START times and gaps assist segmentation. Raw-video attachment alone is not proof of a matching optical packet or successful decode. Develop the receiver on the earlier videos and evaluate frozen settings on the new recordings.

**[Repetition_Comparison.ipynb](Repetition_Comparison.ipynb)** retains the earlier T01/T02 workflow and its historical 12-trial plan. It is not the current recording schedule. Existing results and notebooks are preserved; no new clean-only baseline is requested by the capture notebook.

## Hardware

The tested setup is an **ESP32-S3** driving a **LAFVIN 4-inch ST7796S SPI display**, with a phone camera as the receiver. The firmware retains the pin assignments from the existing working display project. The notebook explains the connections and the optical packet format.

At the initial settings, each channel bit lasts 200 ms. An uncoded `HI` packet takes **25.6 seconds**, including training, header, checksum and guard slots. Consecutive identical bits hold the patch at the same brightness across multiple slots.

The firmware uses ESP32 Arduino core **3.2.1**, CDC on boot and native hardware USB. **LovyanGFX 1.2.32** is vendored at commit `e2cc321544fd4e2b6d02f613f3b8555210d2c690`, with its MIT licence retained in `vendor/LovyanGFX/license.txt`.

```sh
python tools/firmware.py build
python tools/firmware.py backup --port /dev/cu.usbmodem101
python tools/firmware.py flash --port /dev/cu.usbmodem101
```

These helpers are configured for the original Mac/ESP32 setup; inspect `--help`, the notebook appendix and your device before using them elsewhere. The app-only uploader checks the original backup, device identity, bootloader and partition compatibility. It is not a universal fresh-board installer. Private flash backups and compiled firmware are intentionally excluded from Git. The original board's backup remains in the separate working project and is not distributed here.

## Project layout

| Path | Purpose |
|---|---|
| `Final_Recordings.ipynb` | Current three-video capture workflow |
| `optical_link/capture.py` | Batch plan, flexible body cues and retained logs |
| `optical_link/capture_cell.py` | Plain recording cells with a start prompt and HTML cues |
| `Optical_Link_Guided.ipynb` | Original guided experiment and explanation |
| `firmware/optical_tx/` | Timed LCD transmitter |
| `optical_link/protocol.py` | Framing, CRC and error-correcting codes |
| `optical_link/device.py` | Serial control and transmission logging |
| `optical_link/video.py` | Video timestamps and ROI brightness extraction |
| `optical_link/receiver.py` | Optical synchronization and independent decoding |
| `tests/` | Protocol and receiver checks |
| `tools/` | Firmware management and notebook generation |
| `vendor/LovyanGFX/` | Pinned display driver and upstream licence |

## Validation and current scope

```sh
python -m unittest discover -s tests -v
```

Tests cover protocol/video decoding, paced USB uploads, missing START responses, retained failures, Reed–Solomon two-byte correction and beyond-capacity outcomes, all 11 planned transmissions, unique IDs, batch interruption, video preservation, and controls that require an explicit operator start. The capture notebook also passed Run All with serial opening blocked. These are software checks, not new physical results.

During setup on 24 October 2026, the firmware upload was hash-verified, the controller completed the blink and `HI` timing tests, and the screen's flashing was visually confirmed. Generated-video tests do not establish real optical-channel performance. Six selected uncoded physical recordings are now published with reproducible metrics below. The researched Reed–Solomon integration is implemented and software-tested; the remaining physical captures and analysis are not yet complete.

This repository is a public snapshot plus an explicitly shared six-video pilot dataset. The selected videos and their portable measurement records are included. The original working notebook, other recordings, device backups, institutional handouts and lab sheets remain outside the public snapshot. Later local edits to the separate working project are not synchronized automatically.

## Physical pilot recordings

[Open the six-recording dataset and results](recordings/pilot_2026-10-24/README.md).

The selected set contains three clean recordings (`HELLO`, `RIYAADH`, `MANUNITED`) and three moving-light recordings (`MANUNITED`, `ADRIAN`, `OMAR`). Original movies are preserved byte-for-byte. The manifest records video hashes, ROIs, trace hashes and source log associations; portable traces and metrics are in `analysis/pilot_2026-10-24/`.

```sh
python tools/evaluate_pilot.py
# Optional: verify the movie hashes and re-extract brightness from the video files
python tools/evaluate_pilot.py --from-video
```

All three selected clean messages match exactly and pass CRC. The three selected noisy messages have 4/72, 2/48 and 1/32 payload-bit errors respectively and fail CRC. These selected examples use different messages and conditions and exclude earlier failed retakes; they are pilot evidence, not a controlled performance estimate. The next experiments should use matched messages across coding methods, consistent interference, unique sequence IDs and a record of every attempt.

## Attribution

The display configuration was adapted from the author's existing robot-face firmware. Repetition and Hamming conventions follow the Week 2 Lab 2 reference implementation; institutional teaching files are not included. The notebook and supporting implementation were developed with AI assistance and require author review and understanding. Third-party LovyanGFX code retains its upstream MIT licence and notices.

The researched RS method uses the unmodified `reedsolo` 1.7.0 pure-Python implementation, bundled with its license and provenance in `optical_link/_vendor/`. The project integration uses GF(256), primitive polynomial 0x11d, generator 2, first root 0, and four parity bytes; the existing CRC remains independent error detection. Upstream algebraic-code authorship is attributed rather than claimed as coursework implementation. See https://github.com/tomerfiliba-org/reedsolomon and https://pypi.org/project/reedsolo/1.7.0/.
