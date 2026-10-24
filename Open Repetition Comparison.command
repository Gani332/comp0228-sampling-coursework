#!/bin/zsh
set -e
project_root="${0:A:h}"
lab_python="$project_root/../../Week2/Lab2/.venv/bin/python"
if [[ -x "$project_root/.venv/bin/python" ]]; then
  notebook_python="$project_root/.venv/bin/python"
elif [[ -x "$lab_python" ]]; then
  notebook_python="$lab_python"
else
  print 'Create a Python environment in this project and install requirements.txt first.'
  print 'python3 -m venv .venv'
  print '.venv/bin/python -m pip install -r requirements.txt'
  read 'reply?Press Enter to close.'
  exit 1
fi
cd "$project_root"
exec "$notebook_python" -m jupyterlab --ip=127.0.0.1 --notebook-dir="$project_root" "$project_root/Repetition_Comparison.ipynb"
