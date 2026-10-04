'use strict';

const liveView = new URLSearchParams(location.search).get('view') === 'live';
document.body.classList.toggle('live-view', liveView);
document.documentElement.classList.toggle('live-view', liveView);

const $ = (id) => document.getElementById(id);
const canvas = $('map');
const ctx = canvas.getContext('2d');

let data = { samples: [], spaces: {} };
let byId = new Map();
let mode = 'clap';
let poolState = {pools: [], active_pool_ids: [], sample_ids: []};
let poolMembers = new Set();
let selected = null;
let visible = [];
let neighborIds = [];

let zoom = 1;
let pan = [0, 0];
let points = [];
let drag = null;
let lastScrub = 0;
let lastHit = null;
let selectionVersion = 0;

let scrubTimer = null;
let pendingHit = null;

function clearScrub() {
    clearTimeout(scrubTimer);
    scrubTimer = null;
    pendingHit = null;
}

function scrub(id) {
    pendingHit = id;
    clearTimeout(scrubTimer);

    if (id == null || id === lastHit) return;

    const trigger = () => {
        if (pendingHit == null || pendingHit === lastHit) return;

        lastHit = pendingHit;
        pendingHit = null;
        lastScrub = performance.now();

        select(lastHit, true, true);
    };

    const delay = Math.max(
        0,
        +$('debounce').value - (performance.now() - lastScrub)
    );

    if (delay === 0) trigger();
    else scrubTimer = setTimeout(trigger, delay);
}

let audioCtx;
let master;
let voice = null;
let playVersion = 0;
let sequenceVersion = 0;

const buffers = new Map();

// -----------------------------------------------------------------------------
// Browser <-> Ableton/Max synchronization
// -----------------------------------------------------------------------------

let syncSocket = null;
let syncRetry = null;
let liveConnected = false;
let libraryReady = false;
let pendingSyncMessages = [];
let scrubSync = false;
let scrubActive = false;

function syncSend(message) {
    if (syncSocket && syncSocket.readyState === WebSocket.OPEN) {
        syncSocket.send(JSON.stringify(message));
    }
}

function setScrubSync(enabled, fromSync = false) {
    scrubSync = !!enabled;

    const button = $('sync16');
    if (button) {
        button.classList.toggle('active', scrubSync);
        button.setAttribute('aria-pressed', scrubSync ? 'true' : 'false');
    }

    // The jweb~ page has MaxBridge. This therefore updates the Max patch
    // whether the toggle was changed in Live or in the full browser.
    if (window.max) {
        window.max.outlet('scrubsync', scrubSync ? 1 : 0);
    }

    if (!fromSync) {
        syncSend({
            type: 'scrub_sync',
            enabled: scrubSync,
        });
    }

    // Turning quantization off should also stop a currently running scrub.
    if (!scrubSync && scrubActive) {
        setScrubActive(false, fromSync);
    }
}

function setScrubActive(active, fromSync = false) {
    const next = !!active;
    if (next === scrubActive) return;

    scrubActive = next;

    if (window.max) {
        window.max.outlet('scrub', scrubActive ? 1 : 0);
    }

    if (!fromSync) {
        syncSend({
            type: 'scrub',
            active: scrubActive,
        });
    }
}

