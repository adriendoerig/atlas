#!/bin/zsh
cd "$(dirname "$0")"
set -e
trap 'print "Setup stopped. Read the error above, then press Return."; read' ZERR
# Python's macOS installer may not add its framework binary to Finder's PATH.
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v python3.12 >/dev/null 2>&1; then
  print "Install Python 3.12 from https://www.python.org/downloads/macos/ first."
  print "Then double-click Setup.command again. Press Return to close."
  read
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  python3.12 -m venv .venv
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3,12), "Use a Python 3.12 environment for this project"'
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/python -m pip check
.venv/bin/python -c 'import drum_atlas.server, soundfile, torch; print("Drum Atlas is ready.")'
chmod +x Launch.command Cleanup.command
print "Next: double-click Launch.command, then Open Drum Atlas.webloc."
print "On this Mac, create pools pointing to its own sample folders."
print "Press Return to close."
read
