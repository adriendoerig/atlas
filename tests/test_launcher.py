import json
import runpy
from pathlib import Path
from fastapi.testclient import TestClient
from drum_atlas.server import create_app


def test_stop_refuses_reused_pid(tmp_path,monkeypatch):
    helper=runpy.run_path(str(Path(__file__).parents[1]/'server_control.py'))
    stop=helper['stop']
    stop.__globals__['identity']=lambda pid:'a different process'
    monkeypatch.setattr('os.kill',lambda *a: (_ for _ in ()).throw(AssertionError('must not kill')))
    record=tmp_path/'process.json';record.write_text(json.dumps({'pid':123,'identity':'old process'}))
    stop(record)
    assert not record.exists()


def test_ui_assets_do_not_reuse_stale_cache(tmp_path):
    client=TestClient(create_app(tmp_path/'db.sqlite'))
    for url in ['/?view=live','/static/app.js?v=live-layout-3','/static/style.css?v=live-layout-3','/api/library']:
        response=client.get(url)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
