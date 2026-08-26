@echo off
setlocal enabledelayedexpansion
title SCP-079 // SETUP
cd /d "%~dp0"

REM  Run with:  Setup.bat check    to only report status, install nothing.
set "CHECKONLY="
if /i "%~1"=="check" set "CHECKONLY=1"

set "PYCMD="
set "PYBASE="
set "OLLAMA="
set "MODEL=llama3.2:3b"

echo.
echo  ============================================================
echo    SCP-079 CONTAINMENT TERMINAL  --  SETUP
echo  ============================================================
echo.

if defined CHECKONLY (
    echo  [CHECK ONLY] Reporting status. Nothing will be installed.
    echo.
) else (
    echo  This checks for everything the terminal needs and offers to
    echo  install whatever is missing. Nothing is installed unless you
    echo  type Y first.
    echo.
    echo  It needs three things:
    echo    1. Python 3.10 or newer, plus the pygame library
    echo    2. Ollama - runs the AI on your own machine, nothing is sent online
    echo    3. One language model to talk to ^(a few GB to download^)
    echo.
    echo  ------------------------------------------------------------
    echo   ABOUT YOUR ANTIVIRUS
    echo  ------------------------------------------------------------
    echo  Avast, Bitdefender and others may flag this file as suspicious,
    echo  and may block or silently delete it. That is expected and it is
    echo  not a sign that something is wrong.
    echo.
    echo  It happens because this script does the same things an installer
    echo  does: downloads files, unpacks them, and installs software. That
    echo  pattern looks identical to the real thing from the outside, so
    echo  heuristic scanners flag it on behaviour alone.
    echo.
    echo  This file is safe. It only installs what the game needs to run.
    echo  Do not take that on trust though - you can check it yourself:
    echo.
    echo    * This is a plain text file. Open it in Notepad and read it.
    echo      Every command is visible, there is nothing compiled or hidden.
    echo    * Everything is downloaded from official sources: python.org
    echo      and ollama.com through Windows' own winget, and the game
    echo      itself from the project's public GitHub page.
    echo    * Nothing downloaded is ever executed automatically.
    echo.
    echo  If you would still rather not, run it in a virtual machine, or
    echo  install Python, pygame, Pillow and Ollama yourself and skip this
    echo  entirely. The game does not need this script, it is a convenience.
    echo  ------------------------------------------------------------
    echo.
    pause
    echo.
)

REM ---------------------------------------------------------------- winget
where winget >nul 2>&1
if errorlevel 1 (
    set "WINGET="
    echo  [i] winget not found. Installers will open in your browser instead.
) else (
    set "WINGET=1"
)
echo.

REM ------------------------------------------------------------ game files
REM  This file is designed to survive being downloaded ON ITS OWN. Someone
REM  handed "Setup.bat" and nothing else should end up with a working game,
REM  not an error, so if the code folder is not next to it this fetches the
REM  whole thing from GitHub first.
echo  ------------------------------------------------------------
echo   STEP 1 OF 6  --  GAME FILES
echo  ------------------------------------------------------------

set "CODEDIR=%~dp0Scp-079 Required Code"
if exist "!CODEDIR!\main.py" (
    echo  [OK] Game files are here.
    goto :files_done
)

echo  [X] The game files are not in this folder.
echo      Only Setup.bat is here, so there is nothing to run yet.
if defined CHECKONLY (
    echo      Run Setup.bat normally ^(without "check"^) to download them.
    goto :files_done
)

set "REPOZIP=https://github.com/ColdestSiren/scp-079-terminal/archive/refs/heads/main.zip"
set "TARGET=%~dp0Scp-079-terminal"

echo.
echo      They can be downloaded from the project's own GitHub page:
echo        %REPOZIP%
echo      About 8 MB. It will be unpacked into:
echo        !TARGET!
echo.
echo      Nothing downloaded is run automatically. The files are put in
echo      place and setup carries on from there.
echo.
set /p "ANS=      Download the game now? (Y/N): "
if /i not "!ANS!"=="Y" (
    echo.
    echo      Skipped. Without the game files nothing else here applies -
    echo      download the project from GitHub and run Setup.bat from
    echo      inside that folder instead.
    goto :done_early
)

if exist "!TARGET!\Scp-079 Required Code\main.py" (
    echo.
    echo  [*] There is already an install at !TARGET!
    echo      Not overwriting it. Run Setup.bat from inside that folder.
    goto :done_early
)

