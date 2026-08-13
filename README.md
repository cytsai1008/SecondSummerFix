# SecondSummerFix

**English** · [简体中文](README.zh-CN.md)

Fixes for *A Second Chance to Relive Summer* (Ren'Py, Steam app **4309030**) — broken saves after the 1.0 → 2.1.0 update, Steam Cloud syncing the wrong folder, Steam achievements never firing, and distorted audio under CrossOver/Wine.

**The small update of 2026-08-13 fixed two of these**: the build now ships `steam_api64.dll`, and Steam Cloud now syncs the folder the game really uses. Those workarounds moved to [`fixed/`](fixed/README.md) — keep reading only if you are on an older build.

Each fix is independent. Take the one matching your symptom.

## Symptom → fix

| What you see | Fix |
|---|---|
| `Couldn't find a place to stop rolling back` when loading a save | `tools/savefix.cmd fix` — [docs/saves.md](docs/saves.md) |
| Clicking a save slot does nothing at all | Same. The save's signature is stale; `fix` re-signs it. |
| Low volume, crackle, wrong pitch (macOS/Linux, Wine) | `wine/environment.txt` — [wine/README.md](wine/README.md) |
| Saves differ between machines, or Steam Cloud restores old ones | Fixed 2026-08-13. Older builds: [fixed/README.md](fixed/README.md) |
| Achievements never unlock on Steam | Fixed 2026-08-13. Older builds: [fixed/achievements.md](fixed/achievements.md) |

## Install

Quick download (just `tools/`, no repo clone): [tools.zip](https://github.com/cytsai1008/SecondSummerFix/releases/latest/download/tools.zip)

Copy `tools/` into the game's install root — the folder holding `CSE-1.0-pc\` and `CSE-2.1.0-pc\` — so it sits one level above them:

```
...\steamapps\common\CSE-1.0-pc\
    CSE-1.0-pc\
    CSE-2.1.0-pc\
    tools\            <- here
```

`savefix.py` locates the installs by scanning its own parent directory, so running it from anywhere else exits with `no installed game found under <path>`. `wine/environment.txt` is different: it goes next to each `.exe`, see [wine/README.md](wine/README.md).

## Files

| | |
|---|---|
| `tools/savefix.py` `savefix.cmd` | Save checker/repairer. Run the `.cmd`; it supplies the `ecdsa` dependency. |
| `wine/environment.txt` | Drop next to the game's `.exe` to fix Wine audio. |
| `docs/saves.md` | Why saves break, how the repair works, save locations, Steam Cloud, two-machine play. |
| `wine/README.md` | The Wine audio problem and the two settings that fix it. |
| `fixed/` | The two problems the 2026-08-13 update fixed, and the workarounds they needed. |

Everything under `wine/` applies only to running the Windows build through Wine or CrossOver. On Windows, ignore that folder. The rest applies everywhere.

Nothing here is game-specific beyond the paths: `savefix.py` hardcodes no version numbers or offsets, and the audio fix works for any Ren'Py game under Wine.

## Safety

- `savefix` with no argument is read-only. Backups are automatic before any write.
- Saves and `.rpyc` files are pickles; the tools never hand them to the stock unpickler, so nothing inside them can execute.
- Take the `steam_api64.dll` from the official SDK, never from a cracked game.
