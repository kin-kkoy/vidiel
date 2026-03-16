from __future__ import annotations

import os
import re
from collections import deque
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from vidiel.dependencies import check_dependencies, install_guidance
from vidiel.downloader import DownloadWorker
from vidiel.models import (
    AUDIO_QUALITY_OPTIONS,
    VIDEO_QUALITY_OPTIONS,
    DownloadRecord,
    DownloadRequest,
    DownloadType,
    QueueItem,
)
from vidiel.settings import SettingsStore
from vidiel.updater import YtDlpUpdateWorker


class MainWindow(QMainWindow):
    URL_PATTERN = re.compile(r"https?://[^\s<>(){}\[\]\"']+")

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ViDieL")
        self.resize(1080, 760)

        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.dependency_status = check_dependencies()

        self.worker_thread: QThread | None = None
        self.worker: DownloadWorker | None = None
        self.update_thread: QThread | None = None
        self.update_worker: YtDlpUpdateWorker | None = None
        self.active_request: DownloadRequest | None = None
        self.pending_queue: deque[QueueItem] = deque()
        self.last_output_path = ""
        self._last_log_message = ""

        self._build_ui()
        self._apply_settings()
        self._refresh_dependencies_banner()
        self._refresh_history()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        hero = self._build_hero_card()
        root.addWidget(hero)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_download_panel())
        splitter.addWidget(self._build_sidebar())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

    def _build_hero_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("heroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        title = QLabel("Video downloads without the mess")
        title.setObjectName("heroTitle")

        subtitle = QLabel(
            "Paste a URL, choose video or MP3, and keep the output predictable. "
            "Everything stays local on this machine."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("heroSubtitle")

        self.dependency_banner = QLabel()
        self.dependency_banner.setObjectName("dependencyBanner")
        self.dependency_banner.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.dependency_banner)
        return card

    def _build_download_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/watch?v=...")
        form.addRow("Video URL", self.url_input)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Video", DownloadType.VIDEO)
        self.type_combo.addItem("Audio (MP3)", DownloadType.AUDIO)
        self.type_combo.currentIndexChanged.connect(self._refresh_quality_options)
        form.addRow("Download type", self.type_combo)

        self.quality_combo = QComboBox()
        form.addRow("Quality", self.quality_combo)

        self.custom_name_input = QLineEdit()
        self.custom_name_input.setPlaceholderText("Optional custom file name, e.g. abcd")
        form.addRow("Custom output name for the file", self.custom_name_input)

        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText(str(Path.home() / "Downloads"))
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._pick_output_dir)
        output_layout.addWidget(self.output_input, 1)
        output_layout.addWidget(browse_button)
        form.addRow("Output folder", output_row)

        layout.addLayout(form)

        self.filename_label = QLabel("File name: waiting for metadata")
        self.filename_label.setObjectName("mutedText")
        layout.addWidget(self.filename_label)

        self.import_drop_zone = QLabel("Drop a .txt or .md URL list here, or use Import URL List")
        self.import_drop_zone.setObjectName("dropZone")
        self.import_drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.import_drop_zone.setAcceptDrops(True)
        self.import_drop_zone.installEventFilter(self)
        layout.addWidget(self.import_drop_zone)

        self.queue_summary_label = QLabel("Queue: 0 waiting")
        self.queue_summary_label.setObjectName("queueSummary")
        layout.addWidget(self.queue_summary_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Idle")
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.download_button = QPushButton("Download Now")
        self.download_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.download_button.clicked.connect(self._handle_download_action)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_download)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.clicked.connect(self._open_output_folder)
        self.copy_path_button = QPushButton("Copy Final Path")
        self.copy_path_button.clicked.connect(self._copy_final_path)
        self.copy_path_button.setEnabled(False)
        self.import_list_button = QPushButton("Import URL List")
        self.import_list_button.clicked.connect(self._import_url_list)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced details")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.open_folder_button)
        buttons.addWidget(self.copy_path_button)
        buttons.addWidget(self.import_list_button)
        buttons.addWidget(self.advanced_toggle)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setPlaceholderText("The underlying yt-dlp command preview will appear here.")
        self.command_preview.setMaximumHeight(96)
        self.command_preview.hide()
        layout.addWidget(self.command_preview)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Activity log")
        self.log_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.log_output, 1)

        return panel

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_settings_group())
        layout.addWidget(self._build_history_group(), 1)
        return sidebar

    def _build_settings_group(self) -> QWidget:
        group = QGroupBox("Settings")
        group.setObjectName("settingsGroup")
        form = QFormLayout(group)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.default_folder_input = QLineEdit()
        self.default_folder_input.setPlaceholderText(str(Path.home() / "Downloads"))
        folder_button = QPushButton("Choose")
        folder_button.clicked.connect(self._pick_default_dir)
        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        folder_layout.addWidget(self.default_folder_input, 1)
        folder_layout.addWidget(folder_button)
        form.addRow("Default folder", folder_row)

        self.cookies_checkbox = QCheckBox("Try browser cookies (Firefox)")
        form.addRow("Browser cookies", self.cookies_checkbox)

        self.fragments_combo = QComboBox()
        self.fragments_combo.addItem("1 (Lowest load)", 1)
        self.fragments_combo.addItem("4 (Recommended)", 4)
        self.fragments_combo.addItem("8 (Fastest)", 8)
        form.addRow("Concurrent fragments", self.fragments_combo)

        self.performance_combo = QComboBox()
        self.performance_combo.addItem("Balanced", "balanced")
        self.performance_combo.addItem("Low memory / background", "low_memory")
        self.performance_combo.addItem("Max speed", "max_speed")
        self.performance_combo.currentIndexChanged.connect(self._apply_performance_preset)
        form.addRow("Performance mode", self.performance_combo)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Built-in downloader", "native")
        self.backend_combo.addItem("aria2c if installed", "aria2c")
        form.addRow("Download backend", self.backend_combo)

        actions_row = QWidget()
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        self.update_ytdlp_button = QPushButton("Update yt-dlp")
        self.update_ytdlp_button.clicked.connect(self._start_ytdlp_update)
        save_button = QPushButton("Save settings")
        save_button.clicked.connect(self._save_settings)
        actions_layout.addWidget(self.update_ytdlp_button)
        actions_layout.addWidget(save_button)
        form.addRow("", actions_row)
        return group

    def _build_history_group(self) -> QWidget:
        group = QGroupBox("Recent Downloads")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._open_history_item)
        layout.addWidget(self.history_list, 1)

        active_label = QLabel("Active Job")
        active_label.setObjectName("sectionLabel")
        layout.addWidget(active_label)

        self.active_item_label = QLabel("Nothing downloading right now.")
        self.active_item_label.setObjectName("activeJobCard")
        self.active_item_label.setWordWrap(True)
        layout.addWidget(self.active_item_label)

        queue_header = QHBoxLayout()
        queue_label = QLabel("Queue")
        queue_label.setObjectName("sectionLabel")
        queue_header.addWidget(queue_label)
        queue_header.addStretch(1)

        self.move_up_queue_button = QPushButton("Move Up")
        self.move_up_queue_button.clicked.connect(self._move_queue_item_up)
        self.move_down_queue_button = QPushButton("Move Down")
        self.move_down_queue_button.clicked.connect(self._move_queue_item_down)
        self.remove_queue_button = QPushButton("Remove Selected")
        self.remove_queue_button.clicked.connect(self._remove_selected_queue_item)
        self.clear_queue_button = QPushButton("Clear Queue")
        self.clear_queue_button.clicked.connect(self._clear_queue)
        queue_header.addWidget(self.move_up_queue_button)
        queue_header.addWidget(self.move_down_queue_button)
        queue_header.addWidget(self.remove_queue_button)
        queue_header.addWidget(self.clear_queue_button)
        layout.addLayout(queue_header)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queueList")
        layout.addWidget(self.queue_list, 1)
        self._refresh_queue_list()
        return group

    def _apply_settings(self) -> None:
        self.output_input.setText(self.settings.output_dir)
        self.default_folder_input.setText(self.settings.output_dir)
        self.cookies_checkbox.setChecked(self.settings.use_cookies)
        self._refresh_backend_options()
        fragments_index = self.fragments_combo.findData(self.settings.concurrent_fragments)
        if fragments_index >= 0:
            self.fragments_combo.setCurrentIndex(fragments_index)
        performance_index = self.performance_combo.findData(self.settings.performance_mode)
        if performance_index >= 0:
            self.performance_combo.setCurrentIndex(performance_index)
        backend_index = self.backend_combo.findData(self.settings.downloader_backend)
        if backend_index >= 0:
            self.backend_combo.setCurrentIndex(backend_index)

        self._refresh_quality_options()

    def _refresh_dependencies_banner(self) -> None:
        if self.dependency_status.ok:
            aria2c_note = " aria2c is available for speed mode." if self.dependency_status.aria2c else " aria2c is optional and not installed."
            self.dependency_banner.setText(
                "Dependencies ready: yt-dlp, ffmpeg, and ffprobe are available." + aria2c_note
            )
            self.dependency_banner.setProperty("state", "ok")
        else:
            self.dependency_banner.setText(install_guidance(self.dependency_status.missing))
            self.dependency_banner.setProperty("state", "error")
        self.dependency_banner.style().unpolish(self.dependency_banner)
        self.dependency_banner.style().polish(self.dependency_banner)
        self._refresh_backend_options()

    def _refresh_backend_options(self) -> None:
        if not hasattr(self, "backend_combo"):
            return
        current_value = self.backend_combo.currentData()
        self.backend_combo.clear()
        self.backend_combo.addItem("Built-in downloader", "native")
        aria2c_label = "aria2c (Installed)" if self.dependency_status.aria2c else "aria2c (Not installed)"
        self.backend_combo.addItem(aria2c_label, "aria2c")
        index = self.backend_combo.findData(current_value)
        if index >= 0:
            self.backend_combo.setCurrentIndex(index)

    def _refresh_quality_options(self) -> None:
        current_type = self.current_download_type()
        self.quality_combo.clear()
        options = AUDIO_QUALITY_OPTIONS if current_type == DownloadType.AUDIO else VIDEO_QUALITY_OPTIONS
        for option in options:
            self.quality_combo.addItem(option.label, option.key)

    def _refresh_history(self) -> None:
        selected_row = self.history_list.currentRow()
        self.history_list.clear()
        for record in self.settings.history:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.history_list.addItem(item)
            widget = self._build_history_item_widget(record)
            item.setSizeHint(widget.sizeHint())
            self.history_list.setItemWidget(item, widget)
        if self.history_list.count():
            self.history_list.setCurrentRow(min(selected_row, self.history_list.count() - 1))

    def _toggle_advanced(self, checked: bool) -> None:
        self.command_preview.setVisible(checked)

    def current_download_type(self) -> DownloadType:
        value = self.type_combo.currentData()
        return value if isinstance(value, DownloadType) else DownloadType(value)

    def _pick_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose Output Folder", self.output_input.text())
        if directory:
            self.output_input.setText(directory)

    def _pick_default_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose Default Folder", self.default_folder_input.text())
        if directory:
            self.default_folder_input.setText(directory)

    def _save_settings(self) -> None:
        self.settings.output_dir = self.default_folder_input.text().strip() or str(Path.home() / "Downloads")
        self.settings.use_cookies = self.cookies_checkbox.isChecked()
        self.settings.concurrent_fragments = int(self.fragments_combo.currentData())
        self.settings.performance_mode = str(self.performance_combo.currentData())
        self.settings.downloader_backend = str(self.backend_combo.currentData())
        self.settings_store.save(self.settings)
        self.output_input.setText(self.settings.output_dir)
        self._append_log("Settings saved.")

    def _start_ytdlp_update(self) -> None:
        if self.update_thread:
            return

        self.update_ytdlp_button.setEnabled(False)
        self.update_thread = QThread(self)
        self.update_worker = YtDlpUpdateWorker()
        self.update_worker.moveToThread(self.update_thread)

        self.update_thread.started.connect(self.update_worker.run)
        self.update_worker.status_changed.connect(self._append_log)
        self.update_worker.finished.connect(self._finish_ytdlp_update)
        self.update_worker.finished.connect(self.update_thread.quit)
        self.update_thread.finished.connect(self._cleanup_update_worker)
        self.update_thread.start()

    def _finish_ytdlp_update(self, ok: bool, message: str) -> None:
        self._append_log(message)
        self.dependency_status = check_dependencies()
        self._refresh_dependencies_banner()
        if ok:
            QMessageBox.information(self, "yt-dlp Updated", message)
        else:
            QMessageBox.warning(self, "yt-dlp Update Failed", message)

    def _cleanup_update_worker(self) -> None:
        self.update_ytdlp_button.setEnabled(True)
        if self.update_worker:
            self.update_worker.deleteLater()
        if self.update_thread:
            self.update_thread.deleteLater()
        self.update_worker = None
        self.update_thread = None

    def _apply_performance_preset(self) -> None:
        mode = self.performance_combo.currentData()
        if mode == "low_memory":
            self.fragments_combo.setCurrentIndex(self.fragments_combo.findData(1))
            self.backend_combo.setCurrentIndex(self.backend_combo.findData("native"))
        elif mode == "max_speed":
            self.fragments_combo.setCurrentIndex(self.fragments_combo.findData(8))
        else:
            self.fragments_combo.setCurrentIndex(self.fragments_combo.findData(4))
            if self.backend_combo.currentData() not in {"native", "aria2c"}:
                self.backend_combo.setCurrentIndex(self.backend_combo.findData("native"))

    def _handle_download_action(self) -> None:
        request = self._build_request_from_form()
        if not request:
            return

        if self.worker_thread:
            self._enqueue_request(request)
            return

        self._launch_request(request)

    def _build_request_from_form(self) -> DownloadRequest | None:
        return self._build_request_from_url(self.url_input.text().strip())

    def _build_request_from_url(
        self,
        url: str,
        *,
        download_type: DownloadType | None = None,
        custom_name: str = "",
    ) -> DownloadRequest | None:
        if not self.dependency_status.ok:
            QMessageBox.warning(self, "Missing Dependencies", install_guidance(self.dependency_status.missing))
            return None

        output_dir = self.output_input.text().strip() or self.settings.output_dir

        if not url:
            QMessageBox.warning(self, "Missing URL", "Paste a video URL first.")
            return None
        if not Path(output_dir).exists():
            QMessageBox.warning(self, "Invalid Folder", "Choose an existing output folder.")
            return None

        backend = self.settings.downloader_backend
        if backend == "aria2c" and not self.dependency_status.aria2c:
            backend = "native"
            self._append_log("aria2c is not installed. Falling back to the built-in downloader.")
            QMessageBox.warning(
                self,
                "aria2c Not Installed",
                "aria2c is not installed on this system, so ViDieL will use the built-in downloader instead.",
            )

        resolved_type = download_type or self.current_download_type()
        quality = self.quality_combo.currentData()
        if resolved_type != self.current_download_type():
            quality = self._default_quality_for_type(resolved_type)

        return DownloadRequest(
            url=url,
            download_type=resolved_type,
            quality=quality,
            output_dir=os.path.abspath(output_dir),
            use_cookies=self.cookies_checkbox.isChecked(),
            custom_name=custom_name or self.custom_name_input.text().strip(),
            concurrent_fragments=self.settings.concurrent_fragments,
            downloader_backend=backend,
            performance_mode=self.settings.performance_mode,
            downloader_path=self.dependency_status.aria2c if backend == "aria2c" else "",
        )

    def _import_url_list(self) -> None:
        QMessageBox.information(
            self,
            "Import Format Reminder",
            "Supported import formats:\n\n"
            "- url\n"
            "- mp3 | url\n"
            "- mp4 | url\n"
            "- mp3 | custom name | url\n"
            "- mp4 | custom name | url\n\n"
            "Braces and dash bullets are fine.\n\n"
            "Example:\n"
            "{\n"
            "  - mp3 | cello-cover | https://example.com/a\n"
            "  - mp4 | https://example.com/b\n"
            "}",
        )

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import URL List",
            str(Path.home()),
            "Text or Markdown (*.txt *.md *.markdown);;All Files (*)",
        )
        if not file_path:
            return

        self._import_url_list_from_path(file_path)

    def _import_url_list_from_path(self, file_path: str) -> None:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not read file:\n{exc}")
            return

        entries = self._parse_import_entries(content)
        if not entries:
            QMessageBox.warning(
                self,
                "No URLs Found",
                "No valid import entries were found.\n\n"
                "Supported formats:\n"
                "- url\n"
                "- mp3 | url\n"
                "- mp4 | url\n"
                "- mp3 | custom name | url\n"
                "- mp4 | custom name | url",
            )
            return

        requests: list[DownloadRequest] = []
        invalid_count = 0
        for entry in entries:
            request = self._build_request_from_url(
                entry["url"],
                download_type=entry["download_type"],
                custom_name=entry["custom_name"],
            )
            if request:
                requests.append(request)
            else:
                invalid_count += 1

        if not requests:
            return

        started_now = False
        if self.worker_thread:
            for request in requests:
                self._enqueue_request(request)
        else:
            first_request, *remaining = requests
            self._launch_request(first_request)
            started_now = True
            for request in remaining:
                self._enqueue_request(request)

        summary = f"Imported {len(requests)} URL(s)"
        if started_now:
            summary += ": 1 started, the rest queued."
        else:
            summary += " into the queue."
        if invalid_count:
            summary += f" Skipped {invalid_count} invalid item(s)."
        self._append_log(summary)
        self.status_label.setText(summary)

    @classmethod
    def _extract_urls_from_text(cls, content: str) -> list[str]:
        seen: set[str] = set()
        urls: list[str] = []
        for match in cls.URL_PATTERN.findall(content):
            cleaned = match.rstrip(".,)")
            if cleaned not in seen:
                seen.add(cleaned)
                urls.append(cleaned)
        return urls

    @classmethod
    def _parse_import_entries(cls, content: str) -> list[dict]:
        entries: list[dict] = []
        seen: set[tuple[str, str, str]] = set()

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line in {"{", "}"} or line.startswith("#"):
                continue

            line = re.sub(r"^[-*]\s*", "", line).strip()
            url_match = cls.URL_PATTERN.search(line)
            if not url_match:
                continue

            url = url_match.group(0).rstrip(".,)")
            prefix = line[: url_match.start()].strip()
            prefix = prefix.rstrip("|").strip()
            parts = [part.strip() for part in prefix.split("|") if part.strip()] if prefix else []

            download_type: DownloadType | None = None
            custom_name = ""

            if parts:
                first = parts[0].lower()
                if first in {"mp3", "audio"}:
                    download_type = DownloadType.AUDIO
                    parts = parts[1:]
                elif first in {"mp4", "video"}:
                    download_type = DownloadType.VIDEO
                    parts = parts[1:]

            if parts:
                custom_name = parts[0]

            key = (url, download_type.value if download_type else "current", custom_name)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "url": url,
                    "download_type": download_type,
                    "custom_name": custom_name,
                }
            )

        return entries

    @staticmethod
    def _default_quality_for_type(download_type: DownloadType) -> str:
        if download_type == DownloadType.AUDIO:
            return AUDIO_QUALITY_OPTIONS[0].key
        return VIDEO_QUALITY_OPTIONS[0].key

    def _launch_request(self, request: DownloadRequest) -> None:
        self.active_request = request
        self._set_running_state(True)
        self._set_progress_state("active")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Starting...")
        self.filename_label.setText("File name: resolving metadata...")
        self.status_label.setText("Preparing download...")
        self.command_preview.clear()
        self._append_log(f"Starting: {request.url}")
        self._refresh_active_item_label()
        self.url_input.clear()
        self.custom_name_input.clear()

        self.worker_thread = QThread(self)
        self.worker = DownloadWorker(request)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.status_changed.connect(self._on_status)
        self.worker.title_resolved.connect(self._on_title_resolved)
        self.worker.command_ready.connect(self.command_preview.setPlainText)
        self.worker.finished.connect(self._on_download_finished)
        self.worker.failed.connect(self._on_download_failed)
        self.worker.cancelled.connect(self._on_download_cancelled)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.cancelled.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)

        self.worker_thread.start()

    def _enqueue_request(self, request: DownloadRequest) -> None:
        label = self._format_queue_label(request)
        self.pending_queue.append(QueueItem(request=request, label=label))
        self._refresh_queue_list()
        self._append_log(f"Added to queue: {request.url}")
        self.url_input.clear()
        self.custom_name_input.clear()
        self.status_label.setText(f"Queued {len(self.pending_queue)} item(s) after the current download.")

    def _cancel_download(self) -> None:
        if self.worker:
            self._set_progress_state("cancelled")
            self.worker.cancel()

    def _on_status(self, message: str) -> None:
        self.status_label.setText(message)
        if message.startswith("Downloading "):
            self.progress_bar.setFormat(message.removeprefix("Downloading "))
        elif message.startswith("Processing "):
            self._set_progress_state("processing")
            self.progress_bar.setFormat("Processing...")
        if not message.startswith("Downloading "):
            self._append_log(message)

    def _on_title_resolved(self, title: str) -> None:
        self.filename_label.setText(f"File name: {title}")

    def _on_download_finished(self, result: dict) -> None:
        output_path = result.get("output_path", "")
        self.last_output_path = output_path
        self.copy_path_button.setEnabled(bool(output_path))
        self.progress_bar.setValue(100)
        self._set_progress_state("success")
        self.progress_bar.setFormat("Complete")
        self.status_label.setText("Download complete.")
        self.filename_label.setText(f"File name: {result.get('title', 'Completed download')}")
        self._append_log(f"Saved to: {output_path or 'Unknown path'}")
        url = self.active_request.url if self.active_request else result.get("url", "")
        self._record_history(result.get("title", "Unknown"), "success", output_path, url)
        self._append_log(self._queue_status_message())

    def _on_download_failed(self, message: str) -> None:
        self._set_progress_state("error")
        self.progress_bar.setFormat("Failed")
        self.status_label.setText("Download failed.")
        self._append_log(f"Error: {message}")
        failed_url = self.active_request.url if self.active_request else self.url_input.text().strip()
        self._record_history("Failed download", "failed", "", failed_url)
        self._append_log(self._queue_status_message())
        QMessageBox.critical(self, "Download Failed", message)

    def _on_download_cancelled(self, message: str) -> None:
        self._set_progress_state("cancelled")
        self.progress_bar.setFormat("Cancelled")
        self.status_label.setText("Cancelled.")
        self._append_log(message)
        cancelled_url = self.active_request.url if self.active_request else self.url_input.text().strip()
        self._record_history("Cancelled download", "cancelled", "", cancelled_url)
        self._append_log(self._queue_status_message())

    def _cleanup_worker(self) -> None:
        self._set_running_state(False)
        if self.worker:
            self.worker.deleteLater()
        if self.worker_thread:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None
        self.active_request = None

        if self.pending_queue:
            next_item = self.pending_queue.popleft()
            self._refresh_queue_list()
            self._append_log(f"Starting next queued item: {next_item.request.url}")
            self._launch_request(next_item.request)
        else:
            self._set_progress_state("idle")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Idle")
            self.status_label.setText("Ready")
            self.filename_label.setText("File name: waiting for metadata")
            self._refresh_active_item_label()

    def _set_running_state(self, running: bool) -> None:
        queue_count = len(self.pending_queue)
        self.download_button.setText(f"Add To Queue ({queue_count})" if running and queue_count else "Add To Queue" if running else "Download Now")
        self.cancel_button.setEnabled(running)
        self.cancel_button.setVisible(running)
        has_items = bool(self.pending_queue)
        self.move_up_queue_button.setEnabled(has_items)
        self.move_down_queue_button.setEnabled(has_items)
        self.remove_queue_button.setEnabled(has_items)
        self.clear_queue_button.setEnabled(has_items)
        self.queue_summary_label.setText(
            f"Queue: {queue_count} waiting" + (" | 1 active" if running else "")
        )

    def _append_log(self, message: str) -> None:
        if not message or message == self._last_log_message:
            return
        self._last_log_message = message
        self.log_output.appendPlainText(message)

    def _record_history(self, title: str, status: str, output_path: str, url: str) -> None:
        record = self.settings_store.make_record(title, status, output_path, url)
        self.settings.history.insert(0, record)
        self.settings.history = self.settings.history[:20]
        self.settings_store.save(self.settings)
        self._refresh_history()

    def _open_history_item(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, DownloadRecord):
            return
        if record.output_path:
            path = Path(record.output_path)
            self.last_output_path = record.output_path
            self.copy_path_button.setEnabled(True)
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                self._append_log(f"Opened: {record.title}")
                return
        QMessageBox.information(self, "File Not Found", "That recent file is no longer available at its saved path.")

    def _open_output_folder(self) -> None:
        target = self.last_output_path or self.output_input.text().strip() or self.settings.output_dir
        if not target:
            return
        path = Path(target)
        folder = path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _copy_final_path(self) -> None:
        if not self.last_output_path:
            return
        QApplication.clipboard().setText(self.last_output_path)
        self._append_log("Copied final file path to clipboard.")

    def _refresh_queue_list(self) -> None:
        if not hasattr(self, "queue_list"):
            return
        selected_row = self.queue_list.currentRow()
        self.queue_list.clear()
        for index, item in enumerate(self.pending_queue, start=1):
            list_item = QListWidgetItem()
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.queue_list.addItem(list_item)
            widget = self._build_queue_item_widget(index, item)
            list_item.setSizeHint(widget.sizeHint())
            self.queue_list.setItemWidget(list_item, widget)
        if self.queue_list.count():
            self.queue_list.setCurrentRow(min(selected_row, self.queue_list.count() - 1))
        self._set_running_state(self.worker_thread is not None)

    def _move_queue_item_up(self) -> None:
        row = self.queue_list.currentRow()
        if row <= 0:
            return
        items = list(self.pending_queue)
        items[row - 1], items[row] = items[row], items[row - 1]
        self.pending_queue = deque(items)
        self._refresh_queue_list()
        self.queue_list.setCurrentRow(row - 1)

    def _move_queue_item_down(self) -> None:
        row = self.queue_list.currentRow()
        items = list(self.pending_queue)
        if row < 0 or row >= len(items) - 1:
            return
        items[row], items[row + 1] = items[row + 1], items[row]
        self.pending_queue = deque(items)
        self._refresh_queue_list()
        self.queue_list.setCurrentRow(row + 1)

    def _refresh_active_item_label(self) -> None:
        if not hasattr(self, "active_item_label"):
            return
        if not self.active_request:
            self.active_item_label.setText("Nothing downloading right now.")
            return
        mode = "MP3 audio" if self.active_request.download_type == DownloadType.AUDIO else "Video"
        quality = self.active_request.quality if self.active_request.quality != "best" else "Best available"
        self.active_item_label.setText(
            f"{mode} | {quality}\n{self.active_request.url}\n"
            f"Name: {self.active_request.custom_name or 'Auto'}\n"
            f"Output: {self.active_request.output_dir}"
        )

    def _set_progress_state(self, state: str) -> None:
        self.progress_bar.setProperty("state", state)
        self.progress_bar.style().unpolish(self.progress_bar)
        self.progress_bar.style().polish(self.progress_bar)

    def _remove_selected_queue_item(self) -> None:
        row = self.queue_list.currentRow()
        if row < 0:
            return
        items = list(self.pending_queue)
        if row >= len(items):
            return
        removed = items.pop(row)
        self.pending_queue = deque(items)
        self._refresh_queue_list()
        self._append_log(f"Removed from queue: {removed.request.url}")
        self.status_label.setText(self._queue_status_message())

    def _clear_queue(self) -> None:
        if not self.pending_queue:
            return
        self.pending_queue.clear()
        self._refresh_queue_list()
        self._append_log("Cleared pending queue.")
        self.status_label.setText(self._queue_status_message())

    @staticmethod
    def _format_queue_label(request: DownloadRequest) -> str:
        mode = "MP3" if request.download_type == DownloadType.AUDIO else "Video"
        quality = request.quality if request.quality != "best" else "Best"
        return f"{mode} | {quality} | {request.url}"

    def _queue_status_message(self) -> str:
        if self.pending_queue:
            return f"{len(self.pending_queue)} item(s) waiting in queue."
        return "Queue is empty."

    def _build_history_item_widget(self, record: DownloadRecord) -> QWidget:
        widget = QWidget()
        widget.setObjectName("listCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        title = QLabel(record.title or "Unknown download")
        title.setObjectName("listTitle")
        title.setWordWrap(True)
        top_row.addWidget(title, 1)

        media_type = QLabel(self._infer_media_type(record.output_path))
        media_type.setObjectName("statusChip")
        media_type.setProperty("status", "media")
        top_row.addWidget(media_type, 0, Qt.AlignmentFlag.AlignTop)

        status = QLabel(record.status.capitalize())
        status.setObjectName("statusChip")
        status.setProperty("status", record.status)
        top_row.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)

        meta = QLabel(record.timestamp)
        meta.setObjectName("listMeta")

        detail_value = record.output_path or record.url
        detail = QLabel(detail_value)
        detail.setObjectName("listDetail")
        detail.setWordWrap(True)

        layout.addLayout(top_row)
        layout.addWidget(meta)
        layout.addWidget(detail)
        return widget

    def _build_queue_item_widget(self, index: int, item: QueueItem) -> QWidget:
        widget = QWidget()
        widget.setObjectName("listCard")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        mode = "MP3 audio" if item.request.download_type == DownloadType.AUDIO else "Video"
        quality = item.request.quality if item.request.quality != "best" else "Best"

        title = QLabel(f"{index}. {mode} | {quality}")
        title.setObjectName("listTitle")
        top_row.addWidget(title, 1)

        badge = QLabel("Queued")
        badge.setObjectName("statusChip")
        badge.setProperty("status", "queued")
        top_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        url_label = QLabel(item.request.url)
        url_label.setObjectName("listDetail")
        url_label.setWordWrap(True)

        output_label = QLabel(f"Output: {item.request.output_dir}")
        output_label.setObjectName("listMeta")
        output_label.setWordWrap(True)

        if item.request.custom_name:
            name_label = QLabel(f"Name: {item.request.custom_name}")
            name_label.setObjectName("listMeta")
            name_label.setWordWrap(True)
        else:
            name_label = None

        layout.addLayout(top_row)
        layout.addWidget(url_label)
        if name_label:
            layout.addWidget(name_label)
        layout.addWidget(output_label)
        return widget

    @staticmethod
    def _infer_media_type(output_path: str) -> str:
        suffix = Path(output_path).suffix.lower()
        if suffix == ".mp3":
            return "MP3"
        if suffix == ".mp4":
            return "MP4"
        if suffix:
            return suffix.removeprefix(".").upper()
        return "FILE"

    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        if source is getattr(self, "import_drop_zone", None):
            event_type = event.type()
            if event_type == QEvent.Type.DragEnter:
                mime = event.mimeData()
                if mime.hasUrls():
                    event.acceptProposedAction()
                    self.import_drop_zone.setProperty("dragging", True)
                    self.import_drop_zone.style().unpolish(self.import_drop_zone)
                    self.import_drop_zone.style().polish(self.import_drop_zone)
                    return True
            elif event_type == QEvent.Type.DragLeave:
                self.import_drop_zone.setProperty("dragging", False)
                self.import_drop_zone.style().unpolish(self.import_drop_zone)
                self.import_drop_zone.style().polish(self.import_drop_zone)
                return True
            elif event_type == QEvent.Type.Drop:
                self.import_drop_zone.setProperty("dragging", False)
                self.import_drop_zone.style().unpolish(self.import_drop_zone)
                self.import_drop_zone.style().polish(self.import_drop_zone)
                urls = event.mimeData().urls()
                if not urls:
                    return True
                local_path = urls[0].toLocalFile()
                if local_path and Path(local_path).suffix.lower() in {".txt", ".md", ".markdown"}:
                    self._import_url_list_from_path(local_path)
                else:
                    QMessageBox.warning(self, "Unsupported File", "Drop a .txt or .md file with URLs.")
                event.acceptProposedAction()
                return True
        return super().eventFilter(source, event)


