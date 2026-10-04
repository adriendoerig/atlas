from fastapi.testclient import TestClient
from drum_atlas.server import create_app
from drum_atlas.store import connect
from drum_atlas import pools


def test_timing_modes_relay_reconnect_and_one_shot_gate(tmp_path):
    with TestClient(create_app(tmp_path/'db.sqlite')) as client:
        with client.websocket_connect('/api/sync?role=browser') as browser:
            assert browser.receive_json()['scrub_mode']=='one-shot'
            browser.receive_json()
            with client.websocket_connect('/api/sync?role=live') as live:
                live.receive_json();live.receive_json();browser.receive_json()
                for mode in ('16n','8n','4n'):
                    browser.send_json({'type':'scrub_mode','mode':mode})
                    assert live.receive_json()=={'type':'scrub_mode','mode':mode}
                    browser.send_json({'type':'scrub','active':True})
                    assert live.receive_json()=={'type':'scrub','active':True}
                # Invalid modes don't alter the clock state or produce relay traffic.
                browser.send_json({'type':'scrub_mode','mode':'invalid'})
                live.send_json({'type':'scrub_mode','mode':'one-shot'})
                assert browser.receive_json()=={'type':'scrub_mode','mode':'one-shot'}
                browser.send_json({'type':'scrub','active':True})
                assert live.receive_json()=={'type':'scrub','active':False}
                with client.websocket_connect('/api/sync') as reconnect:
                    state=reconnect.receive_json()
                    assert state['scrub_mode']=='one-shot'
                    assert not state['scrub_sync'] and not state['scrub_active']


def test_select_all_pools_distinct_union_and_empty_library(tmp_path):
    path=tmp_path/'db.sqlite';client=TestClient(create_app(path))
    assert client.put('/api/pools/active/all').json()['sample_ids']==[]
    db=connect(path)
    db.executemany('INSERT INTO samples(id,path) VALUES(?,?)',[(1,'/a.wav'),(2,'/b.wav'),(3,'/c.wav')]);db.commit()
    a=pools.create(db,'A','manual');b=pools.create(db,'B','manual')
    db.executemany('INSERT INTO pool_samples VALUES(?,?)',[(a,1),(a,2),(b,2),(b,3)]);db.commit()
    result=client.put('/api/pools/active/all').json()
    assert result['sample_ids']==[1,2,3] and set(result['active_pool_ids'])=={a,b}
    assert pools.state(db)['active_pool_ids']==[a,b]
    db.close()
