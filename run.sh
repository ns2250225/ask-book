#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then uv venv .venv; else python3 -m venv .venv; fi
fi
if ! .venv/bin/python -c 'import fastapi,uvicorn,pymupdf,ebooklib' >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then uv pip install --python .venv/bin/python -r requirements.lock; else .venv/bin/python -m pip install -r requirements.lock; fi
fi
if [ ! -d frontend/node_modules ]; then npm --prefix frontend ci; fi
npm --prefix frontend run build
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "${BOOKSKILL_PORT:-8000}" --no-access-log
