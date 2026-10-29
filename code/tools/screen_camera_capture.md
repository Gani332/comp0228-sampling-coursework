# Windows screen → Mac webcam capture

This additive workflow saves physical footage, per-frame timing and transmitter logs.
It does not recover payloads, score packets, register datasets or run filter comparisons.
Host transmitter completion is not proof of physical delivery. Header recognition is
not payload recovery. Windows/Mac physical acceptance has **not** been performed.

## Install and preflight

Use Python 3.11+ (required by existing repository hashing utilities) with the repository's base dependencies on both machines:

```sh
python -m pip install -r code/requirements.txt
```

On Windows additionally install the optional renderer:

```sh
python -m pip install -r code/requirements-screen-camera.txt
python code/tools/run_screen_batch.py --message HELLO --dry-run
python code/tools/run_screen_transmitter.py --message HI --codec none --interleaving off --dry-run
```

Scripts resolve repository defaults from their own files and work from any current
directory when invoked by an absolute script path. `--output` is a directory root;
relative overrides resolve from your current directory. Every invocation creates a
new exclusive session directory. Dry-run/help open neither camera nor display.
Defaults: 200 ms/bit, 5-second countdown, 8-second black batch gaps, sequences 1–10,
Mac camera 0, requested 1280×720 at 30 FPS, 1800-second post-detection budget.
Use `--help` for all options. Camera index 0 is not necessarily the built-in camera.

## Exact operator procedure

1. On Windows, fix brightness, disable automatic brightness/night shifts and screen
   sleep, and avoid notifications. Use mains power. Set the Mac so its camera faces
   the large central patch. Avoid reflections. Static side references are black and
   white; select only the central patch for acquisition, leaving its edges out.
   The central patch is large enough to divide into future 5×5 tiles.
2. Start Windows calibration (no bits are sent until SPACE):

   ```sh
   python code/tools/run_screen_batch.py --message HELLO --session-label hello-01
   ```

   The patch is bright while waiting. Optional `--fullscreen --monitor 0` selects
   the display; monitor indices depend on Windows configuration. All display work
   runs on the main thread. Leave this screen waiting while preparing the Mac.
3. Read the printed plan and recommended timeout. For HELLO at defaults the budget
   recommendation is 660 seconds. A maximum-size 64-byte message can exceed 1800
   seconds. Use the actual printed recommendation for your message and timing.
4. On the Mac, start the independent recorder:

   ```sh
   python code/tools/run_camera_recorder.py --camera 0 --bit-ms 200 --timeout-after-first-seconds 660 --session-label hello-01
   ```

   AVFoundation is preferred on macOS. If access fails, grant Camera permission to
   the hosting Terminal/VS Code app in System Settings → Privacy & Security → Camera,
   then restart it as needed. No privacy bypass is attempted. The actual backend,
   camera settings and output directory are printed. Resolution/FPS setter results
   and readbacks are recorded; exposure/focus are operator-controlled and no support
   for locking them is assumed. Audio is never captured.
5. Drag a rectangle inside the bright patch; ENTER accepts. Press **S** to begin
   recording. Confirm RECORDING / WAITING FOR FIRST PACKET. The output directory is
   printed in the terminal. Free disk space appears in preview; below 2 GB warns.
   Waiting has no automatic timeout, so storage keeps growing. **Q**, **Escape** or
   closing the preview stops; **M** explicitly marks first transmission manually if
   optical detection fails. Manual marking is labeled and is not optical evidence.
6. When ready, press **SPACE** on Windows. Black countdown precedes transmission.
   Batch sends all ten cases in one window, without further interaction:
   none off/on, repeat3 off/on, repeat5 off/on, hamming74 off/on, rs4 off/on.
   The payload and bit duration are identical; IDs are unique within this session.
   Between packets the screen stays black for eight seconds. **Escape**, window
   close or Ctrl+C interrupts and retains partial logs.
