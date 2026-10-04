# Install on another Mac

1. Unzip `DrumAtlas-Mac.zip` into a permanent folder, for example Documents.
2. Install **Python 3.12** if needed, from https://www.python.org/downloads/macos/.
3. Double-click **Setup.command**. It creates a local environment and installs
   dependencies. Keep an internet connection available for this step.
4. Double-click **Launch.command**, then **Open Drum Atlas.webloc**.
5. Use **+ New Pool** to select sample folders on that computer (enter their paths).
   The first CLAP scan downloads the model weights; allow time and disk space.
6. For Ableton use, copy your current `.amxd` device separately. Set its jweb~ URL
   to `http://127.0.0.1:8765/?view=live` and apply `MAX-SYNC.md` once for subdivisions.
   The browser works without Ableton.

**Cleanup.command** or Ctrl-C in the launch terminal stops the server. Cleanup
never deletes audio, pools or cached analysis. The browser shortcut can be
copied to the Desktop or dragged to the Dock.

The archive excludes this computer's virtualenv, database, sample paths, audio,
model weights, Git history, and development screenshots. Each Mac gets its own
library under `~/Library/Application Support/Drum Atlas` and model cache under
`~/Library/Caches/Drum Atlas`. Copying the old virtualenv does not install Python
on another machine. Libraries contain absolute sample paths, so start with new
pools unless the audio is deliberately restored at the same paths.

If macOS asks about opening a downloaded command, use Finder's Open action to
review it. If an unzip tool drops executable permissions, run in the extracted
folder: `chmod +x Setup.command Launch.command Cleanup.command`.

The tested target is an Apple Silicon Mac with Python 3.12. Intel Macs have not
been verified; dependency availability can differ. Windows and Linux do not
have launch helpers in this archive. This is a source setup bundle, not a signed
standalone application. Another physical Mac was not available for validation.
