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

Hardware actions default to disabled. The initial software demonstration uses synthetic data and is labelled accordingly. Your original phone video stays on your computer in `recordings/`; results are saved locally in `results/`.

### Python setup

Use Python 3.11 or a compatible Python environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m jupyterlab Optical_Link_Guided.ipynb
```

Install **FFmpeg/FFprobe** separately and make `ffprobe` available on your PATH. On macOS, the included `Open Optical Link.command` launcher uses this project's `.venv`, or the existing Week 2 Lab 2 environment when present.

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

Nine tests cover the CRC check vector, Hamming single-bit correction, repetition decoding, corrupted headers/bodies, timing jitter, missing samples, and a generated video through the receiver pipeline.

During setup on 24 October 2026, the firmware upload was hash-verified, the controller completed the blink and `HI` timing tests, and the screen's flashing was visually confirmed. Generated-video tests do not establish real optical-channel performance. Physical recordings, controlled comparisons, the third researched coding family, and the remaining coursework analysis are separate work.

This repository is a clean public snapshot. The original working notebook, personal recordings, per-attempt measurements, device backups, institutional handouts and lab sheets are not published. Later local edits to the separate working project are not synchronized automatically.

## Attribution

The display configuration was adapted from the author's existing robot-face firmware. Repetition and Hamming conventions follow the Week 2 Lab 2 reference implementation; institutional teaching files are not included. The notebook and supporting implementation were developed with AI assistance and require author review and understanding. Third-party LovyanGFX code retains its upstream MIT licence and notices.