7. The Mac recognizes only the public preamble and a CRC-valid supported header.
   Its single fixed timer starts when header validation completes, not from recording
   startup or retrospectively from preamble start. Recognition takes roughly the
   preamble-plus-header duration (16 seconds at 200 ms), plus analysis delay. Later
   observations do not reset the deadline. Keep recording until the batch finishes,
   then Q stops, or let the budget expire. A short budget can truncate transmission.
   Poor lighting can prevent recognition; keep footage and stop manually.
8. Retain the entire Mac receiver folder and copy the complete Windows transmitter
   session folder alongside it. Keep the human session label consistent as a hint.
   Sequence IDs associate observations **within a session**, not across history.
   No automatic association, segmentation, decoding or registration is performed.

For just one packet on Windows:

```sh
python code/tools/run_screen_transmitter.py --message HELLO --codec hamming74 --interleaving on --sequence 1
```

## Data and limits

Default output is `data/screen/{transmitter,receiver}/...`.
The Windows manifest is saved before any display opens and retains all planned
entries, including interrupted/not_sent entries. Per-packet JSON identifies codec,
sequence, exact UTF-8 bytes, depth, original body, actual wire bits and per-slot
absolute deadlines/request/completion/lateness. Unchanged bits still consume full
slots. An overrun of a full bit period aborts. Scheduling uses monotonic deadlines;
OS scheduling and screen refresh still introduce jitter. Swap timestamps describe
host calls, **not measured optical photon times**. The deterministic order is for
operation simplicity and can confound environmental drift with configuration;
it is not a randomized experiment.

Interleaving on uses the existing ragged depth-8 permutation on the body only.
Guards, preamble, header and CRC values remain unchanged. **The header has no
interleaving field.** Only the matched Windows manifest supplies depth to a later
decoder; do not infer it from ordering or apparent decoding success.

The Mac writes one honest `rx_...__continuous__settings-in-transmitter-manifest.avi`
using MJPG, plus `_frames.csv`, `_capture.json` and `_header_observations.csv`.
It never labels the entire footage with a guessed codec or depth. The CSV's
monotonic read-return timestamps are authoritative; they are host observations,
not sensor exposure timestamps. AVI is constant-FPS and may distort presentation
timing. Do not pass it through the old FFprobe-only extraction pipeline until
that pipeline explicitly supports this sidecar. Raw footage is never overwritten
or reencoded after capture. Final verification sequentially decodes every saved
frame, checks count alignment and first/last readability, and saves SHA-256 hashes.
OpenCV write() may not report codec failures immediately; final verification is
therefore essential. Acquisition failure/backlog stops retain partial files and
explicit counts of unwritten successful reads; such captures need review.

The header observer uses a capped time/sample buffer and one background job at a
time, with checks at most once per second. Capture uses a dedicated acquisition
thread and a bounded disk queue; preview and analysis may skip updates, recording
frames are not silently discarded. Sustained backlog stops with explicit counts.
No automatic retry hides a device or writer failure. Re-run in a fresh session.

## Software verification and physical acceptance

```sh
PYTHONPATH=code python -m unittest discover -s code/tests -q
```

Tests inject clock/rendering/camera/writer components and synthetic optical traces.
They are not evidence of physical Windows/Mac compatibility. Before relying on a
real capture, perform and retain results for:

- Windows ten-case dry-run; calibration then slow uncoded HI; inspect timing logs.
- Mac permission/preview and brief recording; inspect frame-count validation.
- Long early wait (timer unarmed), then a single complete packet.
- One full ten-packet HELLO batch in a continuous video. Inspect all transmitter
  logs and header observations; missed observations do not invalidate raw footage.
- Early manual stop, no-signal manual stop, explicit timeout, camera disconnect,
  renderer abort, and fresh-session/no-overwrite behavior.

Hardware operations must be performed separately on the actual Windows transmitter
and Mac receiver; no network start or shared wall clock is needed.

## Compare a saved screen recording

Both comparison runners support the new capture structure through a separate
prepared registry. Historical manifests, caches and frozen results remain intact.
Use Python 3.11+ for the complete repository test suite. No camera or screen is
opened during comparison. Preparation opens a saved video image only when you
have not supplied reference coordinates.

