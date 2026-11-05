"""Opt-in live test: python scripts/smoke.py [http://127.0.0.1:8000]."""
import json
import sys
import time
import urllib.request

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
for video, expected in [('jNQXAC9IVRw', 'manual'), ('kqtD5dpn9C8', 'automatic'), ('aqz-KE-bpKQ', 'captions_missing')]:
    request = urllib.request.Request(base + '/transcripts', data=json.dumps({'url': f'https://youtu.be/{video}', 'language': 'en'}).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        id = json.load(response)['id']
    for _ in range(180):
        with urllib.request.urlopen(base + '/transcripts/' + id, timeout=15) as response:
            job = json.load(response)
        if job['status'] in {'completed', 'failed'}:
            break
        time.sleep(1)
    else:
        raise SystemExit(f'{video}: timeout')
    actual = job['transcript']['source'] if job['status'] == 'completed' else job['error']['code']
    print(video, actual, flush=True)
    if actual != expected:
        raise SystemExit(f'Expected {expected}, got {actual}')
    if job['status'] == 'completed':
        for format in ['txt', 'srt']:
            with urllib.request.urlopen(f'{base}/transcripts/{id}/export?format={format}', timeout=15) as response:
                assert response.read()
print('Live smoke passed')
