from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DownloadType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


@dataclass(slots=True)
class QualityOption:
    key: str
    label: str


VIDEO_QUALITY_OPTIONS = [
    QualityOption("best", "Best available"),
    QualityOption("1080", "1080p"),
    QualityOption("720", "720p"),
    QualityOption("480", "480p"),
]

AUDIO_QUALITY_OPTIONS = [
    QualityOption("192", "Recommended MP3"),
    QualityOption("320", "MP3 320 kbps"),
    QualityOption("192", "MP3 192 kbps"),
    QualityOption("128", "MP3 128 kbps"),
]


@dataclass(slots=True)
class DownloadRequest:
    url: str
    download_type: DownloadType
    quality: str
    output_dir: str
    use_cookies: bool
    custom_name: str = ""
    concurrent_fragments: int = 1
    downloader_backend: str = "native"
    performance_mode: str = "balanced"
    downloader_path: str = ""


@dataclass(slots=True)
class QueueItem:
    request: DownloadRequest
    label: str


@dataclass(slots=True)
class DownloadRecord:
    title: str
    status: str
    output_path: str
    url: str
    timestamp: str


@dataclass(slots=True)
class AppSettings:
    output_dir: str = ""
    use_cookies: bool = False
    concurrent_fragments: int = 4
    downloader_backend: str = "native"
    performance_mode: str = "balanced"
    history: list[DownloadRecord] = field(default_factory=list)
