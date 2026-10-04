import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from drum_atlas import pools, projections
from drum_atlas.store import connect
from drum_atlas.server import create_app


def test_subset_cache_global_restore_and_invalidation(tmp_path,monkeypatch):
    import umap
    calls=[]
    class Layout:
        def __init__(self,**kwargs): self.kwargs=kwargs
        def fit_transform(self,matrix):
            calls.append((self.kwargs,matrix.copy()))
            return np.column_stack([np.arange(len(matrix)),np.arange(len(matrix))**2])
    monkeypatch.setattr(umap,'UMAP',Layout)
    path=tmp_path/'db.sqlite';db=connect(path)
    for i in range(1,7):
        db.execute('INSERT INTO samples(id,path,features) VALUES(?,?,?)',(i,str(tmp_path/f'{i}.wav'),'[1,2]'))
    for mode,metric in [('timbral','euclidean'),('clap','cosine')]:
        db.execute('INSERT INTO spaces VALUES(?,?,?,?)',(mode,'original',metric,json.dumps({'projection':'UMAP'})))
        for i in range(1,7):
            db.execute('INSERT INTO points VALUES(?,?,?,?,?)',(mode,i,i*10,i*20,np.array([i,1,2],dtype='<f4').tobytes()))
    db.commit()
    a=pools.create(db,'A','manual');b=pools.create(db,'B','manual')
    db.executemany('INSERT INTO pool_samples VALUES(?,?)',[(a,i) for i in [1,2,3]]+[(b,i) for i in [3,4]])
    db.commit();pools.select(db,[a,b])
    original=[tuple(r) for r in db.execute('SELECT * FROM points')]
    client=TestClient(create_app(path))
    response=client.post('/api/projection/selection')
    assert response.status_code==200 and not response.json()['cached']
    assert len(calls)==2 and all(matrix.shape==(4,3) for _,matrix in calls)
    library=client.get('/api/library').json()
    assert library['projection']['scope']=='selection'
    assert {s['id'] for s in library['samples'] if s['coords']}=={1,2,3,4}
    assert client.post('/api/projection/selection').json()['cached']
    assert len(calls)==2
    assert [tuple(r) for r in db.execute('SELECT * FROM points')]==original
    assert client.post('/api/projection/global').status_code==200
    library=client.get('/api/library').json()
    assert library['projection']['scope']=='global'
    assert library['samples'][0]['coords']['timbral']==[10,20]
    client.post('/api/projection/selection')
    client.put('/api/pools/active',json={'ids':[a]})
    assert client.get('/api/library').json()['projection']['scope']=='global'
    # Small selections use a finite layout without UMAP.
    assert client.post('/api/projection/selection').status_code==200
    assert len(calls)==2
    db.execute("UPDATE spaces SET signature='changed'");db.commit()
    assert projections.current(db)['scope']=='global'
    client.put('/api/pools/active',json={'ids':[]})
    assert client.post('/api/projection/selection').status_code==400
    db.close()
