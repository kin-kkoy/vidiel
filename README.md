# ViDieL

Local-only desktop video downloader and converter for Linux, built with Python, `PySide6`, `yt-dlp`, and `ffmpeg`.

## What it does

- Download a video from a URL
- Extract audio as MP3
- Choose output folder
- Track progress and activity logs
- Persist simple local settings and recent download history
- Show dependency guidance if `yt-dlp` or `ffmpeg` are missing
- Preview the underlying `yt-dlp` command in an optional advanced area

## Stack choice

`PySide6` is the fastest route here to a desktop UI that still feels polished and maintainable. The app keeps the backend simple:

- Qt UI layer in one main window
- One worker thread for download/conversion work
- `yt-dlp` Python API for reliable progress hooks and error handling
- Local JSON settings in `~/.config/ViDieL/settings.json`

## Project structure

```text
src/vidiel/
  app.py
  __main__.py
  dependencies.py
  downloader.py
  models.py
  settings.py
  ui/
    main_window.py
requirements.txt
README.md
```

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
vidiel
```

## Linux setup

Install system tools first:

```bash
# Debian / Ubuntu
sudo apt install ffmpeg

# Fedora
sudo dnf install ffmpeg

# Arch
sudo pacman -S ffmpeg
```

Install `yt-dlp` either in the app venv or with `pipx`:

```bash
pip install -e .
```

The app checks for `yt-dlp`, `ffmpeg`, and `ffprobe` at startup and shows clear guidance if they are missing.

## Packaging later

For Linux packaging later, the practical path is:

- `PyInstaller` for a single-folder build
- or `briefcase` if you want a more app-like packaging workflow later
- keep `ffmpeg` external for Linux first instead of bundling it

For Windows later:

- keep the same Python service modules
- swap Linux path defaults for Windows app-data paths
- review browser cookies support and file opening behavior
- package with `PyInstaller`

## v2 ideas

- Queue multiple URLs cleanly
- Basic format inspection before download
- Select browser for cookies instead of fixed Firefox
- Metadata preview before starting the download
- Retry action for failed downloads
