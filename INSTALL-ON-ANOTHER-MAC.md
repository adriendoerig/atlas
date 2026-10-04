# Install on another Mac

## Set up Drum Atlas

1. Download and unzip the project, or clone its repository, into a permanent folder such as `~/Documents/DrumAtlas`.
2. Install **Python 3.12** if needed from [python.org](https://www.python.org/downloads/macos/).
3. Double-click **Setup.command**. It creates a project-local environment and installs dependencies. Keep an internet connection available for this step.
4. For browser-only use, double-click **Launch.command**, then **Open Drum Atlas.webloc**. The interface is at <http://127.0.0.1:8765/>.
5. Open **Sample pools → + New Pool** and enter the path to a sample folder on this Mac. The first CLAP scan downloads the model weights; allow time and disk space.

## Max for Live

You need Ableton Live with Max for Live. The project’s `max4live/` folder contains:

- `drum_atlas_prototype.amxd` — the device to load in Live.
- `drum_atlas_server.js` — the companion script that starts the local server when the device loads.

Before using automatic launch on another Mac, open `drum_atlas_server.js` in a text editor and change the `ROOT` constant near the top to the **absolute path of the installed DrumAtlas project**, for example:

```js
const ROOT = '/Users/yourname/Documents/DrumAtlas';
```

Run **Setup.command** first so that the project’s `.venv` exists. Load the device in Live; the script reuses a server if one is already running, otherwise it starts one. There is no need to run **Launch.command** separately for this workflow.

**The device can go anywhere**, including your Ableton User Library—it does not need to remain in the project folder. Keep `drum_atlas_server.js` beside the device, or make it available through Max’s search path. If Max cannot find it, point the device’s `node.script` object at the script’s location. Moving the device does not change `ROOT`: that still points to the installed Python project.

The device’s web view uses `http://127.0.0.1:8765/?view=live`. Use **Open Browser** for the full interface. Start Live’s transport to audition in **16ths / 8ths / 4ths**; **1-shot** works without the transport. [MAX-SYNC.md](MAX-SYNC.md) documents the timing messages for anyone modifying the patch.

## Stopping the server

For a server started with **Launch.command**, use **Cleanup.command** or Ctrl-C in the launch terminal. Cleanup does not delete audio, pools, or cached analysis.

The Max companion script manages the server it starts and includes a `stop` handler and shutdown cleanup. **Cleanup.command** only tracks the separate command launcher; it does not stop a server started by the device. The script leaves an already-running server it did not start alone.

## Your library and files

Each Mac keeps its own library in `~/Library/Application Support/Drum Atlas/` and model cache in `~/Library/Caches/Drum Atlas/`. Original audio stays in its sample folders.

Install dependencies afresh on each Mac rather than copying `.venv`. Libraries reference absolute sample paths, so create new pools on the destination computer unless your audio is deliberately restored at the same paths. The browser shortcut can be copied to the Desktop or dragged to the Dock.

## Troubleshooting & compatibility

- If macOS asks about opening a downloaded command, use Finder’s **Open** action to review it.
- If an unzip tool drops executable permissions, run this in the project folder: `chmod +x Setup.command Launch.command Cleanup.command`.
- If the device cannot start the server, check the script’s `ROOT`, confirm Setup completed, and try **Launch.command** to see startup errors in a terminal.
- If port 8765 is already occupied, stop the existing server before starting another copy.

The tested target is an Apple Silicon Mac with Python 3.12. Intel Macs have not been verified; dependency availability can differ. Windows and Linux do not have launch helpers. This is a source setup, not a signed standalone application; installation on another physical Mac has not yet been validated.
