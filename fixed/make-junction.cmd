@echo off
rem ===========================================================================
rem make-junction.cmd -- point Steam Cloud's save folder at the one the game uses.
rem
rem Steam Auto-Cloud for this game syncs
rem     <root>\CSE-1.0-pc\game\saves        (the OLD 1.0 install)
rem which the current build never reads or writes. Ren'Py does keep
rem     <root>\CSE-2.1.0-pc\game\saves
rem up to date by itself. Linking the first at the second means Steam always
rem sees current saves, and anything Steam downloads lands where the game
rem already looks.
rem
rem Both folders are inside the game install, so no Wine prefix is involved.
rem
rem Run from the game root (the folder holding CSE-1.0-pc and CSE-2.1.0-pc):
rem     make-junction.cmd                 create the link
rem     make-junction.cmd --dry-run       show what would happen
rem     make-junction.cmd --undo          put a real folder back
rem     make-junction.cmd "D:\path\to\CSE-1.0-pc"
rem
rem Wine note: a junction is an NTFS reparse point, and the filesystem under a
rem Wine prefix usually has none. This tries /J first, then /D, then checks that
rem the link REALLY works by writing a file through it -- because under Wine a
rem command can succeed and still not produce a link the Linux side follows.
rem If both fail, make the link from Linux instead:
rem     ln -s ../../CSE-2.1.0-pc/game/saves <root>/CSE-1.0-pc/game/saves
rem ===========================================================================

setlocal

set "DRY=0"
set "UNDO=0"
set "ROOT="

:parseargs
if "%~1"=="" goto argsdone
if /i "%~1"=="--dry-run" (
    set "DRY=1"
    shift
    goto parseargs
)
if /i "%~1"=="--undo" (
    set "UNDO=1"
    shift
    goto parseargs
)
if /i "%~1"=="-h" goto usage
if /i "%~1"=="--help" goto usage
if /i "%~1"=="/?" goto usage
set "ROOT=%~1"
shift
goto parseargs
:argsdone

rem ---------------------------------------------------------------- find root
if not "%ROOT%"=="" goto rootset
if exist "%CD%\CSE-2.1.0-pc\" (
    set "ROOT=%CD%"
    goto rootset
)
if exist "%~dp0..\CSE-2.1.0-pc\" (
    set "ROOT=%~dp0.."
    goto rootset
)
echo ERROR: could not find the game install.
echo        Run this from the folder holding CSE-1.0-pc and CSE-2.1.0-pc,
echo        or pass it: make-junction.cmd "D:\...\steamapps\common\CSE-1.0-pc"
exit /b 1
:rootset

rem normalise (strips any trailing \ and resolves ..)
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "OLD=%ROOT%\CSE-1.0-pc\game\saves"
set "NEW=%ROOT%\CSE-2.1.0-pc\game\saves"
set "OLDPARENT=%ROOT%\CSE-1.0-pc\game"

echo.
echo == Install ==
echo   %ROOT%

if not exist "%ROOT%\CSE-2.1.0-pc\" (
    echo ERROR: no CSE-2.1.0-pc inside that folder -- is it the right one?
    exit /b 1
)

if "%UNDO%"=="1" goto doundo

rem --------------------------------------------------- already linked, or not?
if not exist "%OLD%\" goto notlinked
echo probe> "%OLD%\_linkprobe.tmp" 2>nul
if not exist "%NEW%\_linkprobe.tmp" goto notlinked
del "%OLD%\_linkprobe.tmp" >nul 2>nul
echo.
echo == Nothing to do ==
echo   %OLD%
echo   already resolves to the 2.1.0 save folder.
exit /b 0
:notlinked
if exist "%OLD%\_linkprobe.tmp" del "%OLD%\_linkprobe.tmp" >nul 2>nul

rem the game creates this on first run; make it so a fresh install can be linked
if exist "%NEW%\" goto targetok
echo   target does not exist yet, creating it
if "%DRY%"=="0" mkdir "%NEW%"
:targetok

rem -------------------------------------------------------------------- backup
echo.
echo == Backup ==
if not exist "%OLD%\" (
    echo   %OLD% does not exist yet, nothing to back up
    goto backupdone
)

set "BAK=%ROOT%\_save_backup_prelink"
if not exist "%BAK%" goto bakok
set "BAK=%ROOT%\_save_backup_prelink2"
if not exist "%BAK%" goto bakok
set "BAK=%ROOT%\_save_backup_prelink3"
if not exist "%BAK%" goto bakok
echo ERROR: _save_backup_prelink, 2 and 3 all exist. Move or delete one.
exit /b 1
:bakok

