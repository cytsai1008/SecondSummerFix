@echo off
rem CSE save fixer launcher.
rem Prefers uv (pulls in ecdsa automatically); falls back to plain python.
setlocal
set "SCRIPT=%~dp0savefix.py"

where uv >nul 2>&1
if %errorlevel%==0 (
    uv run --quiet --with ecdsa python "%SCRIPT%" %*
    goto :done
)

where python >nul 2>&1
if %errorlevel%==0 (
    python "%SCRIPT%" %*
    goto :done
)

echo Could not find uv or python on PATH.
echo Install either one, then run this again.
exit /b 1

:done
set "RV=%errorlevel%"
rem Pause only on a bare double-click, so the window stays readable.
if not "%~1"=="" goto :eof
if defined SAVEFIX_NOPAUSE goto :eof
echo %CMDCMDLINE% | find /i "/c" >nul && pause
exit /b %RV%