function applySyncMessage(message) {
    if (!message || typeof message !== 'object') return;

    if (message.type === 'presence') {
        const wasConnected = liveConnected;
        liveConnected = Number(message.live || 0) > 0;

        // If the full browser was auditioning locally when Live connects,
        // stop that voice so subsequent browsing is heard only through Ableton.
        if (!liveView && liveConnected && !wasConnected && voice) {
            fade();
            $('audioStatus').textContent =
                'Live connected · auditioning through Ableton';
        }

        return;
    }

    if (!libraryReady) {
        pendingSyncMessages.push(message);
        return;
    }

    if (message.type === 'pools') {
        if (message.library_changed) { load(); }
        else { applyPoolState(message.pool_state); }
        return;
    }

    if (message.type === 'state') {
        if (message.pool_state) applyPoolState(message.pool_state);
        if (message.mode === 'clap' || message.mode === 'timbral') {
            setMode(message.mode, true);
        }

        setScrubSync(!!message.scrub_sync, true);
        setScrubActive(!!message.scrub_active, true);

        if (
            message.selected != null &&
            byId.has(Number(message.selected))
        ) {
            select(
                Number(message.selected),
                liveView,
                false,
                true
            );
        }

        return;
    }

    if (message.type === 'select') {
        const id = Number(message.id);

        if (byId.has(id)) {
            // Live auditions remote browser selections.
            // Full browser updates visually but stays silent
            // while Live is connected.
            select(
                id,
                true,
                !!message.scrub,
                true
            );
        }

        return;
    }

    if (message.type === 'mode') {
        if (
            message.mode === 'clap' ||
            message.mode === 'timbral'
        ) {
            setMode(message.mode, true);
        }

        return;
    }

    if (message.type === 'scrub_sync') {
        setScrubSync(!!message.enabled, true);
        return;
    }

    if (message.type === 'scrub') {
        setScrubActive(!!message.active, true);
        return;
    }

    if (message.type === 'play') {
        const id = Number(message.id);

        if (
            byId.has(id) &&
            (liveView || !liveConnected)
        ) {
            play(id);
        }
    }
}

function flushPendingSync() {
    const queued = pendingSyncMessages;

    pendingSyncMessages = [];

    for (const message of queued) {
        applySyncMessage(message);
    }
}

function connectSync() {
    clearTimeout(syncRetry);

    const protocol =
        location.protocol === 'https:'
            ? 'wss:'
            : 'ws:';

    const role =
        liveView
            ? 'live'
            : 'browser';

    const url =
        `${protocol}//${location.host}/api/sync?role=${role}`;

    const ws = new WebSocket(url);

    syncSocket = ws;
    ws.onopen = () => load();

    ws.onmessage = (event) => {
        try {
            applySyncMessage(
                JSON.parse(event.data)
            );
        } catch (e) {
            console.warn(
                'Drum Atlas sync message failed:',
                e
            );
        }
    };

    ws.onclose = () => {
        if (syncSocket === ws) {
            syncSocket = null;
        }

        if (!liveView) {
            liveConnected = false;
        }

        syncRetry =
            setTimeout(
                connectSync,
                1000
            );
    };

    ws.onerror = () => {
        // onclose handles reconnection.
        // Avoid surfacing transient websocket noise
        // as a sample-server error in the UI.
    };
}

function error(e) {
    const message =
        e.message ||
        String(e);

    $('error').textContent =
        /failed to fetch|load failed|networkerror/i.test(message)
            ? 'The local sample server is offline. Open Launch.command in the Drum Atlas project folder, then click Refresh index.'
            : message;

    $('error').hidden = false;
}

async function get(url) {
    const r =
        await fetch(url, {cache: 'no-store'});

    if (!r.ok) {
        let e;

        try {
            e =
                await r.json();
        } catch {}

        throw Error(
            e?.detail ||
            `Request failed (${r.status})`
        );
    }

    return r.json();
}

async function unlock() {
    if (!audioCtx) {
        audioCtx =
            new AudioContext();

        master =
            audioCtx.createGain();

        master.gain.value =
            +$('volume').value;

        master.connect(
            audioCtx.destination
        );
    }

    await audioCtx.resume();
}

function fade() {
    if (voice) {
        const old =
            voice;

        voice = null;

        old.gain.gain.cancelScheduledValues(
            audioCtx.currentTime
        );

        old.gain.gain.setValueAtTime(
            old.gain.gain.value,
            audioCtx.currentTime
        );

        old.gain.gain.linearRampToValueAtTime(
            0,
            audioCtx.currentTime + 0.012
        );

        old.src.stop(
            audioCtx.currentTime + 0.015
        );
    }
}

function stop() {
    clearScrub();

    ++playVersion;
    ++sequenceVersion;

    fade();

    $('audioStatus').textContent =
        'Stopped';
}

