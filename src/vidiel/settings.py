from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from vidiel.models import AppSettings, DownloadRecord

APP_NAME = "ViDieL"


def _default_config_dir() -> Path:
    config_home = Path.home() / ".config"
    return config_home / APP_NAME


class SettingsStore:
    def __init__(self) -> None:
        self.config_dir = _default_config_dir()
        self.config_path = self.config_dir / "settings.json"

    def load(self) -> AppSettings:
        if not self.config_path.exists():
            return AppSettings(output_dir=str(Path.home() / "Downloads"))

        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppSettings(output_dir=str(Path.home() / "Downloads"))

        history = [
            DownloadRecord(**entry)
            for entry in raw.get("history", [])[:20]
            if isinstance(entry, dict)
        ]

        return AppSettings(
            output_dir=raw.get("output_dir") or str(Path.home() / "Downloads"),
            use_cookies=bool(raw.get("use_cookies", False)),
            history=history,
        )

    def save(self, settings: AppSettings) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = asdict(settings)
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def make_record(title: str, status: str, output_path: str, url: str) -> DownloadRecord:
        return DownloadRecord(
            title=title,
            status=status,
            output_path=output_path,
            url=url,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
