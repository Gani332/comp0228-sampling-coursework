"""Invoke the original controlled coding study without recording-derived noise."""
from pathlib import Path
from .coding_experiments import DEFAULT_CONFIG, run_study
from .screen_capture_packet import identifier, save_json
import hashlib


def run_controlled(root, output, *, seed=20261024, trials=2000):
    root, output = Path(root).resolve(), Path(output)
    if trials < 1 or seed < 0:
        raise ValueError('Require positive trials and a nonnegative seed.')
    config = dict(DEFAULT_CONFIG, seed=seed, trials_per_condition=trials)
    print(f'CONTROLLED: original iid_flip/burst_flip/glare_burst grid; '
          f'{trials} random nine-byte payloads per condition; seed={seed}. '
          'Perfect acquisition/header assumed; no camera-filter simulation.', flush=True)
    run_study(root/'code', output, config)
    save_json(output/'comparison_context.json',dict(
        adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        simulation='controlled',engine='optical_link.coding_experiments.run_study',
        evidence_kind='controlled_synthetic_coding',recording_calibration=False,
        camera_filters_evaluated=False,
        note='Independent of recording, ROI and payload. Actual framing airtime is charged. '
             'Original settings unless explicit seed/trials overrides were supplied.'))
    return output


def run_for_recording(root, recording, mode, output, seed, trials, random_payload):
    from .comparison_runner import run, resolve_recording, recording_slug
    from .screen_recording_comparison import resolve
    import json
    root=Path(root).resolve()
    if random_payload:
        raise ValueError('--random-payload belongs to residual replay. Controlled simulation always uses the original random nine-byte payload design.')
    if mode=='both':
        out=run(root,recording=recording,mode='physical',output=output,
                seed=seed,trials=trials,simulation='residual')
    else:
        screen=resolve(root,recording)
        if screen:
            name=json.loads(screen.read_text())['id']
            base=root/'data/screen/comparison_results'/name
        else:
            video,name=resolve_recording(root,recording)
            base=root/'data/comparison/comparison_results'/recording_slug(name)
        out=(root/output if output is not None else base)/identifier()
        out.mkdir(parents=True,exist_ok=False)
    run_controlled(root,out/'controlled_simulation',seed=seed,trials=trials)
    save_json(out/'simulation_selection.json',dict(simulation='controlled',mode=mode,
              seed=seed,trials_per_condition=trials,recording=recording,
              simulation_depends_on_recording=False,
              physical_metadata_note='Any physical run metadata describes only measured physical replay.'))
    return out