async function buffer(id) {
    if (buffers.has(id)) {
        const b =
            buffers.get(id);

        buffers.delete(id);
        buffers.set(id, b);

        return b;
    }

    const r =
        await fetch(
            `/api/audio/${id}`
        );

    if (!r.ok) {
        const e =
            await r.json();

        throw Error(
            e.detail
        );
    }

    const b =
        await audioCtx.decodeAudioData(
            await r.arrayBuffer()
        );

    buffers.set(
        id,
        b
    );

    if (buffers.size > 64) {
        buffers.delete(
            buffers.keys().next().value
        );
    }

    return b;
}

function waveform(b) {
    const c =
        $('wave');

    const g =
        c.getContext('2d');

    c.width =
        c.clientWidth *
        devicePixelRatio;

    c.height =
        70 *
        devicePixelRatio;

    const x =
        b.getChannelData(0);

    g.clearRect(
        0,
        0,
        c.width,
        c.height
    );

    g.fillStyle =
        '#a5c798';

    for (
        let i = 0;
        i < c.width;
        i++
    ) {
        let peak = 0;

        const start =
            Math.floor(
                i *
                x.length /
                c.width
            );

        const end =
            Math.max(
                start + 1,
                Math.floor(
                    (i + 1) *
                    x.length /
                    c.width
                )
            );

        for (
            let j = start;
            j < end;
            j++
        ) {
            peak =
                Math.max(
                    peak,
                    Math.abs(
                        x[j] || 0
                    )
                );
        }

        g.fillRect(
            i,
            c.height / 2 -
                peak *
                c.height *
                0.42,
            1,
            Math.max(
                1,
                peak *
                c.height *
                0.84
            )
        );
    }
}

async function play(
    id,
    sequence = false
) {
    if (!poolMembers.has(id)) return 0;
    if (!sequence) {
        clearScrub();
        ++sequenceVersion;
    }

    const ticket =
        ++playVersion;

    try {
        await unlock();

        $('audioStatus').textContent =
            'Loading…';

        const b =
            await buffer(id);

        if (
            ticket !==
            playVersion
        ) {
            return 0;
        }

        fade();

        const src =
            audioCtx.createBufferSource();

        const gain =
            audioCtx.createGain();

        src.buffer =
            b;

        src.connect(
            gain
        );

        gain.connect(
            master
        );

        gain.gain.setValueAtTime(
            0,
            audioCtx.currentTime
        );

        gain.gain.linearRampToValueAtTime(
            1,
            audioCtx.currentTime + 0.003
        );

        src.start();

        voice = {
            src,
            gain,
        };

        src.onended = () => {
            src.disconnect();
            gain.disconnect();

            if (
                voice?.src === src
            ) {
                voice = null;

                $('audioStatus').textContent =
                    'Ready to audition';
            }
        };

        if (
            id === selected
        ) {
            waveform(b);
        }

        $('audioStatus').textContent =
            'Playing · ' +
            byId.get(id).name;

        return b.duration;

    } catch (e) {
        if (
            ticket ===
            playVersion
        ) {
            $('audioStatus').textContent =
                'Playback failed';

            error(e);
        }

        return 0;
    }
}

function score(
    value,
    label
) {
    const el =
        document.createElement(
            'div'
        );

    el.className =
        'score';

    const b =
        document.createElement(
            'b'
        );

    b.textContent =
        value == null
            ? '—'
            : value.toFixed(2);

    el.append(
        b,
        document.createTextNode(
            label
        )
    );

    return el;
}

