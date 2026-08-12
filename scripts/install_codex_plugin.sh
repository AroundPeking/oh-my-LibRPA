#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_command="${PYTHON:-python3}"
venv="$root/.venv"

"$python_command" -m venv "$venv"
"$venv/bin/python" -m pip install --upgrade pip
"$venv/bin/python" -m pip install -e "$root"

printf 'Installed Oh-My-LibRPA MCP environment at %s\n' "$venv"