REM curl.exe and tar.exe both ship with Windows 10 and 11, so this needs
REM nothing installed first - which is the whole point of a bootstrap step.
where curl.exe >nul 2>&1
if errorlevel 1 (
    echo  [X] curl is not available, so this cannot download for you.
    echo      Get the project from GitHub by hand instead.
    goto :done_early
)

set "TMPZIP=%TEMP%\scp079-download.zip"
set "TMPDIR=%TEMP%\scp079-unpack"
echo.
echo      Downloading...
curl.exe -L --fail --silent --show-error -o "!TMPZIP!" "%REPOZIP%"
if errorlevel 1 (
    echo  [X] The download failed. Check your connection and try again.
    goto :done_early
)
if not exist "!TMPZIP!" (
    echo  [X] The download produced no file.
    goto :done_early
)

REM A GitHub error page saved as .zip would be a few hundred bytes. The real
REM archive is megabytes, so this catches "downloaded something, but not the
REM game" before it gets unpacked over anything.
for %%S in ("!TMPZIP!") do set "ZIPSIZE=%%~zS"
if !ZIPSIZE! LSS 500000 (
    echo  [X] The download is too small to be the game ^(!ZIPSIZE! bytes^).
    echo      The repository may have moved. Nothing was installed.
    del "!TMPZIP!" >nul 2>&1
    goto :done_early
)

echo      Unpacking...
if exist "!TMPDIR!" rmdir /s /q "!TMPDIR!" >nul 2>&1
mkdir "!TMPDIR!" >nul 2>&1

REM  FULL PATH TO THE WINDOWS TAR, NOT WHATEVER "tar" RESOLVES TO.
REM  Git for Windows ships its own MSYS tar and puts it earlier on PATH, and
REM  that build reads "C:\..." as a REMOTE HOST in rcp syntax. On any machine
REM  with Git installed the unpack failed with:
REM        tar: Cannot connect to C: resolve failed
REM  which is not a message anyone would connect to a zip file.
set "SYSTAR=%SYSTEMROOT%\System32\tar.exe"
set "UNPACKED_OK="
if exist "!SYSTAR!" (
    "!SYSTAR!" -xf "!TMPZIP!" -C "!TMPDIR!"
    if not errorlevel 1 set "UNPACKED_OK=1"
)

REM  Fallback for a Windows old enough to have no bundled tar. PowerShell has
REM  shipped Expand-Archive since 5.0, so between the two this is covered.
if not defined UNPACKED_OK (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "try { Expand-Archive -LiteralPath '!TMPZIP!' -DestinationPath '!TMPDIR!' -Force; exit 0 } catch { exit 1 }"
    if not errorlevel 1 set "UNPACKED_OK=1"
)

if not defined UNPACKED_OK (
    echo  [X] Could not unpack the download. Nothing was installed.
    goto :cleanup_download
)

REM GitHub wraps everything in "<repo>-<branch>", so the real contents are one
REM level down and that wrapper has to be stepped through rather than kept.
set "UNPACKED="
for /d %%D in ("!TMPDIR!\*") do set "UNPACKED=%%~fD"
if not defined UNPACKED (
    echo  [X] The archive was empty. Nothing was installed.
    goto :cleanup_download
)

move "!UNPACKED!" "!TARGET!" >nul 2>&1
if not exist "!TARGET!\Scp-079 Required Code\main.py" (
    echo  [X] The files did not end up where expected. Nothing was installed.
    goto :cleanup_download
)

echo  [OK] Installed to !TARGET!
del "!TMPZIP!" >nul 2>&1
rmdir /s /q "!TMPDIR!" >nul 2>&1
echo.
echo      Carrying on with setup in the new folder...
echo.
REM Handing off rather than continuing here: every step below resolves paths
REM from where the running .bat sits, so the copy inside the game folder is
REM the one that can finish the job correctly.
call "!TARGET!\Setup.bat"
exit /b 0

:cleanup_download
del "!TMPZIP!" >nul 2>&1
rmdir /s /q "!TMPDIR!" >nul 2>&1
goto :done_early

:files_done
echo.

REM ---------------------------------------------------------------- python
echo  ------------------------------------------------------------
echo   STEP 2 OF 6  --  PYTHON
echo  ------------------------------------------------------------

call :find_python
if defined PYCMD (
    echo  [OK] Python with pygame found:  !PYCMD!
    call :check_extras
    goto :python_done
)

