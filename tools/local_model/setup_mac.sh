#!/bin/bash
# One-time setup of the training machine (Apple Silicon Mac). Run from the repository root:
#   bash tools/local_model/setup_mac.sh
# Installs nothing system-wide: it checks for Ollama and Python, builds the project's own
# .venv, downloads the base model (about 2.5 GB) and registers it as "lasermcp-teacher".
set -euo pipefail
cd "$(dirname "$0")/../.."

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Install it from https://ollama.com, open it once, then run this again."
  exit 1
fi

PY=""
for candidate in python3.13 python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or newer is needed. Install it from https://www.python.org/downloads/ and run this again."
  exit 1
fi

echo "== Python environment ($PY)"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

echo "== Base model"
ollama pull phi4-mini
ollama create lasermcp-teacher -f tools/local_model/Modelfile.teacher

echo "== Check: one free request through the real pipeline"
.venv/bin/python tools/ai_eval.py --limit 3

cat <<'DONE'

Ready. Next:
  1) Pilot (about an hour):   caffeinate -i .venv/bin/python tools/train.py collect --count 50
  2) Tell Claude the last line ("kept N, dropped M").
caffeinate keeps the Mac awake while the command runs.
DONE
