@echo off
setlocal EnableExtensions EnableDelayedExpansion
title SCP-079 // CONTAINMENT TERMINAL
cd /d "%~dp0"

set "MAIN=%~dp0Scp-079 Required Code\main.py"
set "PYEXE="
set "PYARGS="
set "FOUND_PYTHON="
set "LAST_PYTHON="
set "PYGAME_MISSING="

REM ============================================================
REM Make sure the main program exists.
REM ============================================================

if not exist "%MAIN%" (
    echo.
    echo   ERROR: The terminal's main.py file was not found.
    echo.
    echo   Expected location:
    echo   "%MAIN%"
    echo.
    pause
    exit /b 1
)

REM ============================================================
REM Check Python installations in order.
REM If one fails, the next one is checked automatically.
REM ============================================================

REM 1. Project virtual environment
call :TryPython "%~dp0.venv\Scripts\python.exe" ""

REM 2. Normal Windows Python launcher
call :TryPython "py" "-3.13"
call :TryPython "py" "-3.12"
call :TryPython "py" "-3.11"
call :TryPython "py" "-3.10"
call :TryPython "py" "-3"

REM 3. Normal python command
call :TryPython "python" ""

REM 4-6. Normal per-user and system-wide Python 3.10+ folders
for %%V in (313 312 311 310) do (
    call :TryPython "%LocalAppData%\Programs\Python\Python%%V\python.exe" ""
    call :TryPython "%ProgramFiles%\Python%%V\python.exe" ""
    if not "!ProgramFiles(x86)!"=="" (
        call :TryPython "!ProgramFiles(x86)!\Python%%V\python.exe" ""
    )
)

REM 7. Previously saved moved-Python location
if not defined PYEXE if exist "%~dp0python-path.txt" (
    set /p "CUSTOM_PYTHON="<"%~dp0python-path.txt"
    set "CUSTOM_PYTHON=!CUSTOM_PYTHON:"=!"

    if defined CUSTOM_PYTHON (
        call :TryPython "!CUSTOM_PYTHON!" ""
    )
)

REM ============================================================
REM Ask for the moved location if automatic checks failed.
REM ============================================================

if not defined PYEXE (
    echo.

    if defined PYGAME_MISSING (
        echo   Python 3.10 or newer was found, but Pygame is not installed.
    ) else (
        echo   Python 3.10 or newer was not found in its normal locations.
    )

    echo.
    echo   If Python 3.13 was moved, paste the full location of
    echo   its python.exe below.
    echo.
    echo   Example:
    echo   E:\Programs\Python313\python.exe
    echo.
    echo   Leave it blank to cancel.
    echo.

    set /p "CUSTOM_PYTHON=Python path: "
    set "CUSTOM_PYTHON=!CUSTOM_PYTHON:"=!"

    if defined CUSTOM_PYTHON (
        call :TryPython "!CUSTOM_PYTHON!" ""

        if defined PYEXE (
            >"%~dp0python-path.txt" echo(!CUSTOM_PYTHON!
            echo.
            echo   Python location saved successfully.
        ) else if /i "!LAST_PYTHON!"=="!CUSTOM_PYTHON!" (
            REM Save a valid interpreter even when pygame is missing, so
            REM Setup.bat knows exactly where to install the libraries.
            >"%~dp0python-path.txt" echo(!CUSTOM_PYTHON!
            echo.
            echo   Python location saved. Setup.bat can install Pygame there.
        )
    )
)

REM ============================================================
REM Stop if no suitable Python was found.
REM ============================================================

if not defined PYEXE (
    echo.

    if defined PYGAME_MISSING (
        echo   Python was found, but it could not import Pygame.
        echo.
        echo   Run Setup.bat to install Pygame into that Python installation.
    ) else (
        echo   A working Python 3.10 or newer installation was not found.
        echo.
        echo   Run Setup.bat to install or locate Python 3.13.
    )

    echo.
    pause
    exit /b 1
)

REM ============================================================
REM Launch SCP-079.
REM ============================================================

"%PYEXE%" %PYARGS% "%MAIN%" %*
set "RC=!errorlevel!"

if not "!RC!"=="0" (
    echo.
    echo   The terminal exited with an error ^(code !RC!^).
    echo.
    pause
)

exit /b !RC!


REM ============================================================
REM Test one Python option.
REM
REM It must:
REM   1. Exist or be available through PATH
REM   2. Be Python 3.10 or newer
REM   3. Be able to import Pygame
REM ============================================================

:TryPython
if defined PYEXE exit /b 0

set "TEST_EXE=%~1"
set "TEST_ARGS=%~2"

if not defined TEST_EXE exit /b 0

REM Commands such as py and python must be available through PATH.
if /i "!TEST_EXE!"=="py" (
    where.exe py >nul 2>&1
    if errorlevel 1 exit /b 0
) else if /i "!TEST_EXE!"=="python" (
    where.exe python >nul 2>&1
    if errorlevel 1 exit /b 0
) else (
    REM Full executable paths must exist.
    if not exist "!TEST_EXE!" exit /b 0
)

REM Check the same supported range Setup.bat and README advertise.
"!TEST_EXE!" !TEST_ARGS! -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1

if errorlevel 1 exit /b 0

set "FOUND_PYTHON=1"
set "LAST_PYTHON=!TEST_EXE!"

REM Check whether Pygame is installed.
"!TEST_EXE!" !TEST_ARGS! -c "import pygame" >nul 2>&1

if errorlevel 1 (
    set "PYGAME_MISSING=1"
    exit /b 0
)

set "PYEXE=!TEST_EXE!"
set "PYARGS=!TEST_ARGS!"
exit /b 0
