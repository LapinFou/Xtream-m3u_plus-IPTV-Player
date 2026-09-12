@echo off
REM Set the path to PyInstaller executable (if pyinstaller is in PATH, just use "pyinstaller")
SET PYINSTALLER=python -m PyInstaller

cls
echo ===============================
echo Set PyInstaller command:
echo.
echo 1. python -m PyInstaller
echo 2. python -m pyinstaller
echo 3. PyInstaller
echo 4. pyinstaller
echo ===============================
set /p py_choice=Enter your choice (1, 2, 3 or 4): 

IF "%py_choice%"=="1" SET PYINSTALLER=python -m PyInstaller
IF "%py_choice%"=="2" SET PYINSTALLER=python -m pyinstaller
IF "%py_choice%"=="3" SET PYINSTALLER=PyInstaller
IF "%py_choice%"=="4" SET PYINSTALLER=pyinstaller

REM Show version
echo.
echo PyInstaller version: 
%PYINSTALLER% --version

REM The embedded player imports python-vlc lazily, so verify the binding explicitly.
REM Install it only when missing to keep normal rebuilds fast and offline-friendly.
python -c "import vlc" >nul 2>&1
IF ERRORLEVEL 1 (
  echo.
  echo python-vlc is missing. Installing the required VLC Python binding...
  python -m pip install "python-vlc>=3.0.20000"
  IF ERRORLEVEL 1 (
    echo.
    echo ERROR: python-vlc could not be installed. The build has been cancelled.
    echo Check your Internet connection and Python installation, then try again.
    pause
    exit /b 1
  )
)

REM Confirm that the module is importable before PyInstaller deletes older builds.
python -c "import vlc" >nul 2>&1
IF ERRORLEVEL 1 (
  echo.
  echo ERROR: python-vlc is still unavailable. The build has been cancelled.
  pause
  exit /b 1
)

echo python-vlc is available.
pause

REM Main Python script to package
SET MAIN_SCRIPT="IPTV M3U_Plus PLAYER by MY-1.py"

REM Set build and dist folders separately
SET BUILD_PATH=build
SET DIST_PATH=dist

REM Give options what to create
cls
echo ===============================
echo What would you like to do?
echo.
echo 1. Create Executable without console
echo 2. Create Executable with console
echo 3. Create both Executables
echo ===============================
set /p exec_choice=Enter your choice (1, 2, or 3): 

REM Clean previous build folder
IF EXIST %BUILD_PATH% (
  echo Deleting existing build directory: %BUILD_PATH%
  rmdir /s /q %BUILD_PATH%
)

REM Clean previous dist folder
IF EXIST %DIST_PATH% (
  echo Deleting existing dist directory: %DIST_PATH%
  rmdir /s /q %DIST_PATH%
)

IF "%exec_choice%"=="2" GOTO option2

REM python-vlc is imported lazily, so PyInstaller cannot discover it automatically.
REM Run PyInstaller directly with all necessary options and added data files
%PYINSTALLER% ^
  --onefile ^
  --noconsole ^
  --noconfirm ^
  --hidden-import vlc ^
  --icon "Images/TV_icon.ico" ^
  --name "IPTV Player" ^
  --workpath %BUILD_PATH% ^
  --distpath %DIST_PATH% ^
  --add-data "Images/TV_icon.ico;Images" ^
  --add-data "Images/404_not_found.png;Images" ^
  --add-data "Images/no_image.jpg;Images" ^
  --add-data "Images/loading-icon.png;Images" ^
  --add-data "Images/home_tab_icon.ico;Images" ^
  --add-data "Images/tv_tab_icon.ico;Images" ^
  --add-data "Images/movies_tab_icon.ico;Images" ^
  --add-data "Images/series_tab_icon.ico;Images" ^
  --add-data "Images/favorite_tab_icon.ico;Images" ^
  --add-data "Images/favorite_tab_icon_colour.ico;Images" ^
  --add-data "Images/info_tab_icon.ico;Images" ^
  --add-data "Images/settings_tab_icon.ico;Images" ^
  --add-data "Images/search_bar_icon.ico;Images" ^
  --add-data "Images/sorting_icon.ico;Images" ^
  --add-data "Images/clear_button_icon.ico;Images" ^
  --add-data "Images/go_back_icon.ico;Images" ^
  --add-data "Images/account_manager_icon.ico;Images" ^
  --add-data "Images/film_camera_icon.ico;Images" ^
  --add-data "Images/primary_full-TMDB.svg;Images" ^
  --add-data "Images/yt_icon_rgb.png;Images" ^
  --add-data "Images/unknown_status.png;Images" ^
  --add-data "Images/online_status.png;Images" ^
  --add-data "Images/maybe_status.png;Images" ^
  --add-data "Images/offline_status.png;Images" ^
  --add-data "Threadpools.py;." ^
  --add-data "CustomPyQtWidgets.py;." ^
  --add-data "AccountManager.py;." ^
  %MAIN_SCRIPT%

IF "%exec_choice%"=="1" GOTO end

:option2
REM Create executable with debug console
REM Keep the lazy python-vlc import available in the diagnostic build too.
%PYINSTALLER% ^
  --onefile ^
  --noconfirm ^
  --hidden-import vlc ^
  --icon "Images/TV_icon.ico" ^
  --name "IPTV Player with debug console" ^
  --workpath %BUILD_PATH% ^
  --distpath %DIST_PATH% ^
  --add-data "Images/TV_icon.ico;Images" ^
  --add-data "Images/404_not_found.png;Images" ^
  --add-data "Images/no_image.jpg;Images" ^
  --add-data "Images/loading-icon.png;Images" ^
  --add-data "Images/home_tab_icon.ico;Images" ^
  --add-data "Images/tv_tab_icon.ico;Images" ^
  --add-data "Images/movies_tab_icon.ico;Images" ^
  --add-data "Images/series_tab_icon.ico;Images" ^
  --add-data "Images/favorite_tab_icon.ico;Images" ^
  --add-data "Images/favorite_tab_icon_colour.ico;Images" ^
  --add-data "Images/info_tab_icon.ico;Images" ^
  --add-data "Images/settings_tab_icon.ico;Images" ^
  --add-data "Images/search_bar_icon.ico;Images" ^
  --add-data "Images/sorting_icon.ico;Images" ^
  --add-data "Images/clear_button_icon.ico;Images" ^
  --add-data "Images/go_back_icon.ico;Images" ^
  --add-data "Images/account_manager_icon.ico;Images" ^
  --add-data "Images/film_camera_icon.ico;Images" ^
  --add-data "Images/primary_full-TMDB.svg;Images" ^
  --add-data "Images/yt_icon_rgb.png;Images" ^
  --add-data "Images/unknown_status.png;Images" ^
  --add-data "Images/online_status.png;Images" ^
  --add-data "Images/maybe_status.png;Images" ^
  --add-data "Images/offline_status.png;Images" ^
  --add-data "Threadpools.py;." ^
  --add-data "CustomPyQtWidgets.py;." ^
  --add-data "AccountManager.py;." ^
  %MAIN_SCRIPT%

:end
echo.
echo Build complete. Executable saved in %DIST_PATH%.
pause
