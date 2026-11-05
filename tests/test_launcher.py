import importlib.util
from pathlib import Path
import socket
import subprocess
import sys

SCRIPT = Path(__file__).parents[1] / 'build' / 'run.py'


def test_help_works_from_another_directory(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), '--help'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert '--no-browser' in result.stdout


def test_occupied_port_is_rejected_before_building(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        port = sock.getsockname()[1]
        result = subprocess.run([sys.executable, str(SCRIPT), '--port', str(port), '--no-browser'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'already in use' in result.stderr
    assert 'npm ci' not in result.stdout


def test_default_launch_opens_browser_and_stops_child(monkeypatch):
    from unittest.mock import MagicMock
    spec = importlib.util.spec_from_file_location('launcher', SCRIPT)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    commands = []
    monkeypatch.setattr(launcher, 'run', lambda cmd: commands.append([str(x) for x in cmd]))
    monkeypatch.setattr(launcher.socket, 'socket', MagicMock())
    monkeypatch.setattr(launcher.shutil, 'which', lambda _: '/tool')
    monkeypatch.setattr(launcher.subprocess, 'check_output', lambda *a, **kw: 'v22.21.1')
    monkeypatch.setattr(launcher.venv.EnvBuilder, 'create', lambda *a: None)
    process = MagicMock()
    process.poll.return_value = None
    process.wait.side_effect = [KeyboardInterrupt(), 0]
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **kw: process)
    response = MagicMock()
    response.__enter__.return_value.status = 200
    monkeypatch.setattr(launcher.urllib.request, 'urlopen', lambda *a, **kw: response)
    opened = []
    monkeypatch.setattr(launcher.webbrowser, 'open', lambda url: opened.append(url) or True)
    assert launcher.main([]) == 0
    assert opened == ['http://127.0.0.1:8000']
    assert commands[0][-2:] == ['install', '.[audio]']
    assert commands[-1] == ['npm', 'run', 'build', '--prefix', 'frontend']
    process.terminate.assert_called_once()


def test_recently_closed_server_port_can_be_reused():
    spec = importlib.util.spec_from_file_location('launcher', SCRIPT)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    with socket.socket() as listener, socket.socket() as client:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.listen()
        client.connect(('127.0.0.1', port))
        connection, _ = listener.accept()
        connection.close()
        assert client.recv(1) == b''
    assert launcher.port_available(port)