async function select(
    id,
    audition = true,
    fromScrub = false,
    fromSync = false
) {
    if (!fromScrub) {
        clearScrub();
    }

    if (!poolMembers.has(id)) return;
    selected =
        id;

    const s =
        byId.get(id);

    if (!s) {
        return;
    }

    const version =
        ++selectionVersion;

    $('name').textContent =
        s.name;

    $('path').textContent =
        s.path;

    $('scores').replaceChildren(
        score(
            s.one_shot,
            'ONE-SHOTNESS'
        ),
        score(
            s.drum_clap ??
                s.drum_heuristic,
            s.drum_clap == null
                ? 'PERCUSSION · HEURISTIC'
                : 'PERCUSSION · CLAP'
        )
    );

    // Compact Ableton view:
    // update filename overlay
    // if index.html provides one.
    const liveSelected =
        $('liveSelected');

    if (liveSelected) {
        liveSelected.textContent =
            s.name;
    }

    // Tell Max for Live which sample
    // is currently selected.
    if (window.max) {
        window.max.outlet(
            'selected',
            s.id,
            s.path
        );
    }

    // Only originate a sync message
    // when this selection was local.
    if (!fromSync) {
        syncSend({
            type: 'select',
            id: s.id,
            scrub: fromScrub,
        });
    }

    $('explain').textContent =
        s.error ||
        `${(s.duration || 0).toFixed(2)} s · ` +
        `${s.sample_rate || '?'} Hz · ` +
        `${s.channels || '?'} ch · ` +
        `${s.detail.onsets ?? '?'} onset(s). ` +
        `${s.clap_detail.prompt ||
            'Heuristic percussion estimate; tonal plucks can pass.'}`;

    $('neighbors').replaceChildren();

    neighborIds = [];

    $('sequence').disabled =
        true;

    draw();
    list();

    /*
     * If this is the full browser and
     * Live is connected, do NOT audition
     * locally: the Live jweb~ instance
     * will receive the sync message and
     * produce the audio through Ableton.
     */
    const quantizedScrub =
        scrubSync &&
        fromScrub &&
        (liveView || liveConnected);

    if (
        audition &&
        !quantizedScrub &&
        (
            liveView ||
            !liveConnected
        )
    ) {
        play(id);

    } else if (
        audition &&
        !liveView &&
        liveConnected
    ) {
        $('audioStatus').textContent =
            quantizedScrub
                ? '1/16 sync · auditioning through Ableton'
                : 'Live connected · auditioning through Ableton';
    } else if (
        audition &&
        quantizedScrub &&
        liveView
    ) {
        $('audioStatus').textContent =
            '1/16 sync · Live clock';
    }

    if (!s.coords[mode]) {
        $('metric').textContent =
            'Outside this map. Lower scan thresholds to reconsider.';

        return;
    }

    $('metric').textContent =
        mode === 'clap'
            ? '512 dimensions · cosine distance'
            : '32 standardized features · Euclidean distance';

    try {
        const ns =
            await get(
                `/api/neighbors/${id}?space=${mode}`
            );

        if (
            version !==
            selectionVersion
        ) {
            return;
        }

        neighborIds =
            ns.map(
                (n) => n.id
            );

        $('sequence').disabled =
            !ns.length;

        for (
            const n of ns
        ) {
            const b =
                document.createElement(
                    'button'
                );

            b.className =
                'neighbor';

            b.textContent =
                '▷ ' +
                byId.get(
                    n.id
                ).name;

            const small =
                document.createElement(
                    'small'
                );

            small.textContent =
                `Distance ${n.distance.toFixed(3)}`;

            b.append(
                small
            );

            b.onclick =
                () =>
                    select(
                        n.id
                    );

            $('neighbors').append(
                b
            );
        }

    } catch (e) {
        if (
            version ===
            selectionVersion
        ) {
            error(e);
        }
    }
}

function filtered() {
    const q =
        $('search')
            .value
            .toLowerCase();

    return data.samples.filter(
        (s) =>
            poolMembers.has(s.id) && s.path
                .toLowerCase()
                .includes(q)
    );
}

function list() {
    const samples =
        filtered().filter(
            (s) =>
                s.coords[mode] ||
                $('rejected').checked
        );

    const scroll =
        $('sampleList')
            .scrollTop;

    $('sampleList')
        .replaceChildren();

    for (
        const s of samples
    ) {
        const b =
            document.createElement(
                'button'
            );

        b.className =
            s.id === selected
                ? 'selected'
                : '';

        b.textContent =
            (
                s.coords[mode]
                    ? ''
                    : '[outside map] '
            ) +
            s.name;

        b.title =
            s.path;

        b.onclick =
            () =>
                select(
                    s.id
                );

        $('sampleList').append(
            b
        );
    }

    $('sampleList').scrollTop =
        scroll;
}

function dimensions() {
    const box =
        canvas.getBoundingClientRect();

    canvas.width =
        box.width *
        devicePixelRatio;

    canvas.height =
        box.height *
        devicePixelRatio;

    ctx.setTransform(
        devicePixelRatio,
        0,
        0,
        devicePixelRatio,
        0,
        0
    );

    return [
        box.width,
        box.height,
    ];
}