def build_stylesheet() -> str:
    return """
        QWidget {
            color: #e8edf4;
            font-family: "Noto Sans", "DejaVu Sans", sans-serif;
            font-size: 14px;
        }
        QMainWindow, QWidget#appRoot {
            background: #0b0f14;
        }
        QLabel {
            background: transparent;
        }
        QFrame#heroCard, QFrame#panel, QGroupBox {
            background: #161c24;
            border: 1px solid #273241;
            border-radius: 18px;
        }
        QLabel#heroTitle {
            font-size: 28px;
            font-weight: 700;
        }
        QLabel#heroSubtitle {
            color: #a9b5c5;
            font-size: 14px;
        }
        QLabel#dependencyBanner {
            margin-top: 8px;
            padding: 10px 12px;
            border-radius: 12px;
            background: #1d2530;
            color: #b9c6d8;
        }
        QLabel#dependencyBanner[state="ok"] {
            background: #14281e;
            color: #9ee0b5;
            border: 1px solid #245739;
        }
        QLabel#dependencyBanner[state="error"] {
            background: #2d1818;
            color: #ffb4b4;
            border: 1px solid #6d2b2b;
        }
        QLabel#mutedText {
            color: #95a4b7;
        }
        QLabel#statusLabel {
            font-weight: 600;
            color: #d6e2f0;
        }
        QLabel#queueSummary {
            color: #79a5ff;
            font-weight: 600;
        }
        QLabel#dropZone {
            background: #101720;
            border: 1px dashed #35506f;
            border-radius: 14px;
            color: #a8bfd9;
            padding: 12px;
            font-weight: 600;
        }
        QLabel#dropZone[dragging="true"] {
            background: #142338;
            border: 1px dashed #5f95ff;
            color: #d6e6ff;
        }
        QLabel#sectionLabel {
            color: #dce7f5;
            font-weight: 700;
            padding-top: 6px;
        }
        QLabel#activeJobCard {
            background: #101720;
            border: 1px solid #2a3645;
            border-radius: 14px;
            padding: 12px;
            color: #b8c4d4;
        }
        QFormLayout QLabel {
            color: #b8c4d4;
            font-weight: 600;
        }
        QLineEdit, QComboBox, QPlainTextEdit, QListWidget {
            background: #0e141b;
            border: 1px solid #2a3645;
            border-radius: 12px;
            padding: 10px 12px;
            selection-background-color: #2f6fed;
        }
        QListWidget::item {
            border: none;
            padding: 4px 0;
        }
        QListWidget::item:selected {
            background: transparent;
        }
        QWidget#listCard {
            background: #101720;
            border: 1px solid #243241;
            border-radius: 14px;
        }
        QLabel#listTitle {
            font-weight: 700;
            color: #edf3fb;
        }
        QLabel#listMeta {
            color: #89a0bb;
            font-size: 12px;
        }
        QLabel#listDetail {
            color: #bfd0e2;
            font-size: 12px;
        }
        QLabel#statusChip {
            padding: 4px 8px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            background: #1d2530;
            color: #cfe0f1;
        }
        QLabel#statusChip[status="success"] {
            background: #163020;
            color: #9ee0b5;
        }
        QLabel#statusChip[status="failed"] {
            background: #381b1b;
            color: #ffb4b4;
        }
        QLabel#statusChip[status="cancelled"] {
            background: #263241;
            color: #b6c3d1;
        }
        QLabel#statusChip[status="queued"] {
            background: #1b2740;
            color: #96bbff;
        }
        QLabel#statusChip[status="media"] {
            background: #2d2437;
            color: #d7b5ff;
        }
        QPlainTextEdit, QListWidget {
            padding: 12px;
        }
        QPlainTextEdit {
            font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
        }
        QComboBox::drop-down {
            border: none;
            width: 28px;
        }
        QPushButton, QToolButton {
            background: #2f6fed;
            border: none;
            border-radius: 12px;
            padding: 10px 14px;
            font-weight: 600;
        }
        QPushButton:hover, QToolButton:hover {
            background: #4580f5;
        }
        QPushButton:disabled {
            background: #263241;
            color: #7d8998;
        }
        QProgressBar {
            background: #0e141b;
            border: 1px solid #2a3645;
            border-radius: 10px;
            min-height: 16px;
            text-align: center;
            font-weight: 700;
        }
        QProgressBar::chunk {
            background: #2f6fed;
            border-radius: 8px;
        }
        QProgressBar[state="processing"]::chunk {
            background: #d99b3a;
        }
        QProgressBar[state="success"]::chunk {
            background: #3fc17d;
        }
        QProgressBar[state="error"]::chunk {
            background: #d85d5d;
        }
        QProgressBar[state="cancelled"]::chunk {
            background: #66788d;
        }
        QProgressBar[state="idle"]::chunk {
            background: #3fc17d;
            border-radius: 8px;
        }
        QCheckBox, QGroupBox {
            color: #dce7f5;
        }
        QGroupBox {
            margin-top: 8px;
            padding: 18px;
            font-weight: 600;
        }
        QGroupBox#settingsGroup {
            padding: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
    """
