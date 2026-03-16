@echo off
setlocal

set "ROOT_DIR=%~dp0.."
pushd "%ROOT_DIR%"

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. Create it on Windows and install dependencies first.
  popd
  exit /b 1
)

call ".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 (
  echo Failed to install or verify PyInstaller.
  popd
  exit /b 1
)

set "ARIA2C_PATH="
for /f "delims=" %%I in ('where aria2c 2^>nul') do (
  set "ARIA2C_PATH=%%I"
  goto :found_aria2c
)

:found_aria2c
if defined ARIA2C_PATH (
  echo Bundling aria2c from: %ARIA2C_PATH%
  set "BUNDLE_ARGS=--add-binary=%ARIA2C_PATH%;bin"
) else (
  echo aria2c not found on PATH. Packaged build will fall back to the built-in downloader.
  set "BUNDLE_ARGS="
)

call ".venv\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --clean ^
  --name ViDieL ^
  --windowed ^
  --paths src ^
  %BUNDLE_ARGS% ^
  src\vidiel\__main__.py

if errorlevel 1 (
  echo Build failed.
  popd
  exit /b 1
)

echo Build complete: dist\ViDieL
echo Note: ffmpeg is still expected as a system dependency on Windows.
echo Note: packaged builds do not self-update bundled yt-dlp yet.

popd
endlocal
