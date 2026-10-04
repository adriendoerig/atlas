"""Cached subset layouts; original features, global points and distances are untouched."""
import hashlib
import json
import numpy as np
from . import pools
from .store import connect


def signature(db):
    state = pools.state(db)
    spaces = [tuple(r) for r in db.execute('SELECT name,signature FROM spaces ORDER BY name')]
    return hashlib.sha256(json.dumps(['subset-1', state['active_pool_ids'], state['sample_ids'], spaces]).encode()).hexdigest()


def current(db):
    row = db.execute("SELECT value FROM settings WHERE key='projection'").fetchone()
    key = row[0] if row else 'global'
    if key != 'global' and key == signature(db):
        cached = db.execute('SELECT layouts FROM projections WHERE key=?',(key,)).fetchone()
        if cached:
            return {'scope':'selection','key':key,'layouts':json.loads(cached[0])}
    return {'scope':'global','key':'global','layouts':{}}


def activate_global(db):
    with db:
        db.execute("INSERT OR REPLACE INTO settings VALUES('projection','global')")


def embed_selection(db_path):
    db = connect(db_path)
    try:
        key = signature(db)
        cached = db.execute('SELECT 1 FROM projections WHERE key=?',(key,)).fetchone()
        if not cached:
            ids = pools.state(db)['sample_ids']
            layouts = {}
            for space in db.execute('SELECT name,metric FROM spaces').fetchall():
                rows = db.execute('SELECT sample_id,vector FROM points WHERE space=? AND sample_id IN '
                                  '(SELECT value FROM json_each(?)) ORDER BY sample_id',
                                  (space['name'],json.dumps(ids))).fetchall()
                if not rows:
                    layouts[space['name']] = {}
                    continue
                matrix = np.array([np.frombuffer(r['vector'],dtype='<f4') for r in rows])
                if len(rows) >= 4:
                    import umap
                    coords = umap.UMAP(n_neighbors=min(15,len(rows)-1),metric=space['metric'],
                                       init='random',random_state=42,min_dist=.12,n_jobs=1).fit_transform(matrix)
                else:
                    coords = np.column_stack([np.arange(len(rows)),np.zeros(len(rows))])
                layouts[space['name']] = {str(r['sample_id']):[float(x),float(y)] for r,(x,y) in zip(rows,coords)}
            if not any(layouts.values()):
                raise ValueError('Select a pool containing mapped samples first.')
            with db:
                db.execute('INSERT OR REPLACE INTO projections(key,layouts) VALUES(?,?)',(key,json.dumps(layouts)))
                # Bound the layout cache; evicted layouts can be rebuilt from the same features.
                db.execute('DELETE FROM projections WHERE rowid NOT IN (SELECT rowid FROM projections ORDER BY rowid DESC LIMIT 20)')
        # A concurrent CLI scan must not activate a layout for stale library contents.
        if signature(db) != key:
            raise ValueError('The library changed during embedding. Please try again.')
        with db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('projection',?)",(key,))
        return {'cached':bool(cached),'scope':'selection','key':key}
    finally:
        db.close()
