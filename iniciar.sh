#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

echo "Iniciando Dashboard de Ventas - Aluminios..."
.venv/bin/python -m streamlit run dashboard.py --server.port 8501