call :find_python_base
if defined PYBASE (
    echo  [*] Python found ^(!PYBASE!^) but its libraries are missing.
    if defined CHECKONLY goto :python_done
    echo.
    echo      Needs: pygame ^(the window and sound^)
    echo             Pillow ^(animated gifs, and showing 079 a picture^)
    echo.
    set /p "ANS=      Install them now? (Y/N): "
    if /i "!ANS!"=="Y" (
        echo.
        call :install_requirements "!PYBASE!"
        call :find_python
        if defined PYCMD (
            echo  [OK] Libraries installed.
        ) else (
            echo  [X] pygame still not importable. See the messages above.
        )
    )
    goto :python_done
)

echo  [X] No Python installation found.
if defined CHECKONLY goto :python_done
echo.
if defined WINGET (
    set /p "ANS=      Install Python 3.13 now? (Y/N): "
    if /i "!ANS!"=="Y" (
        echo.
        winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
        echo.
        echo  [i] Python was just installed, so this window does not know about
        echo      it yet. CLOSE THIS WINDOW and run Setup.bat again to finish.
        echo.
        pause
        exit /b 0
    )
) else (
    set /p "ANS=      Open the Python download page? (Y/N): "
    if /i "!ANS!"=="Y" start "" "https://www.python.org/downloads/"
    echo.
    echo  [i] Install it, tick "Add python.exe to PATH", then run Setup.bat again.
)

:python_done
echo.

REM ---------------------------------------------------------------- ollama
echo  ------------------------------------------------------------
echo   STEP 3 OF 6  --  OLLAMA
echo  ------------------------------------------------------------

call :find_ollama
if defined OLLAMA (
    echo  [OK] Ollama found:  !OLLAMA!
    goto :ollama_done
)

echo  [X] Ollama not found.
if defined CHECKONLY goto :ollama_done
echo.
if defined WINGET (
    set /p "ANS=      Install Ollama now? (Y/N): "
    if /i "!ANS!"=="Y" (
        echo.
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
        echo.
        call :find_ollama
        if not defined OLLAMA (
            echo  [i] Installed, but this window cannot see it yet.
            echo      CLOSE THIS WINDOW and run Setup.bat again to finish.
            echo.
            pause
            exit /b 0
        )
        echo  [OK] Ollama installed.
    )
) else (
    set /p "ANS=      Open the Ollama download page? (Y/N): "
    if /i "!ANS!"=="Y" start "" "https://ollama.com/download"
    echo.
    echo  [i] Install it, then run Setup.bat again.
)

:ollama_done
echo.

REM ---------------------------------------------------------------- model
echo  ------------------------------------------------------------
echo   STEP 4 OF 6  --  LANGUAGE MODEL
echo  ------------------------------------------------------------

if not defined OLLAMA (
    echo  [--] Skipped. Ollama has to be installed first.
    goto :model_done
)

"!OLLAMA!" list 2>nul | findstr /i /c:"%MODEL%" >nul
if not errorlevel 1 (
    echo  [OK] %MODEL% is installed.
    goto :model_done
)

echo  [X] No model installed yet.
if defined CHECKONLY goto :model_done
echo.
echo      Recommended: %MODEL% - about 2 GB, runs on most machines.
echo      You can add bigger ones later from inside the terminal.
echo.
set /p "ANS=      Download %MODEL% now? (Y/N): "
if /i "!ANS!"=="Y" (
    echo.
    "!OLLAMA!" pull %MODEL%
    echo.
)

:model_done
echo.

REM ------------------------------------------------------- install location
echo  ------------------------------------------------------------
echo   STEP 5 OF 6  --  WHERE THE GAME LIVES
echo  ------------------------------------------------------------

set "DESKTOP=%USERPROFILE%\Desktop"
set "HERE=%~dp0"
REM Strip the trailing backslash so the comparison below is not defeated by it.
if "!HERE:~-1!"=="\" set "HERE=!HERE:~0,-1!"
set "TARGET=!DESKTOP!\Scp-079-terminal"

REM Is this copy already sitting on the Desktop? Compared case-insensitively
REM because Windows paths are, and a case mismatch would offer to install a
REM second copy on top of the one you are already running.
set "ONDESKTOP="
echo !HERE! | findstr /i /c:"!DESKTOP!" >nul && set "ONDESKTOP=1"

if defined ONDESKTOP (
    echo  [OK] Already on your Desktop:
    echo       !HERE!
    goto :place_done
)

