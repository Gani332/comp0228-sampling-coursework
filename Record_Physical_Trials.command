#!/bin/zsh
# Opens the notebook only. Hardware transmission requires the notebook prompt.
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  echo 'The coursework Python environment is missing. Open Record_Physical_Trials.ipynb in your configured Jupyter environment.'
  read -r 'reply?Press Enter to close.'
  exit 1
fi
exec "$SCRIPT_DIR/.venv/bin/python" -m jupyterlab "$SCRIPT_DIR/Record_Physical_Trials.ipynb"