if "%DRY%"=="1" (
    echo   would copy "%OLD%" -^> "%BAK%"
    goto backupdone
)
mkdir "%BAK%\CSE-1.0-pc-game-saves" 2>nul
copy /y "%OLD%\*" "%BAK%\CSE-1.0-pc-game-saves\" >nul 2>nul
echo Backup of the Steam Cloud save folder, taken before linking it.> "%BAK%\WHERE.txt"
echo.>> "%BAK%\WHERE.txt"
echo CSE-1.0-pc-game-saves>> "%BAK%\WHERE.txt"
echo     came from: %OLD%>> "%BAK%\WHERE.txt"
echo   copied to %BAK%
:backupdone

rem ---------------------------------------------------------------------- link
echo.
echo == Link ==
if "%DRY%"=="0" goto dolink
echo   would replace %OLD%
echo   with a link to %NEW%
echo.
echo   dry run, nothing written
exit /b 0

:dolink
if exist "%OLD%\" rmdir /s /q "%OLD%"
if exist "%OLD%" del /q "%OLD%" >nul 2>nul
if not exist "%OLDPARENT%\" mkdir "%OLDPARENT%"

mklink /J "%OLD%" "%NEW%" >nul 2>nul
if not errorlevel 1 goto linkmade
echo   junction (/J) not supported here, trying a directory symlink (/D)
mklink /D "%OLD%" "%NEW%" >nul 2>nul
if not errorlevel 1 goto linkmade

echo.
echo ERROR: neither "mklink /J" nor "mklink /D" worked under this Wine build.
echo        Make the link from Linux instead, then re-run this to verify:
echo.
echo          rm -rf "<root>/CSE-1.0-pc/game/saves"
echo          ln -s ../../CSE-2.1.0-pc/game/saves "<root>/CSE-1.0-pc/game/saves"
echo.
echo        Your saves are safe in %BAK%
exit /b 1

:linkmade
echo   %OLD%
echo     -^> %NEW%

rem -------------------------------------------------------------------- verify
echo.
echo == Verify ==
if not exist "%OLD%\" (
    echo ERROR: the link does not resolve to a directory.
    echo        Restore from %BAK% and make the link from Linux instead.
    exit /b 1
)

echo probe> "%OLD%\_linkprobe.tmp" 2>nul
if not exist "%NEW%\_linkprobe.tmp" (
    del "%OLD%\_linkprobe.tmp" >nul 2>nul
    echo ERROR: writing through the link did NOT appear in the target,
    echo        so this is a copy, not a link. Restore from %BAK%
    echo        and make the link from Linux instead.
    exit /b 1
)
del "%NEW%\_linkprobe.tmp" >nul 2>nul
if exist "%OLD%\_linkprobe.tmp" (
    echo ERROR: deleting through the target did not take effect.
    exit /b 1
)
echo   write through the link appears in the target: yes
echo   delete through the target clears it too:      yes

echo.
echo == Done ==
echo   Steam now syncs the folder the game actually uses.
echo   Launch and quit through Steam, then confirm remotecache.vdf updates:
echo     ~/.steam/steam/userdata/^<accountid^>/4309030/remotecache.vdf
exit /b 0

rem ---------------------------------------------------------------------- undo
:doundo
echo.
echo == Undo ==
if not exist "%OLD%" (
    echo   %OLD% does not exist; nothing to undo
    exit /b 0
)
echo probe> "%OLD%\_linkprobe.tmp" 2>nul
if not exist "%NEW%\_linkprobe.tmp" (
    del "%OLD%\_linkprobe.tmp" >nul 2>nul
    echo   %OLD% is a real folder, not a link; nothing to undo
    exit /b 0
)
del "%NEW%\_linkprobe.tmp" >nul 2>nul
if "%DRY%"=="1" (
    echo   would remove the link and put back a real folder with a copy of the saves
    exit /b 0
)
rmdir "%OLD%" 2>nul
if exist "%OLD%" del /q "%OLD%" >nul 2>nul
mkdir "%OLD%"
copy /y "%NEW%\*.save" "%OLD%\" >nul 2>nul
copy /y "%NEW%\persistent" "%OLD%\" >nul 2>nul
echo   replaced the link with a real folder holding a copy of the saves
exit /b 0

:usage
echo make-junction.cmd [install-dir] [--dry-run] [--undo]
echo.
echo Points Steam Cloud's save folder (CSE-1.0-pc\game\saves) at the folder the
echo game actually uses (CSE-2.1.0-pc\game\saves). Run it from the game root.
exit /b 0
