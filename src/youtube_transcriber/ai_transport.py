"""Bounded HTTPS transport: public DNS targets, pinned TLS hostname, no redirects."""
import ipaddress
import json
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import certifi
import urllib3
from .ai_models import InsightError


def public_destination(url):
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError
        if any(ord(c) < 33 or ord(c) > 126 for c in url) or '\\' in url:
            raise ValueError
        port = parts.port or 443
        host = parts.hostname
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError
        return host, port, ips[0], parts.path or '/'
    except (ValueError, OSError):
        raise InsightError('invalid_endpoint', 'Use a public HTTPS API endpoint without credentials, query parameters or fragments.', 400) from None


def _post_json(url, headers, payload):
    host, port, address, path = public_destination(url)
    pool = urllib3.HTTPSConnectionPool(
        address, port=port, server_hostname=host, assert_hostname=host,
        cert_reqs='CERT_REQUIRED', ca_certs=certifi.where(),
        timeout=urllib3.Timeout(connect=10, read=90), retries=False,
    )
    response = None
    try:
        response = pool.urlopen('POST', path, body=json.dumps(payload).encode(), headers={**headers, 'Host':host if port == 443 else f'{host}:{port}', 'Content-Type':'application/json', 'Accept':'application/json'}, redirect=False, retries=False, preload_content=False)
        if response.status != 200:
            return response.status, None
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise InsightError('ai_response_invalid', 'The provider returned an oversized response.')
        try:
            return response.status, json.loads(raw)
        except (ValueError, UnicodeError):
            raise InsightError('ai_response_invalid', 'The provider did not return valid JSON.') from None
    except urllib3.exceptions.TimeoutError:
        raise InsightError('ai_timeout', 'The AI provider timed out. No automatic retry was made; you can retry manually.', 504) from None
    except (urllib3.exceptions.HTTPError, OSError):
        raise InsightError('ai_unavailable', 'Could not securely connect to the AI provider. Check the endpoint and try again.') from None
    finally:
        if response is not None:
            response.close()
        pool.close()


def post_json(url, headers, payload):
    # A process boundary lets the parent terminate DNS or a trickling response.
    # Keys travel through stdin, never command arguments, environment or files.
    command = [sys.executable, '-c',
               'import sys; sys.path.insert(0, sys.argv[1]); from youtube_transcriber.ai_transport import _worker; _worker()',
               str(Path(__file__).resolve().parents[1])]
    try:
        completed = subprocess.run(command, input=json.dumps({'url':url,'headers':headers,'payload':payload}),
                                   capture_output=True, text=True, timeout=100, check=False)
        if completed.returncode != 0:
            raise InsightError('ai_unavailable', 'The AI connection could not be completed.')
        result = json.loads(completed.stdout)
        if 'error' in result:
            raise InsightError(**result['error'])
        return result['status'], result['data']
    except subprocess.TimeoutExpired:
        raise InsightError('ai_timeout', 'The AI request exceeded its time limit. No automatic retry was made; check provider usage before retrying.', 504) from None
    except (OSError, ValueError, KeyError):
        raise InsightError('ai_unavailable', 'The AI connection could not be completed.') from None


def _worker():
    try:
        request = json.load(sys.stdin)
        status, data = _post_json(request['url'], request['headers'], request['payload'])
        result = {'status':status, 'data':data}
    except InsightError as exc:
        result = {'error':{'code':exc.code, 'message':str(exc), 'status':exc.status}}
    except Exception:
        # Never serialize raw exceptions or request headers containing the key.
        result = {'error':{'code':'ai_unavailable','message':'The AI connection could not be completed.','status':502}}
    sys.stdout.write(json.dumps(result))
