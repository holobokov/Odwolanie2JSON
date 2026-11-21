#!/usr/bin/env sh
set -eu

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if command -v python3.13 >/dev/null 2>&1; then
        PYTHON=python3.13
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    else
        echo "Brak Pythona. Zainstaluj Python 3.13 lub uruchom docker compose up --build."
        exit 1
    fi
fi

if [ ! -x ".venv/bin/python" ] || [ "$(.venv/bin/python -c 'import sys; print(sys.version_info >= (3, 13))' 2>/dev/null || printf False)" = "False" ]; then
    rm -rf .venv
    "$PYTHON" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python -m streamlit run app.py --server.address 0.0.0.0
