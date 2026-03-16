# ViDieL

Local-only desktop video downloader and converter for Linux and Windows, built with Python, `PySide6`, `yt-dlp`, and `ffmpeg`.

## What it does

- Download a video from a URL
- Extract audio as MP3
- Choose output folder
- Track progress and activity logs
- Persist simple local settings and recent download history
- Show dependency guidance if `yt-dlp` or `ffmpeg` are missing
- Preview the underlying `yt-dlp` command in an optional advanced area

Quick links:
- [Linux setup](#linux-setup)
- [Windows setup and packaging](#windows-setup-and-packaging)

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
- bundle `aria2c` when present so speed mode works in packaged builds

Current packaging helper:

```bash
./packaging/package_linux.sh
```

This script:

- installs `PyInstaller` into the project venv
- builds a Linux desktop app bundle
- includes `aria2c` in the package if it is installed on the system

For Windows packaging, see the [Windows setup and packaging](#windows-setup-and-packaging) section and use:

```bat
packaging\package_windows.bat
```

## yt-dlp updates

The app now includes an `Update yt-dlp` button in Settings for normal Python/venv installs. It runs:

```bash
python -m pip install --upgrade yt-dlp
```

Packaged builds currently do not self-update their bundled `yt-dlp`. For now, the packaged release path is:

- rebuild the app bundle when you want a newer bundled `yt-dlp`
- or keep using the editable/venv install if you want in-app `yt-dlp` upgrades

For Windows later:

- keep the same Python service modules
- swap Linux path defaults for Windows app-data paths
- review browser cookies support and file opening behavior
- package with `PyInstaller`

## Windows setup and packaging

This project can be built into a Windows `.exe`, but you should build it on Windows, not from Linux.

### What you need

- Windows 10 or 11
- Python 3.11+ installed
- `ffmpeg` installed and available on `PATH`
- optional: `aria2c` installed and available on `PATH` if you want it bundled into the packaged build

### 1. Get the project

Clone the repo on Windows or copy the project folder over.

```powershell
git clone <your-repo-url>
cd ViDieL
```

### 2. Create a virtual environment

In PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
pip install -e .
```

If PowerShell blocks script activation, you can instead use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

### 3. Run the app from source

```powershell
vidiel
```

### 4. Build the Windows app

From the project root:

```bat
packaging\package_windows.bat
```

If the build succeeds, the packaged app will be created in:

```text
dist\ViDieL
```

Run it with:

```bat
dist\ViDieL\ViDieL.exe
```

### 5. What to check after building

- the app launches normally
- MP4 downloads work
- MP3 downloads work
- the backend selector shows `aria2c (Installed)` if you installed it before packaging
- the `Update yt-dlp` button is unavailable in the packaged build

### Windows dependencies

#### ffmpeg

ViDieL still expects `ffmpeg` and `ffprobe` to be available on the system.

Fastest practical path:
- install `ffmpeg`
- ensure both `ffmpeg.exe` and `ffprobe.exe` are on `PATH`

#### aria2c

Optional. If `aria2c.exe` is on `PATH` when you run `packaging\package_windows.bat`, it will be bundled into the packaged app automatically.

### Windows notes

- packaged builds currently do not self-update bundled `yt-dlp`
- if you want a newer bundled `yt-dlp`, rebuild the packaged app
- if you want in-app `yt-dlp` updates, use the venv/source install instead of the packaged build

## v2 ideas

- Queue multiple URLs cleanly
- Basic format inspection before download
- Select browser for cookies instead of fixed Firefox
- Metadata preview before starting the download
- Retry action for failed downloads
