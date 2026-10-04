import json
import sqlite3
from pathlib import Path
import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient
from drum_atlas import pools
from drum_atlas.store import connect, SCHEMA
from drum_atlas.index import scan
from drum_atlas.server import create_app


def quiet(*args, **kwargs): pass

def hit(path):
    t=np.arange(24000)/24000
    sf.write(path,np.sin(2*np.pi*80*t)*np.exp(-t*12),24000)

def test_legacy_migration_is_idempotent(tmp_path):
    path=tmp_path/'legacy.sqlite'
    db=sqlite3.connect(path);db.executescript(SCHEMA)
    db.execute("INSERT INTO samples(id,path,features,clap) VALUES(7,?,'[1,2]',?)",(str(tmp_path/'a.wav'),b'unchanged'))
    db.commit();db.close()
    for _ in range(2):
        db=connect(path)
        assert pools.state(db)['sample_ids']==[7]
        assert pools.state(db)['pools'][0]['name']=='Polaroit'
        assert db.execute('SELECT clap FROM samples').fetchone()[0]==b'unchanged'
        assert db.execute('SELECT count(*) FROM pools').fetchone()[0]==1
        db.close()

def test_union_delete_and_persistence(tmp_path):
    path=tmp_path/'db.sqlite';db=connect(path)
    db.executemany('INSERT INTO samples(id,path) VALUES(?,?)',[(i,str(tmp_path/f'{i}.wav')) for i in range(1,4)])
    db.commit()
    a=pools.create(db,'A','manual');b=pools.create(db,'B','manual')
    db.executemany('INSERT INTO pool_samples VALUES(?,?)',[(a,1),(a,2),(b,2),(b,3)]);db.commit()
    assert pools.select(db,[a,b])['sample_ids']==[1,2,3]
    assert pools.select(db,[])['sample_ids']==[]
    pools.select(db,[a,b]);db.close()
    c=TestClient(create_app(path))
    assert c.get('/api/pools').json()['active_pool_ids']==[a,b]
    assert c.delete(f'/api/pools/{a}').status_code==200
    assert c.get('/api/pools').json()['sample_ids']==[2,3]
    assert len(c.get('/api/library').json()['samples'])==3
    assert c.put('/api/pools/active',json={'ids':[999]}).status_code==400
    assert c.put(f'/api/pools/{b}/members',json={'ids':[999]}).status_code==400
    assert c.get('/api/pools').json()['sample_ids']==[2,3] # invalid replacement rolled back

def test_shared_cache_rescan_and_projection(tmp_path,monkeypatch):
    import drum_atlas.index as idx
    class FakeClap:
        VERSION='pool-test'; calls=0
        def __init__(self,*args): pass
        def embed(self,path):
            FakeClap.calls+=1
            return np.ones(512,dtype=np.float32),.9,{}
    monkeypatch.setattr(idx,'ClapEmbedder',FakeClap)
    root=tmp_path/'sounds';root.mkdir();hit(root/'a.wav');hit(root/'b.wav')
    path=tmp_path/'db.sqlite';db=connect(path)
    a=pools.create(db,'A','folder',[root]);b=pools.create(db,'B','folder',[root]);db.close()
    first=scan(path,[root],pool_id=a,progress=quiet)
    second=scan(path,[root/'.'],pool_id=b,progress=quiet)
    assert first['embedded']==2 and second['embedded']==0 and second['analyzed']==0
    assert second['cached']==2 and FakeClap.calls==2
    db=connect(path)
    before=[tuple(r) for r in db.execute('SELECT * FROM points')]
    assert pools.select(db,[a,b])['sample_ids']==[1,2]
    pools.select(db,[b])
    assert [tuple(r) for r in db.execute('SELECT * FROM points')]==before
    db.close()
    (root/'a.wav').unlink();hit(root/'c.wav')
    x,sr=sf.read(root/'b.wav');sf.write(root/'b.wav',x*.5,sr)
    third=scan(path,[root],pool_id=b,progress=quiet)
    assert third['analyzed']==2 and third['embedded']==2
    db=connect(path);assert len(pools.state(db)['sample_ids'])==2
    members=[r[0] for r in db.execute('SELECT sample_id FROM pool_samples WHERE pool_id=?',(b,))]
    assert 1 not in members
    # An invalid/unmounted root must not clear memberships.
    with pytest.raises(ValueError):scan(path,[tmp_path/'missing'],pool_id=b,progress=quiet)
    assert [r[0] for r in db.execute('SELECT sample_id FROM pool_samples WHERE pool_id=?',(b,))]==members
    db.execute("UPDATE samples SET analysis_version='old' WHERE active=1");db.commit();db.close()
    assert scan(path,[root],pool_id=b,progress=quiet)['analyzed']==2

def test_api_and_websocket_pool_sync(tmp_path):
    path=tmp_path/'db.sqlite'
    with TestClient(create_app(path)) as c:
        with c.websocket_connect('/api/sync?role=live') as ws:
            assert ws.receive_json()['pool_state']['sample_ids']==[]
            assert ws.receive_json()['type']=='presence'
            r=c.post('/api/pools',json={'name':'Manual','kind':'manual'})
            assert r.status_code==201
            pid=r.json()['id']
            assert ws.receive_json()['pool_state']['active_pool_ids']==[pid]
            c.put('/api/pools/active',json={'ids':[]})
            assert ws.receive_json()['pool_state']['active_pool_ids']==[]
            with c.websocket_connect('/api/sync?role=browser') as browser:
                browser.receive_json();browser.receive_json();ws.receive_json()
                for message in [{'type':'mode','mode':'timbral'},{'type':'select','id':4,'scrub':True},
                                {'type':'scrub_sync','enabled':True},{'type':'scrub','active':True}]:
                    browser.send_json(message)
                    assert ws.receive_json()==message
        assert c.get('/?view=live').status_code==200
        assert c.post('/api/pools',json={'name':'Missing','roots':[str(tmp_path/'missing')]}).status_code==400

def test_failed_embedding_keeps_previous_membership(tmp_path,monkeypatch):
    import drum_atlas.index as idx
    root=tmp_path/'sounds';root.mkdir();hit(root/'a.wav')
    path=tmp_path/'db.sqlite';db=connect(path)
    pid=pools.create(db,'Drums','folder',[root]);db.close()
    scan(path,[root],pool_id=pid,clap=False,progress=quiet)
    hit(root/'b.wav')
    class BrokenClap:
        VERSION='broken'
        def __init__(self,*args): raise RuntimeError('Model unavailable')
    monkeypatch.setattr(idx,'ClapEmbedder',BrokenClap)
    with pytest.raises(RuntimeError):scan(path,[root],pool_id=pid,progress=quiet)
    db=connect(path)
    assert db.execute('SELECT count(*) FROM pool_samples WHERE pool_id=?',(pid,)).fetchone()[0]==1
    db.close()

def test_cli_scan_creates_reusable_pool(tmp_path,monkeypatch):
    from drum_atlas.cli import main
    root=tmp_path/'sounds';root.mkdir();hit(root/'a.wav')
    path=tmp_path/'db.sqlite'
    monkeypatch.setattr('sys.argv',['drum-atlas','--db',str(path),'scan',str(root),'--pool','CLI pool','--baseline-only'])
    main();main()
    db=connect(path)
    result=pools.state(db)
    assert len(result['pools'])==1 and result['pools'][0]['name']=='CLI pool'
    assert len(result['sample_ids'])==1
    db.close()
