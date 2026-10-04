import sqlite3
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS samples (
 id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, mtime_ns INTEGER, size INTEGER,
 analysis_version TEXT, duration REAL, sample_rate INTEGER, channels INTEGER,
 one_shot REAL, drum_heuristic REAL, features TEXT, detail TEXT,
 clap BLOB, clap_version TEXT, drum_clap REAL, clap_detail TEXT,
 active INTEGER NOT NULL DEFAULT 1, error TEXT);
CREATE TABLE IF NOT EXISTS spaces (name TEXT PRIMARY KEY, signature TEXT, metric TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS points (space TEXT, sample_id INTEGER REFERENCES samples(id) ON DELETE CASCADE,
 x REAL,y REAL, vector BLOB, PRIMARY KEY(space,sample_id));
'''
def connect(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(str(path),timeout=60)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript(SCHEMA)
    return db
