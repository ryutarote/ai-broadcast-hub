#!/usr/bin/env bash
# One-command setup for the TikTok video pipeline.
#
# Requires: docker, python3, ffmpeg, fonts-noto-cjk
#
# What it does:
#   1. Installs system fonts/ffmpeg if missing (Debian/Ubuntu).
#   2. Creates a venv and installs python deps.
#   3. Starts the AivisSpeech Engine via docker-compose.
#   4. Installs the ろてじん voice model.
#   5. Copies .env.example to .env if missing.

set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="$(pwd)"
echo "==> Working dir: ${ROOT}"

if [[ -f /etc/debian_version ]]; then
  if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "==> Installing ffmpeg + Noto CJK fonts (apt)"
    sudo apt-get update -y
    sudo apt-get install -y ffmpeg fonts-noto-cjk
  fi
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Wrote .env (edit as needed)"
fi

if [[ ! -d .venv ]]; then
  echo "==> Creating python venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin is required."
  exit 1
fi

echo "==> Starting AivisSpeech Engine"
docker compose up -d

echo "==> Waiting for engine to be ready"
for i in {1..60}; do
  if curl -sf http://localhost:10101/version >/dev/null; then
    echo "    engine ready."
    break
  fi
  sleep 2
done

echo "==> Installing ろてじん voice model"
python -m tools.install_voice

echo ""
echo "Setup complete. Run a single post:"
echo "  source .venv/bin/activate && python -m pipeline.run --id 001"
echo "or render all 30:"
echo "  source .venv/bin/activate && python -m pipeline.run"
