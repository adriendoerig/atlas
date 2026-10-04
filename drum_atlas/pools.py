"""Pool memberships never own or duplicate analysis or projection data."""
import json
from pathlib import Path
from .store import connect
from .paths import cache_dir

def state(db):
    ids = json.loads(db.execute("SELECT value FROM settings WHERE key='active_pools'").fetchone()[0])
    members = [r[0] for r in db.execute('''SELECT DISTINCT ps.sample_id FROM pool_samples ps
        JOIN samples s ON s.id=ps.sample_id WHERE s.active=1 AND ps.pool_id IN
        (SELECT value FROM json_each(?)) ORDER BY ps.sample_id''', (json.dumps(ids),))]
    pools = [dict(r) | {'roots':[x[0] for x in db.execute('SELECT path FROM pool_roots WHERE pool_id=? ORDER BY path',(r['id'],))]}
             for r in db.execute('''SELECT p.*,count(s.id) AS count FROM pools p
             LEFT JOIN pool_samples ps ON p.id=ps.pool_id LEFT JOIN samples s ON s.id=ps.sample_id AND s.active=1
             GROUP BY p.id ORDER BY p.name''')]
    return {'pools':pools,'active_pool_ids':ids,'sample_ids':members}

def select(db, ids):
    ids = sorted(set(ids))
    existing = {r[0] for r in db.execute('SELECT id FROM pools')}
    if any(i not in existing for i in ids): raise ValueError('Unknown pool')
    with db:
        db.execute("UPDATE settings SET value=? WHERE key='active_pools'",(json.dumps(ids),))
    return state(db)

def create(db, name, kind, roots=()):
    name = name.strip()
    if not name: raise ValueError('A pool name is required')
    if kind not in ('folder','manual'): raise ValueError('Unknown pool kind')
    roots = sorted({str(Path(p).expanduser().resolve()) for p in roots})
    if kind == 'folder' and (not roots or any(not Path(p).is_dir() for p in roots)):
        raise ValueError('Folder pools require existing directories')
    if kind == 'manual' and roots: raise ValueError('Manual pools do not have folder roots')
    with db:
        pid = db.execute('INSERT INTO pools(name,kind) VALUES(?,?)',(name,kind)).lastrowid
        db.executemany('INSERT INTO pool_roots VALUES(?,?)',[(pid,p) for p in roots])
    return pid

def rescan(db_path, pid):
    from .index import scan
    db = connect(db_path)
    try:
        pool = db.execute('SELECT * FROM pools WHERE id=?',(pid,)).fetchone()
        if pool is None or pool['kind'] != 'folder': raise ValueError('Choose a folder-backed pool')
        roots = [r[0] for r in db.execute('SELECT path FROM pool_roots WHERE pool_id=?',(pid,))]
        space = db.execute("SELECT detail FROM spaces WHERE name='timbral'").fetchone()
        detail = json.loads(space[0]) if space else {}
    finally: db.close()
    return scan(db_path, roots, pool_id=pid, clap=detail.get('drum_method') != 'rough envelope heuristic',
                one_shot=detail.get('one_shot_threshold',.35),drum=detail.get('drum_threshold',.5),
                cache_dir=str(cache_dir()/'models'))
