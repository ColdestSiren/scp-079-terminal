@echo off
REM Runs EVERY test suite in this folder. All of them must print FAIL 0.
REM
REM This used to name four files by hand and had gone stale: thirteen suites
REM had been added since and none of them ran. A list you have to remember to
REM update is a list that stops being true, so it enumerates the folder now.
cd /d "%~dp0.."
setlocal enabledelayedexpansion
set BROKEN=
for %%F in ("%~dp0test_*.py") do (
    echo.
    echo === %%~nxF ===
    py -3.13 "%%F"
    if errorlevel 1 set BROKEN=!BROKEN! %%~nxF
)
echo.
echo ===================================================
if defined BROKEN (
    echo FAILED:!BROKEN!
) else (
    echo ALL SUITES PASSED.
)
echo ===================================================
pause
