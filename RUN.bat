@echo off
setlocal enabledelayedexpansion
title SCP-079 // CONTAINMENT TERMINAL
cd /d "%~dp0"

REM Find the first Python that can actually import pygame, rather than
REM hardcoding one version - a friend's machine may have any of these.
set "PYCMD="
for %%C in ("py -3.13" "py -3.12" "py -3.11" "py -3.10" "py -3" "python") do (
    if not defined PYCMD (
        %%~C -c "import pygame" >nul 2>&1
        if not errorlevel 1 set "PYCMD=%%~C"
    )
)

if not defined PYCMD (
    echo.
    echo   Python with pygame was not found on this machine.
    echo.
    echo   Run Setup.bat first - it checks for everything the terminal
    echo   needs and offers to install whatever is missing.
    echo.
    pause
    exit /b 1
)

!PYCMD! "%~dp0Scp-079 Required Code\main.py" %*
set "RC=!errorlevel!"

if not "!RC!"=="0" (
    echo.
    echo   The terminal exited with an error ^(code !RC!^).
    echo.
    pause
)
exit /b !RC!
