#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
VENV=.venv

if [ ! -d "$VENV" ]; then
  echo "→ Создаю виртуальное окружение…"
  $PY -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "→ Ставлю зависимости…"
pip install -q --upgrade pip
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "→ Создал .env (DEMO_MODE=true). Боевые ключи добавишь позже."
fi

echo ""
echo "  NEUROCORP командный центр → http://localhost:8000"
echo ""
exec uvicorn server:app --host 0.0.0.0 --port 8000
