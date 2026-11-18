@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || exit /b 1

if not exist "main.py" (
    echo main.py must be in the same folder as build.bat.
    goto :error
)

if not exist ".ocp-build\Scripts\python.exe" (
    py -3 -c "import sys; raise SystemExit(not sys.version_info >= (3, 10))" >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv ".ocp-build"
    ) else (
        python -c "import sys; raise SystemExit(not sys.version_info >= (3, 10))" >nul 2>&1
        if errorlevel 1 (
            echo Python 3.10 or newer for Windows is required to build OCP.
            goto :error
        )
        python -m venv ".ocp-build"
    )
    if errorlevel 1 goto :error
)

set "OCP_PYTHON=.ocp-build\Scripts\python.exe"
set "PYINSTALLER_CONFIG_DIR=%CD%\.ocp-build\cache"
"%OCP_PYTHON%" -m pip install --disable-pip-version-check "PyQt6>=6.7,<7" "requests>=2.32,<3" "PyInstaller>=6.11,<7"
if errorlevel 1 goto :error

"%OCP_PYTHON%" "main.py" --write-icon ".ocp-build\ocp.ico"
if errorlevel 1 goto :error

"%OCP_PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --icon "%CD%\.ocp-build\ocp.ico" --name "OCP" --distpath "dist" --workpath ".ocp-build\work" --specpath ".ocp-build" "%CD%\main.py"
if errorlevel 1 goto :error
if not exist "dist\OCP.exe" goto :error

echo.
echo Built: "%CD%\dist\OCP.exe"
popd
pause
exit /b 0

:error
echo.
echo OCP build failed. See the error above.
popd
pause
exit /b 1