echo  [i] This copy is not on your Desktop. It runs perfectly well from
echo      here - this is only about having it somewhere easy to find.
echo       now:  !HERE!
if defined CHECKONLY goto :place_done

if exist "!TARGET!" (
    echo.
    echo  [*] There is already a folder at:
    echo       !TARGET!
    echo      Not touching it. Copying over an existing install could
    echo      overwrite someone's saves and 079's memory.
    goto :place_done
)

echo.
set /p "ANS=      Put a copy on the Desktop? (Y/N): "
if /i not "!ANS!"=="Y" goto :place_done
echo.
echo      Copying to !TARGET! ...
REM robocopy ships with Windows. /XD skips the player data and the throwaway
REM caches - a fresh install should start with a fresh 079, not a clone of
REM this one's memory of whoever has been playing here.
robocopy "!HERE!" "!TARGET!" /E /NFL /NDL /NJH /NJS /NP ^
    /XD memory logs "shared folder" backup __pycache__ _shots ".git" "Add later" >nul
if exist "!TARGET!\RUN.bat" (
    echo  [OK] Copied. Start it from the Desktop with RUN.bat
    echo       Your original copy here is untouched.
) else (
    echo  [X] The copy did not complete. Nothing was removed from here.
)

:place_done
echo.

REM ------------------------------------------------------ automatic updates
echo  ------------------------------------------------------------
echo   STEP 6 OF 6  --  AUTOMATIC UPDATE CHECKS
echo  ------------------------------------------------------------
echo.
echo  The terminal already checks for updates when you open it. This is
echo  about also checking when you log in to Windows, so you find out
echo  without having to open it first.
echo.
echo  It only ever CHECKS. It never downloads and never installs -
echo  installing stays a button you press inside the terminal.
echo.

if defined CHECKONLY (
    if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SCP-079 Update Check.vbs" (
        echo  [OK] Startup entry is installed.
    ) else (
        echo  [--] No startup entry.
    )
    goto :update_done
)
if not defined PYCMD (
    echo  [--] Skipped. Needs a working Python first.
    goto :update_done
)

echo    [1] Startup folder    runs at login. RECOMMENDED.
echo    [2] Task Scheduler    runs at login, as a scheduled task.
echo        ^(Some antivirus suites - Avast's Gaming Mode among them -
echo         switch scheduled tasks off wholesale. If yours does, this
echo         will silently never run and option 1 is the one to pick.^)
echo    [3] No thanks         the terminal still checks when you open it.
echo.
set /p "ANS=      Choose 1, 2 or 3: "

set "STARTUPDIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBSPATH=!STARTUPDIR!\SCP-079 Update Check.vbs"
set "CHECKER=%~dp0Scp-079 Required Code\updatecheck.py"

if "!ANS!"=="1" (
    REM A .vbs wrapper rather than a .bat: a .bat in Startup flashes a
    REM console window at every login, which is exactly the kind of thing
    REM that makes people uninstall software.
    > "!VBSPATH!" echo Set s = CreateObject^("WScript.Shell"^)
    >> "!VBSPATH!" echo s.Run "cmd /c """"!PYCMD!"" ""!CHECKER!"" --quiet""", 0, False
    if exist "!VBSPATH!" (
        echo.
        echo  [OK] Added to Startup. Remove it any time by deleting:
        echo       !VBSPATH!
    ) else (
        echo  [X] Could not write to the Startup folder.
    )
) else if "!ANS!"=="2" (
    schtasks /Create /TN "SCP-079 Update Check" /SC ONLOGON /F ^
        /TR "\"!PYCMD!\" \"!CHECKER!\" --quiet" >nul 2>&1
    if not errorlevel 1 (
        echo.
        echo  [OK] Scheduled task created. Remove it with:
        echo       schtasks /Delete /TN "SCP-079 Update Check" /F
        echo  [i] If your antivirus disables scheduled tasks, this will
        echo      never fire. Re-run Setup.bat and pick 1 instead.
    ) else (
        echo.
        echo  [X] Could not create the task ^(this usually needs admin^).
        echo      Re-run Setup.bat and pick 1 - it needs no privileges.
    )
) else (
    echo.
    echo  [--] Nothing added. The terminal still checks when you open it.
)

:update_done
echo.

REM ---------------------------------------------------------------- summary
echo  ============================================================
echo    SUMMARY
echo  ============================================================
call :find_python
call :find_ollama
set "READY=1"

