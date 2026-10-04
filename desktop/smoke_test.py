"""Exercise the frozen binary, assets, auth, upload, SQLite/FTS, export and shutdown."""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import io

ROOT = Path(__file__).resolve().parent.parent

def main():
    executable = ROOT / 'src-tauri/binaries' / ('bookskill-sidecar.exe' if sys.platform == 'win32' else 'bookskill-sidecar')
    with tempfile.TemporaryDirectory() as folder:
        data = Path(folder)
        ready = data / 'ready.txt'
        token = secrets.token_hex(16)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([str(executable), '--data-dir', folder, '--ready-file', str(ready), '--port', str(port)],
            env={**os.environ, 'BOOKSKILL_SESSION': token})
        origin = f'http://127.0.0.1:{port}'
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def request(path, body=None, headers=None):
            return opener.open(urllib.request.Request(origin+path, data=body, headers=headers or {}), timeout=10)
        try:
            deadline = time.monotonic() + 90
            while not ready.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError((data / 'desktop.log').read_text() if (data / 'desktop.log').exists() else 'Sidecar startup failed')
                time.sleep(.1)
            try:
                request('/api/health')
                raise AssertionError('Unauthenticated API allowed')
            except urllib.error.HTTPError as error:
                assert error.code == 403
            html = request('/__desktop__/start?token='+token).read().decode()
            assert 'id="app"' in html
            import re
            asset = re.search(r'src="([^"]+\.js)"', html)[1]
            assert request(asset).status == 200
            assert json.load(request('/api/health'))['status'] == 'ok'
            try:
                request('/api/demo', b'{}', {'Origin': 'https://evil.example', 'Content-Type': 'application/json'})
                raise AssertionError('Cross-origin mutation allowed')
            except urllib.error.HTTPError as error:
                assert error.code == 403
            boundary = 'bookskill-smoke-boundary'
            upload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="smoke.md"\r\n'
                      'Content-Type: text/markdown\r\n\r\n# Smoke\n\n## Chapter 1\n'
                      f'Knowledge needs context and practice.\r\n--{boundary}--\r\n').encode()
            uploaded = json.load(request('/api/books', upload, {'Content-Type': 'multipart/form-data; boundary='+boundary}))
            assert uploaded['book']['chapterCount'] == 1
            book = json.load(request('/api/demo', b'{}', {'Content-Type': 'application/json'}))
            assert book['chapterCount'] > 0
            assert json.load(request('/api/books/'+book['id']+'/search?q=阅读&kind=book'.replace('阅读', '%E9%98%85%E8%AF%BB')))
            raw = request('/api/books/'+book['id']+'/export').read()
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                assert any(name.endswith('SKILL.md') for name in archive.namelist())
            assert request('/books/'+book['id']).status == 200
            assert (data/'bookskill.db').exists()
            request('/__desktop__/shutdown', b'{}').close()
            process.wait(timeout=20)
            assert process.returncode == 0
            assert not ready.exists()
            print('Frozen sidecar smoke test passed')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

if __name__ == '__main__':
    main()
