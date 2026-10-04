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
    migrate_pools(db)
    return db

POOL_SCHEMA = '''
CREATE TABLE IF NOT EXISTS pools (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL CHECK(kind IN ('folder','manual')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS pool_samples (
 pool_id INTEGER NOT NULL REFERENCES pools(id) ON DELETE CASCADE,
 sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
 PRIMARY KEY(pool_id,sample_id));
CREATE INDEX IF NOT EXISTS pool_samples_sample ON pool_samples(sample_id);
CREATE TABLE IF NOT EXISTS pool_roots (
 pool_id INTEGER NOT NULL REFERENCES pools(id) ON DELETE CASCADE,
 path TEXT NOT NULL, PRIMARY KEY(pool_id,path));
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''

def migrate_pools(db):
    import json
    import os
    db.executescript(POOL_SCHEMA)
    with db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM settings WHERE key='pools_migrated'").fetchone():
            return
        rows = db.execute('SELECT id,path FROM samples').fetchall()
        active = []
        if rows:
            pid = db.execute("INSERT INTO pools(name,kind) VALUES('Polaroit','manual')").lastrowid
            db.executemany('INSERT INTO pool_samples VALUES(?,?)', [(pid,r['id']) for r in rows])
            root = Path(os.path.commonpath([str(Path(r['path']).parent) for r in rows]))
            # Only infer a rescan root when it is a specific existing folder.
            if root.is_dir() and len(root.parts) >= 4:
                db.execute("UPDATE pools SET kind='folder' WHERE id=?",(pid,))
                db.execute('INSERT INTO pool_roots VALUES(?,?)',(pid,str(root)))
            active = [pid]
        db.execute("INSERT INTO settings VALUES('active_pools',?)", (json.dumps(active),))
        db.execute("INSERT INTO settings VALUES('pools_migrated','1')")
