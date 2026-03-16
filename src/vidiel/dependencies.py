from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(slots=True)
class DependencyStatus:
    yt_dlp: str | None
    ffmpeg: str | None
    ffprobe: str | None

    @property
    def missing(self) -> list[str]:
        missing = []
        if not self.yt_dlp:
            missing.append("yt-dlp")
        if not self.ffmpeg:
            missing.append("ffmpeg")
        if not self.ffprobe:
            missing.append("ffprobe")
        return missing

    @property
    def ok(self) -> bool:
        return not self.missing


def check_dependencies() -> DependencyStatus:
    return DependencyStatus(
        yt_dlp=shutil.which("yt-dlp"),
        ffmpeg=shutil.which("ffmpeg"),
        ffprobe=shutil.which("ffprobe"),
    )


def install_guidance(missing: list[str]) -> str:
    lines = ["Missing required tools: " + ", ".join(missing), "", "Linux install examples:"]
    if any(name.startswith("ff") for name in missing):
        lines.append("- Debian/Ubuntu: sudo apt install ffmpeg")
        lines.append("- Fedora: sudo dnf install ffmpeg")
        lines.append("- Arch: sudo pacman -S ffmpeg")
    if "yt-dlp" in missing:
        lines.append("- pipx install yt-dlp")
        lines.append("- or: python3 -m pip install --user yt-dlp")
    return "\n".join(lines)