First copy the **matching** Windows transmitter session to
`data/screen/transmitter/`. Choose the session from the successful run; sequence
IDs and the same message alone cannot identify a session globally. The preparation
command never guesses which session you meant. It verifies sequence/codec/length
against observed headers; interleaving depth still comes solely from the selected
transmitter manifest, not optical evidence. Session association is user-supplied.

Prepare once, substituting your actual folder names:

```sh
python3 code/tools/prepare_screen_recording.py \
  --capture data/screen/receiver/<capture-folder> \
  --transmitter data/screen/transmitter/<matching-session-folder> \
  --recording-id screen-lara-01
```

Select two static reference rectangles outside the central flashing patch in the
saved image. ENTER confirms each rectangle. Select the black and white reference
areas if visible, with margins inside their edges. These coordinates are in the
Mac video, not Windows screen pixels. Rectangles must be independent and must
not overlap the selected measurement patch. If neither reference area is visible,
do not substitute flashing pixels or invent reference data: a new recording or
an explicit reduced-method workflow is needed.

For unattended preparation, replace interactive selection with two options:

```text
--reference-roi X1 Y1 W1 H1 --reference-roi X2 Y2 W2 H2
```

Preparation verifies input hashes and frame/sidecar alignment, extracts grayscale
patch, 25 spatial tiles and references, and saves `recording.json` and
`features.npz` under `data/screen/prepared/<recording-id>/`. Uneven patch sizes
use `array_split` so no pixels are discarded. Raw captures remain unchanged.
Existing prepared IDs are never overwritten. All planned transmitter entries
must be completed and have one unambiguous observed header with complete footage;
missing/ambiguous observations currently require explicit review rather than
silently omitting packets or guessing equal-duration clips. Put all input folders
inside the repository; run commands from the repository root.

Run physical comparison for one prepared recording:

```sh
python3 code/tools/run_recording_comparison.py --recording screen-lara-01 --mode physical
```

You can also pass the path to its `recording.json` or prepared directory.
Ten packets generate 70 rows: seven methods for each actual transmitted setting.
Each packet uses its logged depth and configured bit duration. Payload truth is
used for scoring after decoding; optical header acquisition receives no expected
payload. Body BER compares the recovered body after inverse permutation with the
original encoded body. This has the same mismatch count as comparing both sides
in wire order. Physical outputs default to
`data/screen/comparison_results/<recording-id>/<unique-run>/`.

Run all prepared screen captures:

```sh
python3 code/tools/run_batch_comparison.py --source screen --mode physical
```

Batch outputs default to `data/screen/batch_results/<recording-id>/<unique-run>/`.
`--source historical` (the default) preserves the previous batch input set;
`--source all` includes both registries. Both runners accept `--output` overrides.
Every comparison creates a fresh run directory. Raw, unprepared screen captures
are not automatically included in batch comparisons.

The default simulation is now the **original controlled coding study** described
in the report: independent flips, Markov burst flips and glare bursts. It uses
random nine-byte payloads, 24 noise settings, five codes, depths 1/8, seed 20261024
and 2,000 trials per condition. It is independent of this recording and does not
simulate the seven camera filters. Physical replay still evaluates those filters.

```sh
python3 code/tools/run_recording_comparison.py --recording screen-lara-01 --mode both
python3 code/tools/run_batch_comparison.py --source screen --mode both
```

Batch runs this controlled study once for the entire batch. Its outputs live under
`controlled_simulation/`, explicitly separate from physical result CSVs. Use
`--mode modeled --trials 1` for a small smoke run, not report-quality evidence.

For the later recording-residual sensitivity model, explicitly opt in:

```sh
python3 code/tools/run_recording_comparison.py --recording screen-lara-01 --mode both --simulation residual --trials 200
python3 code/tools/run_batch_comparison.py --source screen --mode both --simulation residual --trials 200
```

Residual calibration subtracts the actual interleaved wire signal. Generated
trials are scored after deinterleaving. Residual replay currently requires 200 ms
captures. The original controlled simulation keeps its original 200 ms airtime
setting regardless of the recording's physical bit duration. Neither simulation
creates additional physical evidence. See [recording_comparison.md](recording_comparison.md).
