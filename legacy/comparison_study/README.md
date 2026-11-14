# Historical collaborator comparison study

This self-contained Python source snapshot preserves the comparison work on GitHub's `dev` branch at commit `955e6c45e7253e63c63cea751ef40f7a3507b18d`. It includes the earlier comparison runner, camera recorder, controlled comparisons and additional receiver filters. `SOURCE.json` records every included file's SHA-256.

**Use the repository-root notebook and `code/` for the final November report.** This snapshot has its own version of the `optical_link` package and its own tests. Do not mix the two directories on `PYTHONPATH` or assume its outputs support the final report's counts.

The original branch remains on GitHub. Dataset files are omitted here; a local preservation ZIP is stored outside the clean project. Optional ESP32 firmware and LovyanGFX are available in the main `code/` tree rather than duplicated here. The historical Python code and vendored Reed–Solomon licence are retained unchanged.

The historical suite has 120 tests; four integration tests require the original receiver-study caches. Restore the preserved GitHub dev dataset into this directory first (so `data/` is beside `code/`). Then, in a separate legacy test process:

```sh
PYTHONPATH=code ../../.venv/bin/python -m unittest discover -s code/tests -v
```

Some historical workflows require their original external data. See `code/tools/recording_comparison.md` and `code/tools/screen_camera_capture.md` for their original usage, not current submission instructions.
