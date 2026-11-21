#!/usr/bin/env sh
set -eu

if [ ! -d ".venv" ]; then
    python3.13 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m streamlit run app.py --server.address 0.0.0.0
