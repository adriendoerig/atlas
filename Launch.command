#!/bin/zsh
cd "$(dirname "$0")"

export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

exec .venv/bin/python server_control.py