from __future__ import annotations

import importlib.metadata
import subprocess
import sys

from PySide6.QtCore import QObject, Signal


def is_packaged_build() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_ytdlp_version() -> str:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


class YtDlpUpdateWorker(QObject):
    status_changed = Signal(str)
    finished = Signal(bool, str)

    def run(self) -> None:
        if is_packaged_build():
            self.finished.emit(
                False,
                "This packaged build cannot update its bundled yt-dlp yet. Rebuild or reinstall ViDieL to refresh bundled tools.",
            )
            return

        self.status_changed.emit("Updating yt-dlp...")
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]

        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, f"Updater failed to start: {exc}")
            return

        output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
        if completed.returncode == 0:
            self.finished.emit(True, output or "yt-dlp is up to date.")
        else:
            self.finished.emit(False, output or "yt-dlp update failed.")
