"""Frozen local server. All paths are supplied by the native desktop host."""
import argparse
import asyncio
import logging
import os
from pathlib import Path
import secrets
import socket
import sys


def create_app(token, origin):
    from backend.main import app
    from fastapi.responses import JSONResponse, RedirectResponse

    @app.middleware('http')
    async def desktop_session(request, call_next):
        if request.headers.get('host') != origin.removeprefix('http://'):
            return JSONResponse({'detail': 'Invalid host'}, status_code=403)
        if request.url.path == '/__desktop__/start':
            if not secrets.compare_digest(request.query_params.get('token', ''), token):
                return JSONResponse({'detail': 'Invalid session'}, status_code=403)
            response = RedirectResponse('/')
            response.set_cookie('bookskill_session', token, httponly=True, samesite='strict')
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response
        if not secrets.compare_digest(request.cookies.get('bookskill_session', ''), token):
            return JSONResponse({'detail': 'Desktop session required'}, status_code=403)
        if request.method not in ('GET', 'HEAD') and request.headers.get('origin', origin) != origin:
            return JSONResponse({'detail': 'Invalid origin'}, status_code=403)
        response = await call_next(request)
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    return app


async def serve(args):
    import uvicorn
    token = os.environ.pop('BOOKSKILL_SESSION')
    origin = f'http://127.0.0.1:{args.port}'
    app = create_app(token, origin)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port,
        log_config=None, access_log=False))

    # Register ahead of the SPA catch-all, which would otherwise shadow it.
    async def shutdown():
        server.should_exit = True
        return {'ok': True}
    from fastapi.routing import APIRoute
    app.router.routes.insert(0, APIRoute('/__desktop__/shutdown', shutdown, methods=['POST']))
    sock = socket.socket()
    # Exclusive binding also prevents a second desktop process using this origin.
    if sys.platform == 'win32':
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(('127.0.0.1', args.port))
    sock.listen(128)
    sock.setblocking(False)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            if task.done():
                await task
                raise RuntimeError('Backend exited before startup')
            await asyncio.sleep(.05)
        Path(args.ready_file).write_text(origin, encoding='utf-8')
        await task
    finally:
        sock.close()
        Path(args.ready_file).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--ready-file', required=True)
    parser.add_argument('--port', type=int, default=17863)
    args = parser.parse_args()
    data = Path(args.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    os.environ['BOOKSKILL_DATA'] = str(data)
    # PyInstaller --windowed sets stdout/stderr to None on Windows.
    stream = open(data / 'desktop.log', 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = stream
    logging.basicConfig(stream=stream, level=logging.INFO)
    try:
        asyncio.run(serve(args))
    except Exception:
        logging.exception('Desktop backend failed')
        raise


if __name__ == '__main__':
    main()
