"""Double-click helpers for this project's localhost server only."""
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
from drum_atlas.paths import data_dir

PROJECT = Path(__file__).resolve().parent
COMMAND = [str(PROJECT/'.venv/bin/drum-atlas'), 'serve']

def identity(pid):
    result = subprocess.run(['/bin/ps','-p',str(pid),'-o','lstart=','-o','command='],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode == 0 else ''

def stop(record):
    if not record.exists():
        print('No server started by Launch.command is recorded. If started manually, use Ctrl-C in its terminal.')
        return
    saved = json.loads(record.read_text())
    pid = saved['pid']
    actual = identity(pid)
    if not actual or actual != saved['identity'] or str(PROJECT/'.venv/bin/drum-atlas') not in actual:
        print('The recorded server is no longer running. No other process was stopped.')
        record.unlink(missing_ok=True)
        return
    os.kill(pid,signal.SIGTERM)
    print('Drum Atlas is shutting down. Your samples and pools are saved.')

def main():
    folder = data_dir();folder.mkdir(parents=True,exist_ok=True)
    record = folder/'server-process.json'
    if len(sys.argv)>1 and sys.argv[1]=='stop':
        stop(record);return
    with (folder/'server-launch.lock').open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Drum Atlas is already launched. Double-click Open Drum Atlas.webloc.');return
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',8765)) == 0:
                print('Port 8765 is already in use. If Drum Atlas is running, open the browser shortcut.');return
        child = subprocess.Popen(COMMAND,cwd=PROJECT)
        record.write_text(json.dumps({'pid':child.pid,'identity':identity(child.pid)}))
        print('Open Drum Atlas.webloc to browse. Ctrl-C or Cleanup.command stops this server.',flush=True)
        try: child.wait()
        except KeyboardInterrupt:
            if child.poll() is None: child.terminate()
            child.wait()
        finally:
            if record.exists() and json.loads(record.read_text())['pid']==child.pid:
                record.unlink()

if __name__=='__main__': main()