if defined PYCMD (
    echo    Python + pygame ... OK
    REM Counts against READY. Without it the game runs but every animation
    REM silently does nothing, which looks like the feature was never built.
    !PYCMD! -c "import PIL" >nul 2>&1
    if not errorlevel 1 (
        echo    Pillow .......... OK
    ) else (
        echo    Pillow .......... MISSING ^(no animations, no images^)
        set "READY="
    )
) else (
    echo    Python + pygame ... MISSING
    echo    Pillow .......... UNKNOWN
    set "READY="
)
if defined OLLAMA (
    echo    Ollama .......... OK
) else (
    echo    Ollama .......... MISSING
    set "READY="
)

if defined OLLAMA (
    "!OLLAMA!" list 2>nul | findstr /i /c:"%MODEL%" >nul
    if not errorlevel 1 (
        echo    Model ........... OK
    ) else (
        echo    Model ........... MISSING
        set "READY="
    )
) else (
    echo    Model ........... UNKNOWN
    set "READY="
)

echo.
if defined READY (
    echo    Everything is ready. Start the terminal with RUN.bat
    echo.
    if not defined CHECKONLY (
        set /p "ANS=    Launch it now? (Y/N): "
        if /i "!ANS!"=="Y" (
            start "" "%~dp0RUN.bat"
            exit /b 0
        )
    )
) else (
    echo    Something is still missing. Run Setup.bat again to retry,
    echo    or install the missing piece yourself and re-run this.
)
echo.
pause
exit /b 0


:done_early
echo.
pause
exit /b 0

REM ================================================================ helpers

:install_requirements
REM Installs from requirements.txt so the list lives in ONE place. Falls back
REM to naming the packages inline if that file went missing.
set "REQ=%~dp0Scp-079 Required Code\requirements.txt"
%~1 -m pip install --upgrade pip
if exist "!REQ!" (
    echo      Installing from requirements.txt ...
    %~1 -m pip install -r "!REQ!"
) else (
    echo      requirements.txt not found - installing by name.
    %~1 -m pip install pygame Pillow
)
exit /b 0

:check_extras
REM Pillow has two jobs: decoding animated gifs, and reading, shrinking
REM and re-encoding a picture the player shows 079 (including one pasted
REM off the clipboard). Treated as REQUIRED: the game will still start
REM without it, but every animated easter egg silently does nothing, and
REM "the funny stuff quietly not happening" is a worse failure than a
REM missing library, because nobody can tell it is broken. Images at
REM least refuse in words rather than half-working.
!PYCMD! -c "import PIL" >nul 2>&1
if not errorlevel 1 (
    echo  [OK] Pillow found ^(animations play, images can be shown^)
    exit /b 0
)
echo  [X] Pillow is MISSING. Every animated easter egg will silently
echo      do nothing - no explosion, no fire screen, no future ones -
echo      and 079 cannot be shown a picture at all.
if defined CHECKONLY exit /b 0
echo.
set /p "ANS=      Install Pillow now? (Y/N): "
if /i "!ANS!"=="Y" (
    echo.
    !PYCMD! -m pip install Pillow
    !PYCMD! -c "import PIL" >nul 2>&1
    if not errorlevel 1 (
        echo  [OK] Pillow installed.
    ) else (
        echo  [X] Pillow still not importable. See the messages above.
    )
) else (
    echo.
    echo      Skipped. Run Setup.bat again when you want the animations.
)
exit /b 0

:find_python
REM Sets PYCMD to the first interpreter that can actually import pygame.
set "PYCMD="
for %%C in ("py -3.13" "py -3.12" "py -3.11" "py -3.10" "py -3" "python") do (
    if not defined PYCMD (
        %%~C -c "import pygame" >nul 2>&1
        if not errorlevel 1 set "PYCMD=%%~C"
    )
)
exit /b 0

:find_python_base
REM Sets PYBASE to any working Python, pygame or not.
set "PYBASE="
for %%C in ("py -3.13" "py -3.12" "py -3.11" "py -3.10" "py -3" "python") do (
    if not defined PYBASE (
        %%~C -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PYBASE=%%~C"
    )
)
exit /b 0

:find_ollama
set "OLLAMA="
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    exit /b 0
)
if exist "%PROGRAMFILES%\Ollama\ollama.exe" (
    set "OLLAMA=%PROGRAMFILES%\Ollama\ollama.exe"
    exit /b 0
)
for /f "delims=" %%O in ('where ollama 2^>nul') do (
    if not defined OLLAMA set "OLLAMA=%%O"
)
exit /b 0