function draw() {
    const [w, h] =
        dimensions();

    visible =
        filtered().filter(
            (s) =>
                s.coords[mode]
        );

    ctx.clearRect(
        0,
        0,
        w,
        h
    );

    ctx.strokeStyle =
        '#253239';

    ctx.lineWidth =
        0.5;

    for (
        let x = 20;
        x < w;
        x += 40
    ) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
    }

    for (
        let y = 20;
        y < h;
        y += 40
    ) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
    }

    const all =
        data.samples.filter(
            (s) =>
                s.coords[mode]
        );

    /*
     * Shrink dots automatically as
     * the atlas grows.
     *
     * 150 samples -> 4.5 px
     * 600 samples -> 2.25 px
     * large atlas -> minimum 1.2 px
     *
     * The interaction hit radius
     * remains much larger.
     */
    const pointRadius =
        Math.max(
            1.2,
            Math.min(
                4.5,
                4.5 *
                    Math.sqrt(
                        150 /
                        Math.max(
                            150,
                            all.length
                        )
                    )
            )
        );

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    for (
        const s of all
    ) {
        const [x, y] =
            s.coords[mode];

        minX =
            Math.min(
                minX,
                x
            );

        maxX =
            Math.max(
                maxX,
                x
            );

        minY =
            Math.min(
                minY,
                y
            );

        maxY =
            Math.max(
                maxY,
                y
            );
    }

    const spanX =
        Math.max(
            maxX - minX,
            1
        );

    const spanY =
        Math.max(
            maxY - minY,
            1
        );

    /*
     * Compact Ableton view has very
     * little vertical room, so reduce
     * plot margins there.
     */
    const plotWidth =
        Math.max(
            40,
            w -
                (
                    liveView
                        ? 40
                        : 120
                )
        );

    const plotHeight =
        Math.max(
            40,
            h -
                (
                    liveView
                        ? 28
                        : 120
                )
        );

    points =
        visible.map(
            (s) => {
                const [x, y] =
                    s.coords[mode];

                return {
                    s,

                    x:
                        (
                            (
                                x -
                                (
                                    minX +
                                    maxX
                                ) /
                                    2
                            ) /
                            spanX
                        ) *
                        plotWidth *
                        zoom +
                        w / 2 +
                        pan[0],

                    y:
                        (
                            (
                                y -
                                (
                                    minY +
                                    maxY
                                ) /
                                    2
                            ) /
                            spanY
                        ) *
                        plotHeight *
                        zoom +
                        h / 2 +
                        pan[1],
                };
            }
        );

    for (
        const p of points
    ) {
        const hue =
            35 +
            Math.min(
                1,
                (
                    p.s.detail
                        .centroid_hz ||
                    0
                ) /
                    8000
            ) *
                175;

        ctx.fillStyle =
            `hsl(${hue},65%,68%)`;

        ctx.globalAlpha =
            p.s.id === selected
                ? 1
                : 0.8;

        const r =
            p.s.id === selected
                ? Math.max(
                    5,
                    pointRadius *
                        1.8
                )
                : pointRadius;

        ctx.beginPath();

        ctx.arc(
            p.x,
            p.y,
            r,
            0,
            Math.PI * 2
        );

        ctx.fill();

        if (
            p.s.id ===
            selected
        ) {
            ctx.strokeStyle =
                '#ecf6e4';

            ctx.lineWidth =
                1;

            ctx.beginPath();

            ctx.arc(
                p.x,
                p.y,
                Math.max(
                    9,
                    r + 5
                ),
                0,
                Math.PI * 2
            );

            ctx.stroke();
        }
    }

    ctx.globalAlpha =
        1;

    $('empty').hidden =
        visible.length > 0;
}

function hit(e) {
    const box =
        canvas.getBoundingClientRect();

    const x =
        e.clientX -
        box.left;

    const y =
        e.clientY -
        box.top;

    let best =
        null;

    /*
     * Keep a generous invisible
     * interaction radius even when
     * dots become tiny.
     */
    let distance =
        24;

    for (
        const p of points
    ) {
        const d =
            Math.hypot(
                x - p.x,
                y - p.y
            );

        if (
            d < distance
        ) {
            best =
                p.s.id;

            distance =
                d;
        }
    }

    return best;
}

