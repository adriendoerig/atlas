"""Platform defaults; environment variables support portable/test installations."""
import os
import sys
from pathlib import Path

def data_dir():
    default = Path.home() / ('Library/Application Support/Drum Atlas' if sys.platform == 'darwin' else '.local/share/drum-atlas')
    return Path(os.environ.get('DRUM_ATLAS_DATA_DIR', default)).expanduser()

def cache_dir():
    default = Path.home() / ('Library/Caches/Drum Atlas' if sys.platform == 'darwin' else '.cache/drum-atlas')
    return Path(os.environ.get('DRUM_ATLAS_CACHE_DIR', default)).expanduser()

def database_path():
    return data_dir() / 'library.sqlite'
