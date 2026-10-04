import asyncio
import sqlite3
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from . import pools, projections
from .paths import database_path
import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

import subprocess
import sys

from .store import connect
from .index import neighbors

STATIC = Path(__file__).parent / 'static'


class PoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = 'folder'
    roots: list[str] = Field(default_factory=list)

class PoolSelection(BaseModel):
    ids: list[int]

def create_app(db_path=None):
    db_path = db_path or database_path()
    app = FastAPI(title='Drum Atlas')
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=['127.0.0.1', 'localhost', 'testserver'],
    )
    @app.middleware('http')
    async def fresh_ui(request, call_next):
        response = await call_next(request)
        if request.url.path == '/' or request.url.path.startswith('/static/') or request.url.path == '/api/library':
            response.headers['Cache-Control'] = 'no-store'
        return response

    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    # Lightweight in-memory relay between the full browser UI and the
    # ?view=live jweb~ UI. Nothing is persisted to disk.
    sync_clients = {}
    live_heartbeats = {}
    LIVE_HEARTBEAT_TTL = 3.0
    mutation_lock = asyncio.Lock()

    def ableton_running():
        """
        A Max/jweb process can survive after Ableton closes, so window.max
        alone is not proof that Live is actually available.

        On macOS, look specifically for the main executable inside an
        Ableton Live .app bundle.
        """
        if sys.platform != 'darwin':
            # For now retain heartbeat-only behaviour on other platforms.
            return True

        try:
            result = subprocess.run(
                ['ps', '-axo', 'command='],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )

            return any(
                'Ableton Live ' in line
                and '.app/Contents/MacOS/Live' in line
                for line in result.stdout.splitlines()
            )

        except Exception:
            # If process detection itself fails, don't create a false
            # "Live connected" state.
            return False

    def pool_state():
        db = connect(db_path)
        try: return pools.state(db)
        finally: db.close()
    sync_state = {
        'selected': None,
        'mode': None,
        'scrub_sync': False,
        'scrub_mode': 'one-shot',
        'scrub_active': False,
    }

    async def send_presence():
        now = asyncio.get_running_loop().time()

        live_count = 0

        if ableton_running():
            live_count = sum(
                1
                for ws, role in sync_clients.items()
                if role == 'live'
                and now - live_heartbeats.get(
                    ws,
                    float('-inf')
                ) < LIVE_HEARTBEAT_TTL
            )

        message = {
            'type': 'presence',
            'live': live_count,
        }

        dead = []

        for ws in list(sync_clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            sync_clients.pop(ws, None)
            live_heartbeats.pop(ws, None)

    async def relay(message, exclude=None):
        dead = []
        for ws in list(sync_clients):
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sync_clients.pop(ws, None)
        if dead:
            await send_presence()

    @app.websocket('/api/sync')
    async def sync(websocket: WebSocket):
        role = websocket.query_params.get('role', 'browser')
        if role not in ('browser', 'live'):
            role = 'browser'

        await websocket.accept()
        sync_clients[websocket] = role

        # Give a newly opened/reconnected view the current shared state.
        await websocket.send_json({
            'type': 'state',
            'pool_state': pool_state(),
            'selected': sync_state['selected'],
            'mode': sync_state['mode'],
            'scrub_sync': sync_state['scrub_sync'],
            'scrub_mode': sync_state['scrub_mode'],
            'scrub_active': sync_state['scrub_active'],
        })
        await send_presence()

        try:
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    continue

                kind = message.get('type')

                if kind == 'live_heartbeat':
                    if role == 'live':
                        live_heartbeats[websocket] = asyncio.get_running_loop().time()
                        await send_presence()

                elif kind == 'presence_query':
                    await send_presence()

                elif kind == 'select':
                    try:
                        sample_id = int(message.get('id'))
                    except (TypeError, ValueError):
                        continue

                    sync_state['selected'] = sample_id
                    await relay({
                        'type': 'select',
                        'id': sample_id,
                        'scrub': bool(message.get('scrub', False)),
                    }, exclude=websocket)

                elif kind == 'mode':
                    next_mode = message.get('mode')
                    if next_mode not in ('clap', 'timbral'):
                        continue

                    sync_state['mode'] = next_mode
                    await relay({
                        'type': 'mode',
                        'mode': next_mode,
                    }, exclude=websocket)

                elif kind == 'play':
                    try:
                        sample_id = int(message.get('id'))
                    except (TypeError, ValueError):
                        continue

                    await relay({
                        'type': 'play',
                        'id': sample_id,
                    }, exclude=websocket)

                elif kind == 'scrub_mode':
                    next_mode = message.get('mode')
                    if next_mode not in ('one-shot','16n','8n','4n'):
                        continue
                    sync_state['scrub_mode'] = next_mode
                    sync_state['scrub_sync'] = next_mode != 'one-shot'
                    sync_state['scrub_active'] = False
                    await relay({'type':'scrub_mode','mode':next_mode}, exclude=websocket)

                elif kind == 'scrub_sync':
                    enabled = bool(message.get('enabled', False))
                    sync_state['scrub_sync'] = enabled
                    sync_state['scrub_mode'] = (sync_state['scrub_mode'] if sync_state['scrub_mode'] != 'one-shot' else '16n') if enabled else 'one-shot'
                    if not enabled: sync_state['scrub_active'] = False
                    await relay({
                        'type': 'scrub_sync',
                        'enabled': enabled,
                    }, exclude=websocket)

                elif kind == 'scrub':
                    active = bool(message.get('active', False)) and sync_state['scrub_sync']
                    sync_state['scrub_active'] = active
                    await relay({
                        'type': 'scrub',
                        'active': active,
                    }, exclude=websocket)

        except WebSocketDisconnect:
            pass
        finally:
            sync_clients.pop(websocket, None)
            live_heartbeats.pop(websocket, None)

            # A scrub gesture cannot survive a disconnected controller.
            # Reset it so a reconnect never leaves the quantized metro running.
            if sync_state['scrub_active']:
                sync_state['scrub_active'] = False
                await relay({
                    'type': 'scrub',
                    'active': False,
                })

            await send_presence()

    async def notify_pools(library_changed=False):
        library_changed = True  # Pool changes can invalidate a subset layout.
        result = pool_state()
        if sync_state['selected'] is not None and sync_state['selected'] not in result['sample_ids']:
            sync_state['selected'] = None
            sync_state['scrub_active'] = False
            await relay({'type':'scrub', 'active':False})
        await relay({'type':'pools', 'pool_state':result, 'library_changed':library_changed})
        return result

    @app.post('/api/projection/selection')
    async def embed_selection():
        async with mutation_lock:
            try: result = await run_in_threadpool(projections.embed_selection, db_path)
            except ValueError as e: raise HTTPException(400, str(e))
            await notify_pools(True)
            return result

    @app.post('/api/projection/global')
    async def global_projection():
        async with mutation_lock:
            db = connect(db_path)
            try: projections.activate_global(db)
            finally: db.close()
            await notify_pools(True)
            return {'scope':'global','key':'global'}

    @app.get('/api/pools')
    def get_pools():
        return pool_state()

    @app.put('/api/pools/active/all')
    async def select_all_pools():
        async with mutation_lock:
            db = connect(db_path)
            try: pools.select(db, [r[0] for r in db.execute('SELECT id FROM pools')])
            finally: db.close()
            return await notify_pools()

    @app.put('/api/pools/active')
    async def set_pools(body: PoolSelection):
        async with mutation_lock:
            db = connect(db_path)
            try: pools.select(db, body.ids)
            except ValueError as e: raise HTTPException(400,str(e))
            finally: db.close()
            return await notify_pools()

    @app.post('/api/pools', status_code=201)
    async def create_pool(body: PoolCreate):
        async with mutation_lock:
            db = connect(db_path)
            try: pid = pools.create(db,body.name,body.kind,body.roots)
            except (ValueError,sqlite3.IntegrityError) as e: raise HTTPException(400,str(e))
            finally: db.close()
            # The empty pool is saved first so failed scans can be retried.
            try:
                if body.kind == 'folder': await run_in_threadpool(pools.rescan,db_path,pid)
            except Exception as e:
                await notify_pools(True)
                raise HTTPException(422,f'Pool {pid} saved; scan failed, retry Rescan: {e}')
            db = connect(db_path)
            try: pools.select(db,pools.state(db)['active_pool_ids']+[pid])
            finally: db.close()
            return {'id':pid, **await notify_pools(True)}

    @app.post('/api/pools/{pid}/rescan')
    async def rescan_pool(pid: int):
        async with mutation_lock:
            try: stats = await run_in_threadpool(pools.rescan,db_path,pid)
            except Exception as e:
                await notify_pools(True)
                raise HTTPException(422,str(e))
            return {'stats':stats, **await notify_pools(True)}

    @app.delete('/api/pools/{pid}')
    async def delete_pool(pid: int):
        async with mutation_lock:
            db = connect(db_path)
            try:
                with db:
                    if not db.execute('DELETE FROM pools WHERE id=?',(pid,)).rowcount:
                        raise HTTPException(404,'Pool not found')
                    pools.select(db,[i for i in pools.state(db)['active_pool_ids'] if i != pid])
            finally: db.close()
            return await notify_pools()

    @app.put('/api/pools/{pid}/members')
    async def curate_pool(pid: int, body: PoolSelection):
        async with mutation_lock:
            db = connect(db_path)
            try:
                row = db.execute('SELECT kind FROM pools WHERE id=?',(pid,)).fetchone()
                if row is None: raise HTTPException(404,'Pool not found')
                if row[0] != 'manual': raise HTTPException(400,'Only manual pools can be curated')
                with db:
                    db.execute('DELETE FROM pool_samples WHERE pool_id=?',(pid,))
                    db.executemany('INSERT INTO pool_samples VALUES(?,?)',[(pid,i) for i in set(body.ids)])
            except sqlite3.IntegrityError: raise HTTPException(400,'Unknown sample')
            finally: db.close()
            return await notify_pools()

    @app.get('/')
    def home():
        return FileResponse(STATIC / 'index.html')

    @app.get('/api/library')
    def library():
        db = connect(db_path)
        try:
            spaces = {
                r['name']: json.loads(r['detail'])
                for r in db.execute('SELECT * FROM spaces')
            }
            points = {
                name: {
                    r['sample_id']: [r['x'], r['y']]
                    for r in db.execute(
                        'SELECT * FROM points WHERE space=?',
                        (name,),
                    )
                }
                for name in spaces
            }
            projection = projections.current(db)
            if projection['scope'] == 'selection':
                points = {name:{int(sid):xy for sid,xy in layout.items()}
                          for name,layout in projection['layouts'].items()}
                for name,detail in spaces.items():
                    count = len(points.get(name,{}))
                    detail['projection'] = 'UMAP' if count >= 4 else 'small-set layout'
            samples = []
            for r in db.execute('SELECT * FROM samples WHERE active=1 ORDER BY path'):
                samples.append(
                    {k: r[k] for k in [
                        'id', 'path', 'duration', 'sample_rate', 'channels',
                        'one_shot', 'drum_heuristic', 'drum_clap', 'error',
                    ]}
                    | {
                        'name': Path(r['path']).name,
                        'detail': json.loads(r['detail'] or '{}'),
                        'clap_detail': json.loads(r['clap_detail'] or '{}'),
                        'coords': {
                            s: p[r['id']]
                            for s, p in points.items()
                            if r['id'] in p
                        },
                    }
                )
            return {'spaces': spaces, 'samples': samples, 'pool_state': pools.state(db), 'projection': {k:projection[k] for k in ('scope','key')}}
        finally:
            db.close()

    @app.get('/api/neighbors/{sample_id}')
    def similar(
        sample_id: int,
        space: str = 'clap',
        k: int = Query(8, ge=1, le=50),
        explicit: bool = False,
    ):
        # Nearest-neighbor lookup is deliberately opt-in. This protects the
        # interactive scrub path (and the server from stale browser tabs) from
        # accidentally launching expensive distance calculations.
        if not explicit:
            return []

        db = connect(db_path)
        try:
            if space not in ('clap', 'timbral'):
                raise HTTPException(400, 'Unknown space')
            try:
                # Distance calculations scale with the active pool selection,
                # not with the entire globally analysed library.
                allowed = pools.state(db)['sample_ids']
                return neighbors(db, space, sample_id, k, allowed_ids=allowed)
            except KeyError:
                raise HTTPException(404, 'Sample is not in this map')
        finally:
            db.close()

    @app.get('/api/audio/{sample_id}')
    def audio(sample_id: int, convert: bool = Query(False)):
        db = connect(db_path)
        row = db.execute(
            'SELECT path,mtime_ns,size,duration FROM samples '
            'WHERE id=? AND active=1 AND error IS NULL',
            (sample_id,),
        ).fetchone()
        db.close()

        if row is None:
            raise HTTPException(404, 'Sample not found')

        path = Path(row['path'])
        if not path.is_file():
            raise HTTPException(404, 'File is missing; rescan its folder')

        st = path.stat()
        if st.st_mtime_ns != row['mtime_ns'] or st.st_size != row['size']:
            raise HTTPException(409, 'File changed; rescan before auditioning')

        # Fast path: serve ordinary short samples exactly as they are on disk.
        # This removes the expensive server-side decode -> NumPy -> WAV encode
        # round trip from the hot audition path. The browser can request
        # ?convert=1 if its WebAudio decoder cannot read the original format.
        if not convert and (row['duration'] is None or row['duration'] <= 12):
            return FileResponse(
                path,
                headers={'Cache-Control': 'no-store'},
            )

        # Compatibility / long-file fallback: preserve the previous behavior.
        try:
            with sf.SoundFile(path) as f:
                rate = f.samplerate
                x = f.read(
                    min(len(f), rate * 12),
                    dtype='float32',
                    always_2d=True,
                )
            x = np.nan_to_num(x)
            if x.shape[1] > 2:
                x = x[:, :2]

            # Peak ceiling only; preserve quiet samples. Playback gain is in the browser.
            x = x / max(1.0, float(np.max(np.abs(x))) if x.size else 1.0)

            out = io.BytesIO()
            sf.write(out, x, rate, format='WAV', subtype='PCM_16')
            return Response(
                out.getvalue(),
                media_type='audio/wav',
                headers={'Cache-Control': 'no-store'},
            )
        except Exception as e:
            raise HTTPException(422, f'Cannot decode sample: {e}')

    return app