canvas.onpointerdown =
    (e) => {
        if (
            e.button !== 0
        ) {
            return;
        }

        unlock()
            .catch(error);

        canvas.setPointerCapture(
            e.pointerId
        );

        drag = {
            x: e.clientX,
            y: e.clientY,
            pan: e.shiftKey,
            scrubbing: false,
        };

        const id =
            hit(e);

        lastHit =
            id;

        lastScrub =
            performance.now();

        if (
            id != null &&
            !e.shiftKey
        ) {
            select(id);
        }
    };

canvas.onpointermove =
    (e) => {
        if (!drag) {
            return;
        }

        if (drag.pan) {
            pan[0] +=
                e.clientX -
                drag.x;

            pan[1] +=
                e.clientY -
                drag.y;

            drag.x =
                e.clientX;

            drag.y =
                e.clientY;

            draw();

            return;
        }

        if (!drag.scrubbing) {
            drag.scrubbing = true;
            setScrubActive(true);
        }

        scrub(
            hit(e)
        );
    };

function endPointerGesture() {
    if (drag?.scrubbing) {
        setScrubActive(false);
    }

    drag = null;
}

canvas.onpointerup =
canvas.onlostpointercapture =
    endPointerGesture;

canvas.onpointercancel =
    () => {
        if (drag?.scrubbing) {
            setScrubActive(false);
        }

        drag = null;
        clearScrub();
    };

canvas.addEventListener(
    'wheel',

    (e) => {
        /*
         * Inside Ableton, leave
         * trackpad/wheel gestures
         * entirely to Live.
         */
        if (liveView) {
            return;
        }

        e.preventDefault();

        /*
         * Full browser:
         * pinch/ctrl-wheel = zoom
         * ordinary 2-finger scroll = pan
         */
        if (
            e.ctrlKey ||
            e.altKey
        ) {
            const box =
                canvas.getBoundingClientRect();

            const cx =
                e.clientX -
                box.left;

            const cy =
                e.clientY -
                box.top;

            const oldZoom =
                zoom;

            const factor =
                Math.exp(
                    -e.deltaY *
                    0.006
                );

            const newZoom =
                Math.max(
                    0.4,
                    Math.min(
                        8,
                        oldZoom *
                            factor
                    )
                );

            const ratio =
                newZoom /
                oldZoom;

            pan[0] =
                cx -
                box.width / 2 -
                (
                    cx -
                    box.width / 2 -
                    pan[0]
                ) *
                ratio;

            pan[1] =
                cy -
                box.height / 2 -
                (
                    cy -
                    box.height / 2 -
                    pan[1]
                ) *
                ratio;

            zoom =
                newZoom;

        } else {
            pan[0] -=
                e.deltaX;

            pan[1] -=
                e.deltaY;
        }

        draw();
    },

    {
        passive: false,
    }
);

function setMode(
    next,
    fromSync = false
) {
    const changed =
        mode !== next;

    mode =
        next;

    stop();

    if (changed) {
        zoom = 1;
        pan = [0, 0];
    }

    if (!fromSync) {
        syncSend({
            type: 'mode',
            mode,
        });
    }

    for (
        const s of [
            'clap',
            'timbral',
        ]
    ) {
        $(s).classList.toggle(
            'active',
            s === mode
        );
    }

    const detail =
        data.spaces[mode];

    $('mapInfo').textContent =
        `${mode.toUpperCase()} / ${data.projection?.scope === 'selection' ? 'SELECTION / ' : ''}` +
        `${detail?.projection || 'No map'} / ` +
        `${detail?.dimensions || 0}D → 2D`;

    $('thresholds').textContent =
        detail
            ? `Scan thresholds: one-shot ${detail.one_shot_threshold}, percussion ${detail.drum_threshold}.`
            : '';

    draw();
    list();

    if (selected) {
        select(
            selected,
            false,
            false,
            true
        );
    }
}

