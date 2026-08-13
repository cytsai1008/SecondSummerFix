# Fixed by the developer — kept for reference

**English** · [简体中文](README.zh-CN.md)

Two of the four original problems were fixed by the small update of **2026-08-13** (depot `4309031`, manifest `4957350886103385162`, build `24699923`, built 2026-08-12 18:59 UTC). Nothing in this folder is needed on that build or later. It stays here for anyone on an older build, and as the record of what was wrong.

| Was broken | Fixed by | Workaround kept here |
|---|---|---|
| Steam achievements never unlock | The build now ships `steam_api64.dll` | [achievements.md](achievements.md) |
| Steam Cloud syncs the old `CSE-1.0-pc` saves folder | Cloud config now points at `CSE-2.1.0-pc\game\saves` | `make-junction.cmd` / `.sh` |

## What the update actually changed

The manifest adds exactly two files — the missing Steam libraries:

```
+ CSE-2.1.0-pc\lib\py3-windows-x86_64\steam_api64.dll   319584 bytes
+ CSE-2.1.0-pc\lib\py3-linux-x86_64\libsteam_api.so     388288 bytes
```

The Windows DLL is 319584 bytes — the same Steamworks SDK 1.62 build [achievements.md](achievements.md) told you to copy in by hand. If you already placed it there, Steam leaves your copy alone because the content matches.

Cloud is a server-side change, so no file shows it. Check `<Steam>\userdata\<accountid>\4309030\remotecache.vdf`: every tracked entry is now `CSE-2.1.0-pc/game/saves/...`, and Steam has written its `steam_autocloud.vdf` marker into that folder. No `CSE-1.0-pc` path is left.

## If you still have the junction

Leave it or remove it, both are fine. It points the old folder at the current one, so it is now redundant rather than wrong. To remove it: `make-junction.cmd --undo` (or `.sh --undo`), with Steam and the game closed. The scripts still expect to sit in the install root next to `CSE-2.1.0-pc\`, same as `savefix`.

## What was *not* fixed

- **Saves broken by the 1.0 → 2.1.0 update** still need `tools/savefix` — see [../docs/saves.md](../docs/saves.md). This update recompiled the scripts again, but the statement identifiers survived, so 2.1.0 saves keep loading.
- **Wine/CrossOver audio** is untouched: `environment.txt` is not part of the depot — see [../wine/README.md](../wine/README.md).
