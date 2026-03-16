from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QObject, Signal


class YtDlpUpdateWorker(QObject):
    status_changed = Signal(str)
    finished = Signal(bool, str)

    def run(self) -> None:
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
