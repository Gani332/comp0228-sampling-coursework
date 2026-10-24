"""Generate the top-down walkthrough; hardware actions default to disabled."""
from pathlib import Path
import textwrap
import nbformat as nbf
ROOT=Path(__file__).resolve().parents[1]
cells=[]
def md(s): cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(s).strip()))
def code(s): cells.append(nbf.v4.new_code_cell(textwrap.dedent(s).strip()))
md('''
# Light → camera → message
### COMP0228 · Guided hardware notebook · First milestone

**Setup verified on 24 October 2026:** optical firmware installed; you confirmed the rectangle flashes. The controller completed the blink test and the 25.6-second HI transmission. Original firmware is backed up. **Real phone-video decoding is still pending.**

**Goal:** make the existing LAFVIN screen send **HI**, record it with a phone,
and recover **HI** from the recording. Then repeat with error correction.

This is the physical communication-channel prototype for **Sampling, Compression
and Data Analysis**, not the COMP0227 depth/SLAM coursework.

```text
Build an optical communication link
├── 1. Prepare       → identify the existing screen and controller
├── 2. Send          → turn a message into timed bright/dark bits
├── 3. Record        → film one complete transmission on your phone
├── 4. Receive       → measure brightness, find timing, recover the message
└── 5. Assess        → log errors and time; compare coding methods later
```

**First use:** open this notebook in VS Code/Jupyter and select a Python kernel
with `requirements.txt` installed. The existing Week2/Lab2 `.venv` has the required
packages on this Mac. Run from the folder containing this notebook. FFprobe must
also be installed (`ffprobe -version` in a terminal).

Run cells in order. Hardware cells have explicit switches initially set to
`False`; a fresh **Run All does not flash or transmit**. Only enable the step you
are ready to perform. Once a switch is enabled, running that cell again repeats it.
Keep Jarvis's voice bridge and Arduino Serial Monitor closed while using the port.
''')
md('''
## 1 · Prepare the known working hardware

We reuse the display configuration from the working thesis robot face:
**ESP32-S3 → SPI → LAFVIN 4-inch ST7796S TFT**. It is an LCD with a backlight;
we transmit by changing a rectangular patch between black and white. The
backlight supply stays constant. A phone camera records the patch.

| Existing connection | Purpose |
|---|---|
| GPIO 12 → SCK; 11 → SDI/MOSI | Display clock and data |
| GPIO 9 → DC; 10 → CS; 8 → RESET | Display control |
| GPIO 15 → T_CS held high | Touch controller remains inactive |
| Existing verified power/GND wiring | Reuse the working setup |

The thesis notes record **J1 open, VCC=5 V, LED=3V3** for this specific screen.
Keep that verified wiring. GPIO signal levels are 3.3 V. No Pi or OV camera is
needed for this milestone. Disconnect power before changing wiring.

The original face source stays in the thesis folder. `backup/` holds a copy and,
when backup succeeds, the full original flash. The appendix explains restoration.
''')
md('### Install the serial dependency in this kernel\n\nRun this cell before the main imports. The package is called **pyserial**, while Python imports it as **serial**. This checks the Python interpreter used by this notebook and installs the package there only if it is missing. If an already-running kernel still reports the old error, restart the kernel and rerun from here.')
code('import sys, importlib, importlib.util, subprocess\nprint("Notebook Python:", sys.executable)\nif importlib.util.find_spec("serial") is None:\n    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyserial"])\n    importlib.invalidate_caches()\nimport serial\nprint("pyserial ready:", serial.__version__)\nprint("Loaded from:", serial.__file__)')
code(r'''
from pathlib import Path
from datetime import datetime, timezone
import json, sys, shutil, subprocess
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path.cwd().resolve()
assert (ROOT / 'optical_link').is_dir(), 'Set the notebook working folder to this project.'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from optical_link.protocol import make_packet, to_bits, GUARD_BITS, PREAMBLE, HEADER_BITS
from optical_link.device import ports, Transmitter
from optical_link.receiver import decode_trace, synthetic_trace
from optical_link.video import preview, extract_trace, save_trace

def attempt_id():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')

print('Python:', sys.executable)
print('FFprobe:', shutil.which('ffprobe'))
print('Detected serial devices:', ports())
''')
md('''
### 1A · Check the screen before sending data

Set `PORT` to the native Espressif device shown above. It was `/dev/cu.usbmodem101`
during setup; macOS may change the name after reconnection.

If the screen still shows the robot face, install the optical firmware using
Appendix A first. With optical firmware, you should see **COMP0228 | LIGHT LINK**
and a dark central rectangle. Set `RUN_BLINK=True` below: the rectangle should
be white for one second, black for one second, three times. It finishes black.
A controller acknowledgment confirms code execution; **you must check the actual
screen**. This notebook cannot see it through USB.
''')
code(r'''
PORT = '/dev/cu.usbmodem101'  # Recheck after reconnecting.
RUN_BLINK = False
if RUN_BLINK:
    with Transmitter(PORT) as tx:
        print(tx.identity)
        print('\n'.join(tx.blink()))
else:
    print('Blink not run. Enable RUN_BLINK when you can watch the screen.')
''')
md('''
## 2 · Prepare a message and understand the signal

A white patch represents **1**; a black patch represents **0**. Each bit gets the
same time slot. For the first experiment this is **200 ms per bit = 5 channel
bits/second**. Two consecutive 1s stay white for two slots; do not count flashes.

`H = 01001000`, `I = 01001001`. We use fixed-length binary instead of Morse so
that the Week 2 error-correcting codes fit directly around the message bits.

The receiver also needs to know where a message begins and how long it is:

```text
8 dark slots | 32-bit training/start pattern | 48-bit header | coded body | 8 dark slots
                                                ↓                ↓
                                  version, code, length, ID, CRC   message + CRC
```

The header tells the receiver the message length and coding method. A CRC is a
checksum that **detects** many corruptions; it does not correct them or guarantee
that every error is detected. Error correction, when selected, protects the body
including its CRC. The header is currently uncoded: damaged headers count as
failed packets. Keep this limitation visible in later comparisons.
''')
code(r'''
MESSAGE = 'HI'          # Start short: 2–8 bytes until timing is validated.
CODEC = 'none'          # Later: 'repeat3', 'repeat5', 'hamming74'.
SEQUENCE = 1            # Increase per attempt to help match recordings and logs.
BIT_MS = 200
packet = make_packet(MESSAGE, codec=CODEC, sequence=SEQUENCE)
planned_seconds = len(packet.bits) * BIT_MS / 1000
print('Message:', MESSAGE, '| UTF-8 bytes:', packet.payload.hex())
print('Payload bits:', ''.join(map(str, to_bits(packet.payload))))
print('Coding:', CODEC, '| Total channel slots:', len(packet.bits))
print(f'Full scheduled transmission including framing/guards: {planned_seconds:.1f} seconds')
print(f'Ideal payload rate including framing/guards: {8*len(packet.payload)/planned_seconds:.3f} bit/s')
''')
md('''
### 2A · Check the software before using the camera

This next cell creates an **artificial brightness trace** with noise and missing
frames. It tests the software only. Its successful result must never be reported
as a successful hardware transmission. The decoder receives timestamps,
brightness and the public nominal bit duration; it never receives the sent text.
''')
code(r'''
sim_packet = make_packet('HI', codec='none', sequence=0)
sim_t, sim_y = synthetic_trace(sim_packet, bit_ms=BIT_MS, drop_fraction=0)
sim_result = decode_trace(sim_t, sim_y, bit_ms=BIT_MS)
print('SYNTHETIC SOFTWARE CHECK:', repr(sim_result['text']), '| CRC:', sim_result['crc_ok'])
fig, ax = plt.subplots(figsize=(12, 2.8))
ax.plot(sim_t, sim_y, lw=1)
ax.axhline(sim_result['threshold'], color='tab:orange', ls='--', label='Threshold')
ax.set(xlabel='Video time (s)', ylabel='Brightness (0–255)', title='Synthetic example — not measured hardware')
ax.legend(); plt.show()
''')
md('''
## 3 · Record one physical transmission

1. Keep the phone and screen still. Frame the display so the central patch is
   large enough to select a clean rectangle inside it.
2. Use normal video, initially 30 or 60 fps. Avoid time-lapse/slow-motion modes.
   Lock focus/exposure if your camera supports it; avoid a saturated white patch.
3. Start recording **before** running the transmit cell. Record the entire packet
   and leave at least two seconds after completion.
4. Stop recording. Transfer the **original** video to `recordings/` without a
   messaging app recompressing it. One packet per recording is simplest.

For `HI`, no coding and 200 ms slots, the transmission takes **25.6 seconds**.
Start the phone first, then enable and run the cell below. The USB connection
loads the bits into the screen controller; the receiver uses the camera video.
No USB transmission time is used to tell the receiver where the light begins.
''')
code(r'''
RUN_TRANSMISSION = False
# Set these when you actually collect a recording; keep failed attempts too.
CONDITIONS = {'distance_cm': None, 'phone_model': '', 'camera_mode': '',
              'lighting': '', 'interference': 'none', 'notes': ''}
if RUN_TRANSMISSION:
    tx_path = ROOT / 'results' / (attempt_id() + '_tx.json')
    with Transmitter(PORT) as tx:
        tx_log = tx.transmit(packet, bit_ms=BIT_MS, log_path=tx_path)
    tx_log['conditions'] = CONDITIONS
    tx_path.write_text(json.dumps(tx_log, indent=2) + '\n')
    print('Controller completed. Stop the phone after two more seconds.')
    print('Transmission log:', tx_path)
else:
    print('No transmission requested. Start recording before enabling this cell.')
''')
md('''
## 4 · Receive from the phone video

### 4A · Choose the video and inspect a frame

Set `VIDEO` below to your original `.MOV`/`.mp4` file. Preview a frame where the
patch is visible. Use the displayed **pixel coordinates** to choose an ROI
(region of interest) wholly inside the central patch, away from text/borders.
The preview uses the stored pixel orientation; a portrait clip may appear
sideways. Use that same coordinate system for the ROI.
''')
code(r'''
VIDEO = None  # Example: ROOT / 'recordings' / 'hi_001.MOV'
PREVIEW_FRAME = 150
if VIDEO is not None:
    frame = preview(VIDEO, frame=PREVIEW_FRAME)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(frame)
    ax.set(xlabel='x (pixels)', ylabel='y (pixels)', title='Choose an ROI inside the flashing patch')
    plt.show()
else:
    print('Set VIDEO after recording and transferring the original clip.')
''')
code(r'''
ROI = None  # Replace with (x, y, width, height), e.g. (520, 300, 100, 80).
if VIDEO is not None and ROI is not None:
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(frame)
    ax.add_patch(Rectangle(ROI[:2], ROI[2], ROI[3], fill=False, ec='lime', lw=2))
    ax.set_title('Confirm the green box stays inside the patch throughout the video')
    plt.show()
else:
    print('Set ROI after inspecting the video preview.')
''')
md('''
### 4B · Turn the recording into measurements

Each frame gives one mean brightness measurement inside the ROI. FFprobe supplies
that frame's presentation timestamp, so variable phone frame rates are respected.
The code refuses to pair mismatched frame/timestamp counts. We save the original
video hash, ROI, timestamps and brightness for reproducibility.

Adjust the ROI if it includes background. If the phone moves so the patch leaves
the ROI, re-record for this first test; tracking a moving ROI is a later extension.
''')
code(r'''
physical_trace = None
if VIDEO is not None and ROI is not None:
    video_t, video_y, metadata = extract_trace(VIDEO, ROI)
    metadata['conditions'] = CONDITIONS
    capture_prefix = ROOT / 'results' / (attempt_id() + '_brightness')
    save_trace(video_t, video_y, metadata, capture_prefix)
    physical_trace = (video_t, video_y)
    print(metadata)
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.plot(video_t, video_y, lw=1)
    ax.set(xlabel='Video presentation time (s)', ylabel='Mean brightness', title='Measured camera signal')
    plt.show()
else:
    print('No physical measurements yet: VIDEO and ROI are required.')
''')
md('''
### 4C · Find the message without being given its contents

The receiver finds the public training/start pattern, estimates the clock from
its observed transitions, learns the dark/bright threshold, and reads the header.
It then samples the middle of each body slot, decodes the selected code and checks
the message CRC. It does **not** use `MESSAGE`, `packet`, or the sender's start time.

The initial receiver expects one short packet, a fixed ROI and a nominal slot
length known in advance. It does not yet track changing exposure or clock drift
through long messages. Failed synchronization, missing samples and failed CRCs
remain failed attempts; do not delete them or fix them using the intended text.
''')
code(r'''
received = None
if physical_trace is not None:
    rx_path = ROOT / 'results' / (attempt_id() + '_rx.json')
    try:
        received = decode_trace(*physical_trace, bit_ms=BIT_MS)
        summary = {k: v for k, v in received.items() if not isinstance(v, (bytes, np.ndarray))}
        summary.update({'payload_hex': received['payload'].hex(),
                        'data_kind': 'physical_video', 'video_sha256': metadata['video_sha256'],
                        'trace_file': str(capture_prefix.with_suffix('.csv')),
                        'status': 'crc_pass' if received['crc_ok'] else 'crc_fail'})
        print('Recovered text:', repr(received['text']))
        print('CRC:', received['crc_ok'], '| Sequence:', received['sequence'], '| Code:', received['codec'])
        print(f"Recovered slot duration: {1000*received['period_seconds']:.3f} ms")
        print('Low-confidence body bits:', received['low_confidence_body_bits'])
        if not received['crc_ok']:
            print('CRC FAILED: this is not a successful message delivery.')
    except ValueError as e:
        summary = {'status': 'decode_failed', 'reason': str(e), 'data_kind': 'physical_video',
                   'video_sha256': metadata['video_sha256'],
                   'trace_file': str(capture_prefix.with_suffix('.csv'))}
        print('Physical attempt failed:', e)
    rx_path.write_text(json.dumps(summary, indent=2) + '\n')
    print('Receiver result saved:', rx_path)
else:
    print('Waiting for a physical video. Synthetic checks do not fill this section.')
''')
code(r'''
if received is not None:
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.plot(video_t, video_y, lw=1, label='Camera measurement')
    ax.axhline(received['threshold'], color='tab:orange', ls='--', label='Learned threshold')
    ax.scatter(received['body_sample_times'], received['body_sample_values'], s=10,
               c=received['body_bits'], cmap='coolwarm', label='Body bit samples')
    ax.set(xlabel='Video time (s)', ylabel='Brightness', title='Inspect timing and bit decisions')
    ax.legend(); plt.show()
''')
md('''
## 5 · Assess the attempt, then extend the experiment

Only **after independent decoding** do we compare against the saved transmitter
log. Channel-body BER compares received coded bits with transmitted coded bits.
Payload BER compares the recovered message bits after error correction with the
original message. Framing/header failures do not have a trustworthy payload BER;
they still count in packet failure rate. Do not report failed packets as BER=0.

The rate below counts training, header, checksum, coding and dark guard overhead.
It excludes manual camera handling. Record these definitions when comparing rates.
For repeated trials, use **total CRC-valid delivered payload bits / total channel
time across all attempts**, including failures. Report attempt count, failed
frames and uncertainty alongside BER/goodput.
''')
code(r'''
TX_LOG = None  # Choose the matching results/..._tx.json from this physical attempt.
if received is not None and TX_LOG is not None:
    truth = json.loads(Path(TX_LOG).read_text())
    if truth['status'] != 'controller_completed':
        raise ValueError('Transmitter did not complete this attempt.')
    if (truth['sequence'], truth['codec']) != (received['sequence'], received['codec']):
        raise ValueError('The selected transmitter log does not match this decoded packet.')
    sent = np.array([int(x) for x in truth['transmitted_bits']], dtype=np.uint8)
    body_offset = GUARD_BITS + len(PREAMBLE) + HEADER_BITS
    expected_body = sent[body_offset:-GUARD_BITS]
    expected_payload = bytes.fromhex(truth['payload_hex'])
    if len(expected_body) != len(received['body_bits']) or len(expected_payload) != len(received['payload']):
        raise ValueError('Lengths differ; investigate framing/log matching instead of forcing BER.')
    channel_errors = int(np.count_nonzero(expected_body != received['body_bits']))
    payload_errors = int(np.count_nonzero(to_bits(expected_payload) != to_bits(received['payload'])))
    seconds = truth['scheduled_channel_seconds']
    metrics = {'body_channel_bit_errors': channel_errors, 'body_channel_bits': len(expected_body),
               'body_channel_ber': channel_errors/len(expected_body),
               'payload_bit_errors': payload_errors, 'payload_bits': len(expected_payload)*8,
               'payload_ber': payload_errors/(len(expected_payload)*8),
               'packet_failed': not received['crc_ok'], 'channel_seconds_including_overhead': seconds,
               'crc_valid_payload_goodput_bps': len(expected_payload)*8*bool(received['crc_ok'])/seconds,
               'exact_payload_match': received['payload'] == expected_payload,
               'tx_log': str(TX_LOG), 'rx_log': str(rx_path)}
    print(json.dumps(metrics, indent=2))
    (ROOT/'results'/(attempt_id()+'_metrics.json')).write_text(json.dumps(metrics, indent=2)+'\n')
else:
    print('Select the matching TX_LOG after decoding a real recording.')
''')
md('''
### What comes after the first successful HI?

| Work bucket | Next deliverable | Evidence to retain |
|---|---|---|
| Establish the baseline | Repeat uncoded messages at fixed settings | Original videos, brightness traces, all successes/failures |
| Compare coding | `none`, repetition 3/5, Hamming(7,4), then a researched third family | Same message/conditions, randomized trial order, equal stated time budget |
| Stress the physical channel | Vary distance, angle, light or brief occlusion one at a time | Measured conditions, BER, packet failure, overhead and delivered rate |
| Explain the errors | Compare isolated flips, bursts and lost synchronization | Error locations/run lengths and examples of failed frames |
| Develop an extension | Choose and justify an improvement, e.g. interleaving or better synchronization | Controlled before/after comparison with limitations |
| Communicate the work | Reproducible code, report, presentation and live demonstration | Brief/rubric checklist, contributions, attribution and understood code |

**Week 2 / Lab 2 connection:** repetition and Hamming functions use the lab's bit
conventions. The new physical channel replaces the lab's microphone/speaker
frontend with display/camera. Noise simulations help debug; physical recordings
are still needed for the coursework comparison.

Repetition and Hamming are **two coding families**. Testing two repetition levels
does not fulfil a requirement for a third researched family. This notebook is a
hardware starting point, not the completed coursework or evidence for a grade.

Hamming(7,4) corrects one error per codeword. Multiple errors can be miscorrected;
the body CRC helps detect the resulting corruption. The currently uncoded header
can limit every codec and must be counted in the results.
''')
md('''
## Appendix A · Build, install and restore firmware

These commands are explicit terminal actions; the notebook does not run them.
On this Mac, the supplied firmware was built with **ESP32 Arduino 3.2.1** and
**LovyanGFX 1.2.32**, using `ESP32S3 Dev Module`, native hardware USB and CDC on boot.
The exact pinned display-library source and MIT licence are in `vendor/LovyanGFX/`.
The sketch uses a 4 MB partition layout and no PSRAM, matching the existing face.

From this project folder:

```sh
python tools/firmware.py build
python tools/firmware.py backup --port /dev/cu.usbmodem101
python tools/firmware.py flash --port /dev/cu.usbmodem101
```

`backup` refuses to overwrite an existing original backup. If `backup/manifest.json`
already describes a verified complete backup from setup, proceed to `flash`.
The flash helper checks the backup hash, USB device identity, and bootloader and
partition compatibility before replacing **only the application**. The board's
full original flash is retained. Do not use this backup on another ESP32.
The helper is configured for this Mac's Arduino and PlatformIO tool locations;
`--cli` and `--esptool` allow overrides. Other computers can also use Arduino IDE,
the documented board settings and bundled library after making their own backup.

To restore the same board to its original robot-face state:

```sh
python tools/firmware.py restore --port /dev/cu.usbmodem101
```

Close serial connections before uploading/restoring. If macOS changes the port,
rerun the device listing in section 1. The optical app does not use the touchscreen,
Wi-Fi, voice bridge or robot motors. Serial commands: `ID?`, `WHITE`, `BLACK`,
`BLINK`, `SEND <milliseconds> <binary bits>`, `STOP`.

## Appendix B · Files, tests and sources

| File/folder | Role |
|---|---|
| `firmware/optical_tx/optical_tx.ino` | Adapted display driver and timed light transmitter |
| `optical_link/protocol.py` | Public packet format, CRC, repetition and Hamming |
| `optical_link/device.py` | Serial connection and retained transmission logs |
| `optical_link/video.py` | Original video, actual timestamps, ROI brightness |
| `optical_link/receiver.py` | Optical synchronization, bit sampling and decoding |
| `recordings/`, `results/` | Your original recordings and all measured attempts |
| `evidence/` | Build/test logs and provenance; see hardware status separately |
| `backup/` | Original face source, known build and full flash rollback when available |

Run software checks with `python -m unittest discover -s tests -v`.
They cover the CRC check vector, Hamming single-bit correction, repetition,
corrupt headers/bodies, dropped samples and a generated video through FFprobe.
**Generated tests establish software behaviour, not real optical performance.**

Sources: your thesis `CAD/firmware/home_companion/home_companion/home_companion.ino`,
its `docs/HOME_COMPANION.md`, and `Week2/Lab2/lab2_reference.py`.
Library source: [pinned LovyanGFX](https://github.com/lovyan03/LovyanGFX/tree/e2cc321544fd4e2b6d02f613f3b8555210d2c690).
Video timestamp tool: [FFprobe documentation](https://ffmpeg.org/ffprobe.html).
Keep these attributions and record AI assistance according to your coursework rules.
''')
nb=nbf.v4.new_notebook(cells=cells,metadata={
 'kernelspec':{'display_name':'Python 3 (ipykernel)','language':'python','name':'python3'},
 'language_info':{'name':'python','version':'3.11'}})
nbf.validate(nb)
nbf.write(nb,ROOT/'Optical_Link_Guided.ipynb')
print('Wrote',len(cells),'cells')
if __name__=='__main__': pass
