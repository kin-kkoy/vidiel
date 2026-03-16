#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/dist/ViDieL"
APP_BIN="$APP_DIR/ViDieL"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/vidiel.desktop"

if [[ ! -x "$APP_BIN" ]]; then
  echo "Packaged app not found at: $APP_BIN"
  echo "Build the packaged app first, then run this launcher installer again."
  exit 1
fi

mkdir -p "$DESKTOP_DIR"

cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ViDieL
Comment=Local video downloader and converter
Exec=$APP_BIN
Path=$APP_DIR
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Utility;
StartupNotify=true
StartupWMClass=ViDieL
EOF

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed launcher: $DESKTOP_FILE"
echo "You can now search for ViDieL in your app menu and pin it to the dock."
