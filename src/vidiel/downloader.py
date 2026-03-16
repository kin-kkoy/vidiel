from __future__ import annotations

import os
import re
import shlex
import time
from pathlib import Path

import yt_dlp
from PySide6.QtCore import QObject, Signal

from vidiel.models import DownloadRequest, DownloadType


class DownloadCancelled(Exception):
    pass


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _sanitize_component(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", value).strip() or "download"


def _clean_terminal_text(value: str) -> str:
    cleaned = ANSI_ESCAPE_RE.sub("", value or "")
    return " ".join(cleaned.split())


def build_command_preview(request: DownloadRequest) -> str:
    args = ["yt-dlp", request.url]
    if request.download_type == DownloadType.AUDIO:
        args.extend(["-x", "--audio-format", "mp3"])
        args.extend(["--audio-quality", request.quality + "K"])
    else:
        if request.quality == "best":
            args.extend(["-f", "bv*+ba/b"])
        else:
            args.extend(["-f", f"bv*[height<={request.quality}]+ba/b[height<={request.quality}]"])
    if request.use_cookies:
        args.extend(["--cookies-from-browser", "firefox"])
    if request.concurrent_fragments > 1:
        args.extend(["-N", str(request.concurrent_fragments)])
    if request.downloader_backend == "aria2c":
        args.extend(["--downloader", "aria2c"])
    args.extend(["-P", request.output_dir, "-o", _output_template(request)])
    return shlex.join(args)


def _output_template(request: DownloadRequest) -> str:
    if request.custom_name:
        base_name = _sanitize_component(request.custom_name)
        return f"{base_name}.%(ext)s"
    return "%(title).180B [%(id)s].%(ext)s"


class DownloadWorker(QObject):
    progress_changed = Signal(int)
    status_changed = Signal(str)
    title_resolved = Signal(str)
    command_ready = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, request: DownloadRequest) -> None:
        super().__init__()
        self.request = request
        self._cancel_requested = False
        self._final_path = ""
        self._title = ""
        self._last_progress_emit = 0.0
        self._last_status_emit = 0.0

    def _ui_emit_interval(self) -> float:
        if self.request.performance_mode == "low_memory":
            return 0.9
        if self.request.performance_mode == "max_speed":
            return 0.2
        return 0.45

    def cancel(self) -> None:
        self._cancel_requested = True
        self.status_changed.emit("Cancelling current download...")

    def run(self) -> None:
        self.command_ready.emit(build_command_preview(self.request))
        self.status_changed.emit("Starting download...")

        try:
            options = self._build_options()
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.request.url, download=True)
                result = self._make_result(info)
        except DownloadCancelled:
            self.cancelled.emit("Download cancelled.")
        except yt_dlp.utils.DownloadError as exc:
            self.failed.emit(self._humanize_error(str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.finished.emit(result)

    def _build_options(self) -> dict:
        request = self.request
        output_template = str(Path(request.output_dir) / _output_template(request))
        options: dict = {
            "paths": {"home": request.output_dir},
            "outtmpl": {"default": output_template},
            "progress_hooks": [self._on_progress],
            "logger": _YtdlpLogger(self.status_changed),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,
            "concurrent_fragment_downloads": request.concurrent_fragments,
        }

        if request.downloader_backend == "aria2c":
            options["external_downloader"] = "aria2c"
            options["external_downloader_args"] = {
                "default": [
                    "--max-connection-per-server=8",
                    "--split=8",
                    "--min-split-size=1M",
                    "--summary-interval=0",
                    "--download-result=hide",
                    "--console-log-level=warn",
                ]
            }

        if request.download_type == DownloadType.AUDIO:
            options["format"] = "bestaudio/best"
            options["final_ext"] = "mp3"
            options["keepvideo"] = False
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": request.quality,
                }
            ]
        else:
            if request.quality == "best":
                options["format"] = "bv*+ba/b"
            else:
                options["format"] = f"bv*[height<={request.quality}]+ba/b[height<={request.quality}]"
            options["merge_output_format"] = "mp4"

        if request.use_cookies:
            options["cookiesfrombrowser"] = ("firefox",)

        return options

    def _on_progress(self, data: dict) -> None:
        if self._cancel_requested:
            raise DownloadCancelled()

        status = data.get("status")
        if status == "downloading":
            now = time.monotonic()
            progress = self._extract_percent(data)
            if progress is not None and (
                now - self._last_progress_emit >= self._ui_emit_interval() or progress >= 100
            ):
                self.progress_changed.emit(progress)
                self._last_progress_emit = now

            filename = data.get("filename")
            if filename:
                self._final_path = filename
                title = Path(filename).stem
                if title and title != self._title:
                    self._title = title
                    self.title_resolved.emit(title)

            speed = _clean_terminal_text(data.get("_speed_str") or "")
            eta = _clean_terminal_text(data.get("_eta_str") or "")
            percent = f"{progress}%" if progress is not None else _clean_terminal_text(data.get("_percent_str", "").strip())

            details = [part for part in [percent, speed, f"ETA {eta}" if eta else ""] if part]
            if now - self._last_status_emit >= self._ui_emit_interval():
                self.status_changed.emit("Downloading " + " | ".join(details))
                self._last_status_emit = now

        elif status == "finished":
            filename = data.get("filename")
            if filename:
                self._final_path = filename
            self.progress_changed.emit(100)
            if self.request.download_type == DownloadType.AUDIO:
                self.status_changed.emit("Converting audio to MP3...")
            else:
                self.status_changed.emit("Processing media with ffmpeg...")

    def _make_result(self, info: dict) -> dict:
        requested_downloads = info.get("requested_downloads") or []
        filepath = ""
        if requested_downloads:
            filepath = requested_downloads[0].get("filepath") or ""
        if not filepath:
            filepath = info.get("_filename") or self._final_path

        if filepath and self.request.download_type == DownloadType.AUDIO:
            mp3_path = str(Path(filepath).with_suffix(".mp3"))
            if os.path.exists(mp3_path):
                filepath = mp3_path

        filepath = os.path.abspath(filepath) if filepath else ""
        title = self.request.custom_name or info.get("title") or self._title or _sanitize_component(self.request.url)

        return {
            "title": title,
            "output_path": filepath,
            "url": self.request.url,
        }

    @staticmethod
    def _extract_percent(data: dict) -> int | None:
        if "_percent_str" in data:
            raw = data["_percent_str"].strip().replace("%", "")
            try:
                return max(0, min(100, int(float(raw))))
            except ValueError:
                return None
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        downloaded = data.get("downloaded_bytes")
        if total and downloaded is not None:
            return max(0, min(100, int(downloaded / total * 100)))
        return None

    @staticmethod
    def _humanize_error(message: str) -> str:
        lowered = message.lower()
        if "unsupported url" in lowered:
            return "That URL is not supported by yt-dlp."
        if "ffmpeg is not installed" in lowered:
            return "ffmpeg is required for this conversion but is not installed."
        if "requested format is not available" in lowered:
            return "The selected quality is not available for this video."
        if "cookies" in lowered:
            return "Browser cookies could not be loaded. Try disabling the cookies option."
        return message


class _YtdlpLogger:
    def __init__(self, signal: Signal) -> None:
        self.signal = signal

    def debug(self, msg: str) -> None:
        msg = _clean_terminal_text(msg)
        if not msg or msg.startswith("[debug]") or msg.startswith("[download]"):
            return
        self.signal.emit(msg)

    def warning(self, msg: str) -> None:
        msg = _clean_terminal_text(msg)
        if msg:
            self.signal.emit(msg)

    def error(self, msg: str) -> None:
        msg = _clean_terminal_text(msg)
        if msg:
            self.signal.emit(msg)