let loadingLibrary = false;
let reloadQueued = false;
async function load() {
    if (loadingLibrary) { reloadQueued = true; return; }
    loadingLibrary = true;
    libraryReady =
        false;

    try {
        stop();

        buffers.clear();

        const previousProjection = data.projection?.key;
        data =
            await get(
                '/api/library'
            );

        if (previousProjection !== data.projection?.key) { zoom = 1; pan = [0, 0]; }

        byId =
            new Map(
                data.samples.map(
                    (s) => [
                        s.id,
                        s,
                    ]
                )
            );

        $('status').textContent =
            `${data.samples.length} indexed · ` +
            `${
                data.samples.filter(
                    (s) =>
                        s.coords
                            .timbral
                ).length
            } mapped`;

        for (
            const s of [
                'clap',
                'timbral',
            ]
        ) {
            $(s).disabled =
                !data.spaces[s];
        }

        if (
            !data.spaces[
                mode
            ]
        ) {
            mode =
                Object.keys(
                    data.spaces
                )[0] ||
                'timbral';
        }

        if (
            !byId.has(
                selected
            )
        ) {
            selected =
                null;
        }

        setMode(
            mode,
            true
        );

        $('projectionStatus').textContent = data.projection?.scope === 'selection' ? 'Selection map' : 'Global map';
        $('embedSelection').classList.toggle('active', data.projection?.scope === 'selection');
        $('globalEmbed').classList.toggle('active', data.projection?.scope !== 'selection');
        applyPoolState(data.pool_state);

        libraryReady =
            true;

        flushPendingSync();

        $('error').hidden =
            true;

    } catch (e) {
        $('poolSummary').textContent = 'Server unavailable';
        error(e);
    } finally {
        loadingLibrary = false;
        if (reloadQueued) { reloadQueued = false; load(); }
    }
}

function applyPoolState(next) {
    if (!next) return;
    poolState = next;
    poolMembers = new Set(next.sample_ids);
    if (selected !== null && !poolMembers.has(selected)) {
        stop();
        selected = null;
        ++selectionVersion;
        neighborIds = [];
        $('sequence').disabled = true;
        $('wave').getContext('2d').clearRect(0,0,$('wave').width,$('wave').height);
        $('name').textContent = 'Find your next hit.';
        $('path').textContent = 'Choose a sample in the active pools.';
        $('neighbors').replaceChildren();
        $('scores').replaceChildren();
        $('liveSelected').textContent = '';
    }
    $('poolSummary').textContent = `${next.active_pool_ids.length} active · ${next.sample_ids.length} samples`;
    $('poolList').replaceChildren();
    for (const pool of next.pools) {
        const row = document.createElement('div');
        row.className = 'pool-row';
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = next.active_pool_ids.includes(pool.id);
        checkbox.onchange = () => poolAction(async () => {
            const ids = new Set(poolState.active_pool_ids);
            if (checkbox.checked) ids.add(pool.id); else ids.delete(pool.id);
            applyPoolState(await poolRequest('/api/pools/active','PUT',{ids:[...ids]}));
        });
        label.append(checkbox, document.createTextNode(` ${pool.name} (${pool.count})`));
        row.append(label);
        if (pool.kind === 'folder') {
            const rescan = document.createElement('button');
            rescan.textContent = 'Rescan';
            rescan.onclick = () => poolAction(async () => {
                await poolRequest(`/api/pools/${pool.id}/rescan`,'POST');
                await load();
            });
            row.append(rescan);
        }
        const remove = document.createElement('button');
        remove.textContent = 'Delete';
        remove.title = 'Delete pool; samples and analysis stay in the global library';
        remove.onclick = () => {
            if (confirm(`Delete pool “${pool.name}”? The samples and analysis will be kept.`))
                poolAction(async () => applyPoolState(await poolRequest(`/api/pools/${pool.id}`,'DELETE')));
        };
        row.append(remove);
        $('poolList').append(row);
    }
    draw();
    list();
    if (selected !== null) select(selected, false, false, true);
    if (poolBusy) $('poolManager').querySelectorAll('button,input').forEach(el => el.disabled = true);
}

