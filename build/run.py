#!/usr/bin/env python3
"""Build and serve Intelligence Studio locally, then open the default browser."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def port_available(port):
    with socket.socket() as check:
        # Match Uvicorn: released sockets in TIME_WAIT must not block restart.
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            check.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def interrupt(*_):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000, help='Local port (default: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='Print the URL without opening a browser')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or newer is required')
    if not port_available(args.port):
        print(f'Port {args.port} is already in use or unavailable. Choose another with --port.', file=sys.stderr)
        return 1
    if not shutil.which('npm') or not shutil.which('node'):
        print('Install Node.js 22.12+ (including npm), then retry.', file=sys.stderr)
        return 1
    version = subprocess.check_output(['node', '--version'], text=True).strip().lstrip('v')
    major, minor = map(int, version.split('.')[:2])
    if major < 22 or (major == 22 and minor < 12):
        print('Node.js 22.12+ is required.', file=sys.stderr)
        return 1
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Creating .venv', flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    run([python, '-m', 'pip', 'install', '.[audio]'])
    run(['npm', 'ci', '--prefix', 'frontend'])
    run(['npm', 'run', 'build', '--prefix', 'frontend'])
    url = f'http://127.0.0.1:{args.port}'
    # Frontend assets and API share one origin and one server process.
    process = subprocess.Popen([str(python), '-m', 'uvicorn', 'youtube_transcriber.api:app', '--host', '127.0.0.1', '--port', str(args.port), '--workers', '1', '--no-access-log'], cwd=ROOT)
    old_term = signal.signal(signal.SIGTERM, interrupt)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('The app exited before it became ready. See the server output above.')
            try:
                with urllib.request.urlopen(url + '/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(.2)
        else:
            raise RuntimeError('The app did not become ready within 30 seconds.')
        print(f'\nIntelligence Studio is ready: {url}\nPress Ctrl+C to stop.\n', flush=True)
        if not args.no_browser:
            try:
                if not webbrowser.open(url):
                    print('No browser was available; open the URL above manually.', flush=True)
            except webbrowser.Error:
                print('Could not open the browser; open the URL above manually.', flush=True)
        return process.wait()
    except KeyboardInterrupt:
        print('\nStopping Intelligence Studio…', flush=True)
        return 0
    finally:
        signal.signal(signal.SIGTERM, old_term)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, RuntimeError, OSError) as exc:
        print(f'Launch failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
