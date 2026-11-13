@echo off
REM ============================================================
REM  CodeAgent - reproducible Windows build (64-bit, one-file)
REM  Requires: Python 3.10+ on PATH (build machine only; the
REM  resulting exe embeds the runtime and needs no Python).
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/4] Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
if errorlevel 1 goto :fail

echo [2/4] Running test suite...
python -m pytest tests -q
if errorlevel 1 goto :fail

echo [3/4] Building CodeAgent.exe (PyInstaller, windowed, one-file)...
python -m PyInstaller CodeAgent.spec --noconfirm
if errorlevel 1 goto :fail

echo [4/4] Done.
echo Executable: %cd%\dist\CodeAgent.exe
endlocal
exit /b 0

:fail
echo BUILD FAILED. See output above.
endlocal
exit /b 1
