from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DependencyStatus:
    yt_dlp: str | None
    ffmpeg: str | None
    ffprobe: str | None
    aria2c: str | None

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


def _bundled_binary(name: str) -> str | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / name,
                exe_dir / "bin" / name,
                Path(getattr(sys, "_MEIPASS", exe_dir)) / name,
                Path(getattr(sys, "_MEIPASS", exe_dir)) / "bin" / name,
            ]
        )

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def find_tool(name: str) -> str | None:
    return _bundled_binary(name) or shutil.which(name)


def check_dependencies() -> DependencyStatus:
    return DependencyStatus(
        yt_dlp=find_tool("yt-dlp"),
        ffmpeg=find_tool("ffmpeg"),
        ffprobe=find_tool("ffprobe"),
        aria2c=find_tool("aria2c"),
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