async function poolRequest(url, method, body) {
    const response = await fetch(url, {method, headers:{'Content-Type':'application/json'},
        ...(body ? {body:JSON.stringify(body)} : {})});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
    return result;
}
let poolBusy = false;
async function poolAction(action) {
    if (poolBusy) return;
    poolBusy = true;
    $('poolProgress').textContent = 'Working… Analysis may take a few minutes.';
    $('poolManager').querySelectorAll('button,input').forEach(el => el.disabled = true);
    try { await action(); $('poolProgress').textContent = 'Ready'; }
    catch (e) { $('poolProgress').textContent = e.message; }
    finally {
        poolBusy = false;
        $('poolManager').querySelectorAll('button,input').forEach(el => el.disabled = false);
    }
}
$('embedSelection').onclick = () => poolAction(async () => {
    await poolRequest('/api/projection/selection','POST');
    await load();
});
$('globalEmbed').onclick = () => poolAction(async () => {
    await poolRequest('/api/projection/global','POST');
    await load();
});
$('newPool').onclick = () => { $('poolForm').hidden = false; $('poolName').focus(); };
$('cancelPool').onclick = () => { $('poolForm').hidden = true; };
$('poolForm').onsubmit = event => {
    event.preventDefault();
    poolAction(async () => {
        await poolRequest('/api/pools','POST',{name:$('poolName').value,kind:'folder',roots:[$('poolFolder').value]});
        $('poolForm').hidden = true;
        $('poolForm').reset();
        await load();
    });
};

$('clap').onclick =
    () =>
        setMode(
            'clap'
        );

$('timbral').onclick =
    () =>
        setMode(
            'timbral'
        );

$('search').oninput =
    () => {
        draw();
        list();
    };

$('rejected').onchange =
    list;

$('refresh').onclick =
    load;

$('reset').onclick =
    () => {
        zoom = 1;
        pan = [0, 0];

        draw();
    };

$('sync16').onclick =
    () => {
        setScrubSync(!scrubSync);
    };

$('openBrowser').onclick =
    () => {
        if (window.max) {
            window.max.outlet('openbrowser');
        } else {
            window.open('/', '_blank');
        }
    };

$('play').onclick =
    () => {
        if (!selected) {
            return;
        }

        if (
            !liveView &&
            liveConnected
        ) {
            syncSend({
                type: 'play',
                id: selected,
            });

        } else {
            play(
                selected
            );
        }
    };

$('stop').onclick =
    stop;

$('volume').oninput =
    () => {
        if (master) {
            master.gain.setTargetAtTime(
                +$('volume').value,
                audioCtx.currentTime,
                0.01
            );
        }
    };

$('sequence').onclick =
    async () => {
        stop();

        const token =
            sequenceVersion;

        const ids =
            [...neighborIds];

        for (
            const id of ids
        ) {
            if (
                token !==
                sequenceVersion
            ) {
                return;
            }

            let duration;

            if (
                !liveView &&
                liveConnected
            ) {
                syncSend({
                    type: 'play',
                    id,
                });

                duration =
                    byId.get(id)
                        ?.duration ||
                    0.35;

            } else {
                duration =
                    await play(
                        id,
                        true
                    );
            }

            if (
                token !==
                sequenceVersion
            ) {
                return;
            }

            await new Promise(
                (r) =>
                    setTimeout(
                        r,
                        Math.max(
                            350,
                            Math.min(
                                duration *
                                    1000 +
                                    150,
                                2200
                            )
                        )
                    )
            );
        }
    };

window.addEventListener(
    'keydown',

    (e) => {
        if (
            e.target.matches(
                'input,select,button'
            )
        ) {
            return;
        }

        if (
            e.code ===
            'Space'
        ) {
            e.preventDefault();

            if (selected) {
                if (
                    !liveView &&
                    liveConnected
                ) {
                    syncSend({
                        type: 'play',
                        id: selected,
                    });

                } else {
                    play(
                        selected
                    );
                }
            }
        }

        if (
            e.code ===
            'Escape'
        ) {
            stop();
        }
    }
);

new ResizeObserver(
    draw
).observe(
    canvas.parentElement
);

connectSync();
load();