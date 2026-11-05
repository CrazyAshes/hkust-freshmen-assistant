#!/bin/bash
# macOS: double-click to start. Needs Python 3.9+ (https://www.python.org/downloads/).
cd "$(dirname "$0")"
PY=/Users/yuyinliu/.workbuddy-ai/binaries/python/versions/3.13.12/bin/python3
[ -x "$PY" ] || PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "没有找到 python3，请先安装 Python 3 / python3 not found, please install Python 3 first."
  read -n 1 -s -r -p "按任意键退出 / press any key"; exit 1
fi
if [ ! -d .venv ]; then
  "$PY" -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
# first run on a fresh copy: build the search index from data/corpus/
[ -f data/knowledge.db ] || .venv/bin/python manage.py rebuild
open http://127.0.0.1:8000 >/dev/null 2>&1 &
.venv/bin/python server.py 8000
