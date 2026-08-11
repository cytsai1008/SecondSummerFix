# Distorted audio under CrossOver / Wine

**English** · [简体中文](README.zh-CN.md)

## Symptom

Running the Windows build through Wine (CrossOver bottle on macOS): volume is
very low, raising the system volume makes it audible but crackly, and some
sounds play at the wrong pitch.

There is no native Mac or Linux build on Steam, so Wine is the only route short
of running the game under the Ren'Py SDK.

## Cause

Wine has to imitate the Windows audio stack on top of CoreAudio. Its modern path
(**WASAPI**) does the sample-rate conversion badly — that is the low volume, the
crackle, and the pitch shift. The fault is inside Wine's conversion, not in the
Mac audio device.

## Fix

Ren'Py reads `environment.txt` from the folder next to the game's executable at
startup, before the engine initialises. Put this there:

```
SDL_AUDIODRIVER = "winmm"
RENPY_SOUND_BUFSIZE = "8192"
```

- `winmm` — the old, simple Windows audio path. Wine imitates it far better than
  WASAPI.
- `RENPY_SOUND_BUFSIZE` — undocumented engine knob, found in the engine source;
  8192 is 4× the default. Small buffers running dry mid-play are the classic
  cause of crackle.

Copy the `environment.txt` beside this file into each install folder, next to
`A_Second_Chance_to_Relive_Summer.exe`:

```
CSE-2.1.0-pc/environment.txt
CSE-1.0-pc/environment.txt
```

Then just quit and restart the game — the file is read by the game itself, so no
bottle restart is needed. Steam file verification and game updates leave it alone.

Sanity check that the file is being read: set the driver to `dummy` and restart —
the game should go completely silent. Then set it back.

## What did not work

- Changing the output device or sample rate (44.1 / 48 / 96 kHz) in Audio MIDI
  Setup. The fault is in Wine, not the device.
- Setting audio options in the CrossOver bottle config. Those need a full
  **Quit Bottle** to take effect, so several tests silently never applied at all.
  `environment.txt` avoids that trap entirely — hence preferring it.

If `winmm` ever fails on another setup, the same file with `directsound` or
`dsound` is the next thing to try — one line to edit, one game restart per test.

## Running `savefix` from outside the bottle

`savefix.py` finds the live save folder through `%APPDATA%`, which does not exist
on macOS or Linux, so it exits with `no Ren'Py save folder found in %APPDATA%\RenPy`.
Point it at the bottle's Roaming folder and it works natively — no Wine involved:

```sh
cd "<bottle>/drive_c/Program Files (x86)/Steam/steamapps/common/CSE-1.0-pc"
APPDATA="<bottle>/drive_c/users/crossover/AppData/Roaming" \
  uv run --quiet --with ecdsa python tools/savefix.py
```

On a stock CrossOver install `<bottle>` is
`~/Library/Application Support/CrossOver/Bottles/Steam`. On Linux/Proton the user
folder is `users/steamuser` instead of `users/crossover`.

That is the read-only check; `fix` and `sync` take the same variable.

## Portable

This is not specific to this game. Drop the same `environment.txt` next to any
Windows Ren'Py game's `.exe` running under Wine or CrossOver.
