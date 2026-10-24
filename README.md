# COMP0228 Sampling Coursework

Optical communication coursework for **Sampling, Compression and Data Analysis** at UCL.

The current prototype sends a message through a flashing LCD patch, records it with a phone camera, and reconstructs the message from the video. It supports an uncoded baseline, repetition coding (3 and 5 repetitions), and Hamming(7,4).

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

## Controlled repetition comparison

Open **[Repetition_Comparison.ipynb](Repetition_Comparison.ipynb)** for the next experiment, or use `Open Repetition Comparison.command` on the original Mac.

- Fixed message `MANUNITED`, 200 ms bit slots.
- 12 planned trials: uncoded/repeat3 × clean/noisy × three repeats.
- T01 is a 72-second clean repeat3 transmission; T02 is repeat3 with a light disturbance.
- A large visual cue schedules one two-second light sweep, anchored to the controller START acknowledgment with a two-second margin after the header. The cue records host instructions, not measured physical light timing.
- Each recording is linked to its own transmission log. Retakes retain earlier records and get new sequence IDs. A wrong packet ID/code is reported as a pairing error, and the same video cannot be assigned to two attempts.
- Failed synchronization/header attempts count in packet failure rate; their unknown payload BER is not entered as zero. Aborted transmissions and unevaluated attempts are reported separately.

All new experiment data stays in the ignored `experiments/repetition_comparison/` folder. Hardware actions default to disabled. A separate arming cell enables the transmit cell, which consumes that switch; rerunning the transmit cell alone does not send twice. The original pilot notebook and six-recording dataset remain available.

This is a **single-interference-event-per-packet pilot**, not a continuous-noise experiment. More messages, repeated conditions and uncertainty analysis are needed before making general performance claims. The visual cue and bookkeeping passed software checks and a notebook dry run; the first physical repeat3 trial must still be collected.

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
| `Optical_Link_Guided.ipynb` | Guided experiment and explanation |
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

Nineteen tests cover the original protocol/video checks plus the controlled comparison: START-anchored cues, header margins, repetition repair, recording association, retained retakes/aborts and failed-packet accounting.

During setup on 24 October 2026, the firmware upload was hash-verified, the controller completed the blink and `HI` timing tests, and the screen's flashing was visually confirmed. Generated-video tests do not establish real optical-channel performance. Six selected uncoded physical recordings are now published with reproducible metrics below. Controlled coding comparisons, the third researched coding family and the remaining coursework analysis are still to be completed.

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
