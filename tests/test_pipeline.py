import json
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from drum_atlas.demo import generate
from drum_atlas.analysis import analyze
from drum_atlas.index import scan,neighbors
from drum_atlas.store import connect
from drum_atlas.server import create_app

def quiet(*args,**kwargs):pass

def test_envelope_separates_hits_and_loops(tmp_path):
    generate(tmp_path)
    assert analyze(tmp_path/'kick_0.wav')['one_shot']>.7
    assert analyze(tmp_path/'loop.wav')['one_shot']<.3
    assert analyze(tmp_path/'sustained_tone.wav')['one_shot']<.45
    assert analyze(tmp_path/'silence.wav')['one_shot']==0

def test_cache_changes_missing_corrupt_and_api(tmp_path):
    root=tmp_path/'samples';generate(root)
    (root/'broken.wav').write_bytes(b'not audio')
    dbpath=tmp_path/'index.sqlite'
    first=scan(dbpath,[root],clap=False,progress=quiet)
    assert first['accepted']>=12 and first['errors']==1
    second=scan(dbpath,[root],clap=False,progress=quiet)
    assert second['analyzed']==0 and second['cached']==21
    f=root/'kick_0.wav';x,sr=sf.read(f);sf.write(f,x*.5,sr)
    (root/'hat_0.wav').unlink()
    third=scan(dbpath,[root],clap=False,progress=quiet)
    assert third['analyzed']==1
    db=connect(dbpath)
    assert db.execute('SELECT active FROM samples WHERE path=?',(str(root/'hat_0.wav'),)).fetchone()[0]==0
    client=TestClient(create_app(dbpath))
    library=client.get('/api/library').json()
    accepted=[s for s in library['samples'] if s['coords']]
    sid=accepted[0]['id']
    ns=client.get(f'/api/neighbors/{sid}?space=timbral').json()
    assert sid not in [n['id'] for n in ns]
    before=neighbors(db,'timbral',sid)
    db.execute('UPDATE points SET x=999,y=-999');db.commit()
    assert neighbors(db,'timbral',sid)==before  # 2-D coordinates never drive similarity.
    audio=client.get(f'/api/audio/{sid}')
    assert audio.status_code==200 and audio.content[:4]==b'RIFF'
    assert client.get('/api/audio/99999').status_code==404
    assert client.get('/api/neighbors/99999?space=timbral').status_code==404
    assert client.get('/api/neighbors/1?space=unknown').status_code==400
    assert client.get('/').status_code==200
    db.close()

def test_invalid_root_does_not_prune(tmp_path):
    import pytest
    root=tmp_path/'samples';generate(root)
    path=tmp_path/'index.sqlite';scan(path,[root],clap=False,progress=quiet)
    with pytest.raises(ValueError):scan(path,[tmp_path/'absent'],clap=False,progress=quiet)
    db=connect(path);assert db.execute('SELECT count(*) FROM samples WHERE active=1').fetchone()[0]==21;db.close()

def test_clap_stage_cache_and_matched_spaces(tmp_path,monkeypatch):
    import drum_atlas.index as idx
    class FakeClap:
        VERSION='test-model'
        calls=0
        def __init__(self,*args):pass
        def embed(self,path):
            FakeClap.calls+=1
            v=np.zeros(512,dtype=np.float32);v[0]=1
            return v,.1 if 'snare' in str(path) else .9,{'prompt':'test'}
    monkeypatch.setattr(idx,'ClapEmbedder',FakeClap)
    root=tmp_path/'samples';root.mkdir()
    sr=24000;t=np.arange(sr)/sr
    for name in ['kick','snare','hat']:
        sf.write(root/f'{name}.wav',np.sin(2*np.pi*80*t)*np.exp(-t*12),sr)
    path=tmp_path/'db.sqlite'
    result=idx.scan(path,[root],progress=quiet)
    assert result['embedded']==3 and result['accepted']==2
    result=idx.scan(path,[root],progress=quiet)
    assert result['embedded']==0 and FakeClap.calls==3
    db=connect(path)
    assert {r[0] for r in db.execute("SELECT sample_id FROM points WHERE space='clap'")}=={r[0] for r in db.execute("SELECT sample_id FROM points WHERE space='timbral'")}
    assert len(db.execute("SELECT vector FROM points WHERE space='clap' LIMIT 1").fetchone()[0])==512*4
    db.close()
    result=idx.scan(path,[root],drum=.05,progress=quiet)
    assert result['embedded']==0 and result['accepted']==3
