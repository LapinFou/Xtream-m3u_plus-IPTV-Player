#!/bin/bash

set -e

# Use Python 3 consistently for dependency checks and the PyInstaller build.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it and try again."
  exit 1
fi

PYTHON_BIN=python3
MAIN_SCRIPT="IPTV M3U_Plus PLAYER by MY-1.py"
BUILD_PATH="build"
DIST_PATH="dist"

# PyInstaller and every application dependency must belong to the interpreter
# used for packaging. PyInstaller can otherwise finish with a broken bundle.
if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller not found. Please install it with '$PYTHON_BIN -m pip install pyinstaller'"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" >/dev/null 2>&1; then
  echo "Installing missing application dependencies..."
  if ! "$PYTHON_BIN" -m pip install -r requirements.txt; then
    echo "ERROR: Application dependencies could not be installed."
    exit 1
  fi
fi

if ! "$PYTHON_BIN" -c "import PyQt5, requests, lxml, dateutil, vlc" >/dev/null 2>&1; then
  echo "ERROR: Required Python modules are still unavailable. Build cancelled."
  exit 1
fi

# python-vlc is only a binding. The VLC application supplies libVLC at runtime.
if [ ! -d "/Applications/VLC.app" ]; then
  echo "WARNING: VLC was not found in /Applications."
  echo "Install the latest VLC from https://www.videolan.org/vlc/ before using the internal player."
fi

# A macOS bundle needs an ICNS icon. Build without a custom icon when none exists.
ICON_ARGS=()
if [ -f "Images/TV_icon.icns" ]; then
  ICON_ARGS=(--icon "Images/TV_icon.icns")
fi

# Remove outputs from an earlier build only after dependency checks succeed.
if [ -d "$BUILD_PATH" ]; then
  echo "Removing old build folder: $BUILD_PATH"
  rm -rf "$BUILD_PATH"
fi

if [ -d "$DIST_PATH" ]; then
  echo "Removing old dist folder: $DIST_PATH"
  rm -rf "$DIST_PATH"
fi

# Keep the packaged files visible inside the macOS application bundle. This
# makes startup more direct and missing runtime dependencies easier to diagnose.
"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --onedir \
  --windowed \
  --noconfirm \
  --hidden-import vlc \
  "${ICON_ARGS[@]}" \
  --name "IPTV_Player" \
  --distpath "$DIST_PATH" \
  --workpath "$BUILD_PATH" \
  --add-data "Images/TV_icon.ico:Images" \
  --add-data "Images/404_not_found.png:Images" \
  --add-data "Images/no_image.jpg:Images" \
  --add-data "Images/loading-icon.png:Images" \
  --add-data "Images/home_tab_icon.ico:Images" \
  --add-data "Images/tv_tab_icon.ico:Images" \
  --add-data "Images/movies_tab_icon.ico:Images" \
  --add-data "Images/series_tab_icon.ico:Images" \
  --add-data "Images/favorite_tab_icon.ico:Images" \
  --add-data "Images/favorite_tab_icon_colour.ico:Images" \
  --add-data "Images/info_tab_icon.ico:Images" \
  --add-data "Images/settings_tab_icon.ico:Images" \
  --add-data "Images/search_bar_icon.ico:Images" \
  --add-data "Images/sorting_icon.ico:Images" \
  --add-data "Images/clear_button_icon.ico:Images" \
  --add-data "Images/go_back_icon.ico:Images" \
  --add-data "Images/account_manager_icon.ico:Images" \
  --add-data "Images/film_camera_icon.ico:Images" \
  --add-data "Images/primary_full-TMDB.svg:Images" \
  --add-data "Images/yt_icon_rgb.png:Images" \
  --add-data "Images/unknown_status.png:Images" \
  --add-data "Images/online_status.png:Images" \
  --add-data "Images/maybe_status.png:Images" \
  --add-data "Images/offline_status.png:Images" \
  --add-data "Threadpools.py:." \
  --add-data "CustomPyQtWidgets.py:." \
  --add-data "AccountManager.py:." \
  "$MAIN_SCRIPT"

echo
echo "Build completed: $DIST_PATH/IPTV_Player.app"
echo "Launch with: open '$DIST_PATH/IPTV_Player.app'"
echo "If Finder shows no error, diagnose with:"
echo "'$DIST_PATH/IPTV_Player.app/Contents/MacOS/IPTV_Player'"
