#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv. Create it and install dependencies first."
  exit 1
fi

.venv/bin/python -m pip install pyinstaller

ARIA2C_PATH="$(command -v aria2c || true)"
BUNDLE_ARGS=()
if [[ -n "$ARIA2C_PATH" ]]; then
  echo "Bundling aria2c from: $ARIA2C_PATH"
  BUNDLE_ARGS+=(--add-binary "$ARIA2C_PATH:bin")
else
  echo "aria2c not found on PATH. Packaged build will fall back to the built-in downloader."
fi

.venv/bin/pyinstaller \
  --noconfirm \
  --clean \
  --name ViDieL \
  --windowed \
  --paths src \
  "${BUNDLE_ARGS[@]}" \
  src/vidiel/__main__.py

echo "Build complete: dist/ViDieL"
echo "Note: ffmpeg is still expected as a system dependency on Linux."
echo "Note: packaged builds do not self-update bundled yt-dlp yet."
