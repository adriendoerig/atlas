import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .store import connect
from .index import neighbors

STATIC = Path(__file__).parent / 'static'


def create_app(db_path):
    app = FastAPI(title='Drum Atlas')
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=['127.0.0.1', 'localhost', 'testserver'],
    )
    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    # Lightweight in-memory relay between the full browser UI and the
    # ?view=live jweb~ UI. Nothing is persisted to disk.
    sync_clients = {}
    sync_state = {
        'selected': None,
        'mode': None,
        'scrub_sync': False,
        'scrub_active': False,
    }

    async def send_presence():
        live_count = sum(1 for role in sync_clients.values() if role == 'live')
        message = {'type': 'presence', 'live': live_count}
        dead = []
        for ws in list(sync_clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sync_clients.pop(ws, None)

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
            'selected': sync_state['selected'],
            'mode': sync_state['mode'],
            'scrub_sync': sync_state['scrub_sync'],
            'scrub_active': sync_state['scrub_active'],
        })
        await send_presence()

        try:
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    continue

                kind = message.get('type')

                if kind == 'select':
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

                elif kind == 'scrub_sync':
                    enabled = bool(message.get('enabled', False))
                    sync_state['scrub_sync'] = enabled
                    await relay({
                        'type': 'scrub_sync',
                        'enabled': enabled,
                    }, exclude=websocket)

                elif kind == 'scrub':
                    active = bool(message.get('active', False))
                    sync_state['scrub_active'] = active
                    await relay({
                        'type': 'scrub',
                        'active': active,
                    }, exclude=websocket)

        except WebSocketDisconnect:
            pass
        finally:
            sync_clients.pop(websocket, None)

            # A scrub gesture cannot survive a disconnected controller.
            # Reset it so a reconnect never leaves the quantized metro running.
            if sync_state['scrub_active']:
                sync_state['scrub_active'] = False
                await relay({
                    'type': 'scrub',
                    'active': False,
                })

            await send_presence()

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
            return {'spaces': spaces, 'samples': samples}
        finally:
            db.close()

    @app.get('/api/neighbors/{sample_id}')
    def similar(sample_id: int, space: str = 'clap', k: int = Query(8, ge=1, le=50)):
        db = connect(db_path)
        try:
            if space not in ('clap', 'timbral'):
                raise HTTPException(400, 'Unknown space')
            try:
                return neighbors(db, space, sample_id, k)
            except KeyError:
                raise HTTPException(404, 'Sample is not in this map')
        finally:
            db.close()

    @app.get('/api/audio/{sample_id}')
    def audio(sample_id: int):
        db = connect(db_path)
        row = db.execute(
            'SELECT path,mtime_ns,size FROM samples '
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
