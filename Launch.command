#!/bin/zsh
cd "$(dirname "$0")"
exec .venv/bin/drum-atlas serve
