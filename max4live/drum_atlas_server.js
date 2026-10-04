const maxApi = require('max-api');
const { spawn } = require('child_process');
const http = require('http');

const ROOT =
    '/Users/adriendoerig/Documents/DrumAtlas';

const PYTHON =
    ROOT + '/.venv/bin/python';

const PORT = 8765;

let child = null;
let ownsServer = false;


// ---------------------------------------------------------------------
// Check whether Drum Atlas is already running
// ---------------------------------------------------------------------

function serverAlive() {
    return new Promise((resolve) => {
        const req = http.get(
            {
                hostname: '127.0.0.1',
                port: PORT,
                path: '/',
                timeout: 1000,
            },

            (res) => {
                res.resume();

                resolve(
                    res.statusCode >= 200 &&
                    res.statusCode < 500
                );
            }
        );

        req.on(
            'error',
            () => resolve(false)
        );

        req.on(
            'timeout',
            () => {
                req.destroy();
                resolve(false);
            }
        );
    });
}


// ---------------------------------------------------------------------
// Wait until FastAPI/Uvicorn is actually accepting connections
// ---------------------------------------------------------------------

async function waitUntilReady() {
    for (let i = 0; i < 50; i++) {
        if (await serverAlive()) {
            maxApi.outlet('ready');
            return;
        }

        await new Promise(
            (resolve) =>
                setTimeout(resolve, 200)
        );
    }

    maxApi.outlet(
        'error',
        'Drum Atlas server did not start'
    );
}


// ---------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------

async function start() {
    // Somebody else already started Drum Atlas.
    if (await serverAlive()) {
        ownsServer = false;
        maxApi.outlet('ready');
        return;
    }

    // Avoid spawning twice.
    if (child) {
        return;
    }

    const env = {
        ...process.env,

        PYTHONPATH:
            process.env.PYTHONPATH
                ? ROOT + ':' + process.env.PYTHONPATH
                : ROOT,
    };

    child = spawn(
        PYTHON,
        [
            '-m',
            'drum_atlas.cli',
            'serve',
            '--port',
            String(PORT),
        ],
        {
            cwd: ROOT,
            env: env,

            // Don't flood the Max console with
            // Uvicorn GET request messages.
            stdio: 'ignore',
        }
    );

    ownsServer = true;

    child.on(
        'exit',
        () => {
            child = null;
            ownsServer = false;
        }
    );

    waitUntilReady();
}


// ---------------------------------------------------------------------
// Stop
// ---------------------------------------------------------------------

function stop() {
    // Only kill a server that THIS Max device started.
    if (
        child &&
        ownsServer
    ) {
        try {
            child.kill('SIGTERM');
        } catch (_) {}

        child = null;
        ownsServer = false;
    }
}


maxApi.addHandler(
    'start',
    start
);

maxApi.addHandler(
    'stop',
    stop
);


// Extra protection when node.script itself is shut down.
process.on(
    'exit',
    stop
);

process.on(
    'SIGTERM',
    () => {
        stop();
        process.exit(0);
    }
);

start();