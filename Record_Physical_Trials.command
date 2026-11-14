#!/bin/zsh
# Prepare a local Python environment and open the notebook. No signal until Record + SPACE.
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  if ! command -v python3 >/dev/null; then
    echo 'Install Python 3, then reopen this launcher.'
    read -r 'reply?Press Enter to close.'
    exit 1
  fi
  python3 -m venv "$SCRIPT_DIR/.venv" || exit 1
fi
if ! "$SCRIPT_DIR/.venv/bin/python" -c 'import pygame, cv2, serial, numpy, pandas, matplotlib, nbformat, ipywidgets, jupyterlab' >/dev/null 2>&1; then
  "$SCRIPT_DIR/.venv/bin/python" -m pip install -r code/requirements.txt -r code/requirements-screen-camera.txt || exit 1
fi
exec "$SCRIPT_DIR/.venv/bin/python" -m jupyterlab "$SCRIPT_DIR/Record_Physical_Trials.ipynb"
