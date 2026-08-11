# Steam achievements never unlock

**English** · [简体中文](achievements.zh-CN.md)

## Symptom

You play through achievement points, nothing pops on Steam, and `log.txt` shows no error. The game itself thinks it worked — `game/saves/persistent` contains:

```
_achievements: new_1 … new_8
```

## Cause

The game code is fine. `game/scripts.rpa` → `archievement.rpyc` registers and grants correctly:

```python
achievement.register('new_1', steam='achievement_1')   # … up to new_11
achievement.grant('new_1')                             # from script_chapter_1/2/3
```

The Steam side is dead because the build ships **no `steam_api64.dll`**. `renpy/common/00steam.rpy:1002`:

```python
dll_path = os.path.join(os.path.dirname(sys.executable), dll_name)  # steam_api64.dll
has_steam = os.path.exists(dll_path)
if not has_steam:
    return            # silent — no error, no log line
```

`lib/py3-windows-x86_64/` holds only `d3dcompiler_47.dll`, `libEGL.dll`, `libGLESv2.dll`, `libpython3.12.dll`, `librenpython.dll`, `libwinpthread-1.dll` and `nvdrs.dll`. A whole-tree search finds no Steam binary at all — only `lib/python3.12/steamapi.pyc`, the ctypes wrapper, which is useless without the DLL.

So `steam_init()` returns early, the Steam backend is never added, and `achievement.grant()` falls through to the persistent-only backend. It fails silently, which is why nothing appears in the log.

There is also no in-game achievement gallery, so Steam was the only place they could ever have shown.

## Fix

Put `steam_api64.dll` from **Steamworks SDK 1.62** into:

```
CSE-2.1.0-pc/lib/py3-windows-x86_64/steam_api64.dll     # 319584 bytes
```

Same folder as `librenpython.dll` — that is where `00steam.rpy` looks (`os.path.dirname(sys.executable)`). Then launch **through Steam** (and, on macOS/Linux, with the Steam client running in the same Wine prefix/bottle), so the appid is supplied.

### The version matters exactly

`steamapi.load()` binds all **1067** symbols eagerly by direct attribute access, with no `getattr` fallback and no exception table. One missing export raises `AttributeError`, `steam_init()` catches it, and Steam is disabled — the same silent nothing you started with. Ren'Py 8.5 wants a very specific window:

| SDK | Missing symbols |
|---|---|
| 1.61 | **14** — `SteamFriends_v018`, `SteamUGC_v021`, `SteamRemotePlay_v003` + their methods |
| 1.62 | **0** ✅ |
| newer (1.6x+) | **59** — `SteamUtils_v010`, `SteamApps_v008`, `SteamInput_v006`, `SteamGameSearch_v001`, `SteamMusicRemote_v001`, … |

1.61 and the newer SDKs miss *disjoint* sets: `Friends_v018` / `UGC_v021` / `RemotePlay_v003` are newer than 1.61, while `Utils_v010` / `Apps_v008` / `Input_v006` are older than the current SDK. 1.62 is the only one that satisfies both ends.

Check a candidate DLL before copying it — all six must hit:

```sh
for s in SteamAPI_SteamUtils_v010 SteamAPI_SteamApps_v008 SteamAPI_SteamInput_v006 \
         SteamAPI_SteamFriends_v018 SteamAPI_SteamUGC_v021 SteamAPI_SteamRemotePlay_v003; do
  printf '%s %s\n' "$(grep -ac "$s" steam_api64.dll)" "$s"
done
```

Six `1`s → correct DLL. Any `0` → wrong SDK version, do not use it.

### Where to get it

- Official: `partner.steamgames.com/downloads/list` → `steamworks_sdk_162.zip` → `sdk/redistributable_bin/win64/steam_api64.dll`. Needs a partner login.
- Public mirror of the same redistributables: `julianxhokaxhiu/SteamworksSDKCI` releases, tagged per SDK version.

**Never** take it from a cracked game. Goldberg / SmartSteamEmu / CreamAPI drop-ins use the same filename and fake achievements locally instead of sending them to Steam.

## Verify it loaded

`steam_init()` logs its outcome (`00steam.rpy:1059`/`1062`). Check `log.txt`:

| Line | Meaning |
|---|---|
| `Initialized steam.` | DLL loaded, all 1067 symbols bound, `SteamAPI_InitFlat` returned 0 ✅ |
| `Failed to initialize steam: <error>` | DLL found, something else broke |
| *neither line* | DLL still not found — old silent path |

Confirmed working on this install:

```
Initialized steam.
 - Init at renpy/common/00steam.rpy:879 took 1044 ms.
```

The 1044 ms is the real Steam handshake.

## Backfilling the achievements you already earned

`achievement.sync()` (`00achievement.rpy:292`) pushes everything in `persistent`:

```python
for a in persistent._achievements:
    for i in backends:
        if not i.has(a):
            i.grant(a)
```

**The catch:** in `archievement.rpy` the `register()` calls *and* both `sync()` calls sit inside `label achievement(who):`. There is no `init python` block, so nothing runs at startup and the Steam name map (`new_1` → `achievement_1`) stays empty until that label is called.

So: load a save and **play forward to the next achievement point**. Reaching any trigger runs the trailing `sync()`, which loops over all of `persistent._achievements` — not just the one you triggered — and pushes the lot. Expect eight or nine popups at once.

Only what is already in `persistent` gets pushed; anything not yet earned still has to be earned normally.

> The *leading* `sync()` at the top of the label is a bug in the game's script:
> on the first call the name map is still empty, so it pushes raw `new_1` instead
> of `achievement_1` and Steam drops it. Harmless — the trailing one fixes it.
