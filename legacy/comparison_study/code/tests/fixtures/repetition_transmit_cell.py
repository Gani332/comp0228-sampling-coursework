# Legacy one-shot recording cell; executed only by its regression test.
attempt_dir = None
if RUN_TRANSMISSION:
    RUN_TRANSMISSION = False  # One-shot: consciously re-enable for another send.
    cue_display = display(HTML('<div style="padding:18px;background:#fff3cd;font-size:23px">Connecting — keep the scene steady.</div>'), display_id=True)
    def show_cue(state):
        colours = {'wait':'#fff3cd', 'steady':'#e7f1ff', 'sweep':'#ffe2e2', 'stop':'#e7f1ff', 'complete':'#dcfce7'}
        message = html.escape(state['message'])
        cue_display.update(HTML(f'<div style="padding:18px;background:{colours[state["phase"]]};color:#111;font-size:23px"><strong>{message}</strong><br><small>Approximately {state["remaining_seconds"]} seconds remaining</small></div>'))
    try:
        attempt_dir = run_trial(ROOT, plan, TRIAL_ID, PORT, SETUP, display=show_cue)
        print('Saved transmission and cue record:', attempt_dir)
    except (Exception, KeyboardInterrupt) as e:
        cue_display.update(HTML('<div style="padding:18px;background:#ffe2e2">Transmission did not complete. The attempt is retained; inspect the error below.</div>'))
        print(type(e).__name__+':', e)
        previous = attempts(ROOT, TRIAL_ID)
        attempt_dir = previous[-1][0] if previous else None
else:
    previous = attempts(ROOT, TRIAL_ID)
    attempt_dir = previous[-1][0] if previous else None
    print('No transmission started. Start phone recording before enabling this cell.')
    if attempt_dir: print('Latest saved attempt for this trial:', attempt_dir)
