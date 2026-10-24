#!/bin/zsh
set -e
project_root="${0:A:h}"
lab_python="$project_root/../../Week2/Lab2/.venv/bin/python"
notebook_python=''
for candidate in "$project_root/.venv/bin/python" /opt/anaconda3/bin/python "$lab_python"; do
  if [[ -x "$candidate" ]] && "$candidate" -c 'import ipywidgets, jupyterlab, serial, numpy, cv2' >/dev/null 2>&1; then
    notebook_python="$candidate"
    break
  fi
done
if [[ -z "$notebook_python" ]]; then
  print 'Install requirements.txt in your Python environment, then open Final_Recordings.ipynb.'
  read 'reply?Press Enter to close.'
  exit 1
fi
cd "$project_root"
exec "$notebook_python" -m jupyterlab --ip=127.0.0.1 --notebook-dir="$project_root" "$project_root/Final_Recordings.ipynb"
