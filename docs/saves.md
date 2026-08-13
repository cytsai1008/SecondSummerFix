# Save repair, save locations and Steam Cloud

**English** · [简体中文](saves.zh-CN.md)

Repairs Ren'Py save files that stop loading after a game update, and keeps every save location holding the same thing.

If the game crashes when you click a save slot with:

```
Exception: Couldn't find a place to stop rolling back.
Perhaps the script changed in an incompatible way?
```

this is the fix.

---

## Quick start

Close the game, then:

```
savefix
```

That's read-only. It prints the state of every save and ends with a **What to do** section naming the exact command to run next. You never have to decide which tool to use.

Double-clicking `savefix.cmd` does the same and keeps the window open.

### Commands

| Command | What it does |
|---|---|
| `savefix` | Check every save and location. Safe, writes nothing. |
| `savefix fix` | Back up, then repair every broken save. |
| `savefix sync` | Back up, then copy the live saves to all locations. |
| `savefix backup` | Take a backup and stop. |

Add `--dry-run` to `fix` or `sync` to see the plan without writing.

Backups are automatic before any write, and land in the install root as `..\CSE-1.0-pc\_save_backup_<timestamp>_<reason>\`.

**Restoring is a plain file copy.** Every backup contains a `WHERE.txt` naming the folder each subfolder came from — copy the files back and you're done. There is no `restore` command on purpose: at the point you need one, you want to see exactly what you're overwriting.

---

## Why saves break

Ren'Py identifies every statement in the script by a triple:

```
(filename, name_version, name_serial)
```

Those identifiers are baked into the compiled `.rpyc` files, and a save's rollback log stores them to remember where you were. When the developer recompiles the scripts for a new release, the identifiers are regenerated.

A save from the old build then points at statements that no longer exist. On load, `RollbackLog.rollback()` walks the log looking for one that is still in the script, finds none, runs off the end, and raises the exception above.

It is not corruption. Your story variables, flags and progress are all intact — only the *bookmarks* went stale.

### The 1.0 → 2.1.0 break, as a worked example

- Saves referenced `name_version` **1771353428**.
- CSE 2.1.0's chapter scripts carry **1771573257** / **1771573258**.
- Overlap: **zero**. The developer recompiled from scratch, so every identifier in every 1.0 save was dead. Nothing partial about it.
- Serials shifted too, but only slightly, and by differing amounts per region (−9, 0, +3 at different points in `script_chapter_2.rpy`) — the signature of statements being inserted and removed, not renumbered wholesale.

### The 2026-08-13 update did *not* do this

That update recompiled the scripts again (`scripts.rpa` and the bytecode caches changed), but the identifiers survived: 2.1.0 saves still load, and the ones already repaired stay repaired. A recompile only breaks saves when the developer rebuilds from scratch, which is what happened at 1.0 → 2.1.0 and did not happen here. Run `savefix` after any update anyway — it is read-only and tells you in one screen.

---

## How the repair works

1. **Find the resume point by content.** The save records the last line of dialogue shown (`store._last_say_what`). That text is matched against the installed script. A unique match gives the statement you were on, and therefore the serial offset. If the line is ambiguous, the preceding lines of your dialogue history are used to pick between candidates.

2. **Corroborate with history.** Every line in the save's history is matched the same way. Those matches must come out in strictly increasing order — if they don't, that region of the script was restructured and the offset can't be trusted.

3. **Rewrite conservatively.** Only identifiers inside the window the history confirms get rewritten. Older ones are deliberately **left dead**. A dead identifier only caps how far you can roll back; a wrongly mapped one would drop you at the wrong line. That is why repaired saves show varying rollback depths (`14/129`, `43/129`, …) — that's the safety margin, not damage.

4. **Refuse rather than guess.** If a `call_location_stack` entry wouldn't land on a `Call` statement, the save is skipped instead of being written with a broken return stack.

5. **Patch in place.** Version is a 4-byte `BININT` and serial a 1/2/4-byte `BININT*` in the pickle. Replacements are written at the same byte width, so nothing shifts and the pickle's memo table stays valid. No re-pickling. Any rewrite that would need a wider opcode is skipped instead of resizing the stream.

6. **Re-sign.** Ren'Py signs the log with an ECDSA key in `%APPDATA%\RenPy\tokens\security_keys.txt`. Patching invalidates that, and `check_load()` then rejects the save **silently** — it looks like nothing happens when you click the slot. The log is re-signed with your own local key, the same thing Ren'Py's `upgrade_savefile` does.

7. **Verify.** Each repaired save is re-read and put through the exact check Ren'Py performs on load before it is reported as fixed.

### Safety

Save files and `.rpyc` files are pickles, and pickles can execute code. They are never handed to the stock unpickler. `SafeUnpickler.find_class` refuses to import anything and returns an inert stub class instead, so nothing inside a save or a script file can run. The tools only ever read data out of them.

---

## Save locations

Ren'Py keeps saves in more than one place, and the one Steam Cloud syncs is not the one the game reads:

| Location | Role |
|---|---|
| `%APPDATA%\RenPy\SCR-1758907360\` | **Live.** What the game actually reads and writes. |
| `CSE-2.1.0-pc\game\saves\` | Mirror, current install. The game writes here too, and **Steam Cloud syncs this**. |
| `CSE-1.0-pc\game\saves\` | Old install. Dead — nothing reads or syncs it any more. |
| `%APPDATA%\RenPy\SCR-1758907360\sync\` | Ren'Py Sync staging. Not scanned on load. |

> Until the small update of **2026-08-13**, Steam Cloud synced the `CSE-1.0-pc` folder
> instead — a folder the 2.1.0 build neither reads nor writes. That is fixed; the
> junction workaround it needed now lives in [../fixed/README.md](../fixed/README.md).
> If you made that junction, the last two rows are one folder under two names, which
> `savefix` detects (via `realpath`) and lists once.

`savefix sync` pushes the live saves to all locations, which is what makes the cloud copy worth having.

`savefix` finds these itself — including old installs with no scripts left — so this table is background, not something you need to act on.

### What Steam actually syncs

App ID **4309030**, cloud root `GameInstall`, and exactly one folder:

```
<Steam>\steamapps\common\CSE-1.0-pc\CSE-2.1.0-pc\game\saves\
```

That's the save slots plus `persistent`.

You can confirm this yourself — Steam records every file it tracks in:

```
<Steam>\userdata\<accountid>\4309030\remotecache.vdf
```

Every entry there should start with `CSE-2.1.0-pc/game/saves/`. If yours still say `CSE-1.0-pc/`, you are on a build older than 2026-08-13. Steam also drops a `steam_autocloud.vdf` marker in the folder it syncs, which is how `savefix` tags it in its report.

---

## Playing on two machines

Steam now syncs the mirror, but the game's source of truth is still `%APPDATA%`, so the two ends need a copy step:

```
   live savedir  %APPDATA%\RenPy\SCR-...        <- the game reads/writes here
        ^  |                                        (savefix sync connects these)
        |  v
   Steam cloud   CSE-2.1.0-pc\game\saves        <- Steam reads/writes here
```

On the machine you just played, run `savefix sync`, then quit Steam so it uploads. On the other machine, after Steam has downloaded, copy the files from `CSE-2.1.0-pc\game\saves\` into `%APPDATA%\RenPy\SCR-1758907360\` and play.

The outbound half goes stale the moment you play again, so make `savefix sync` the last thing you do before quitting.

> Before 2026-08-13 the cloud folder was the *old* install's, which the game never
> touches at all — the junction in [../fixed/](../fixed/README.md) existed to bridge
> that gap. It is no longer needed, and harmless if you already made it.

### Notes

- The first load on the other machine shows Ren'Py's **"unknown token"** prompt, because saves are signed with the originating machine's key. Accept it, and accept the offer to trust the key, and it won't ask again.
- `persistent` is synced too, so unlocks and gallery progress travel with you.
- If the two machines are on different game versions, the saves will show as `BROKEN`. Run `savefix fix`. That's expected, not a failure.
- Crash dumps in the mirror (`_tracesave-*.save`, a few hundred KB) get uploaded too. Harmless, and safe to delete.

### General save notes

- **Crash dumps (`_tracesave-*.save`) are ignored.** They're written when the game throws, not save points. Their timestamps are useful for working out *when* something broke.
- **Autosaves rotate.** `auto-1` … `auto-10` shift as you play, so an old autosave point can age out of the ring while you're working on something else.
- **Moving saves to another PC** triggers Ren'Py's "unknown token" prompt, because the signature is tied to this machine's key. Accept it and the save loads. That's true of untouched saves too — not something the repair introduces.

---

## If it goes wrong

Everything is reversible. Backups are plain folders of plain files: open the most recent `_save_backup_*` folder, read `WHERE.txt`, and copy each subfolder's files back into the folder it names. The one that matters is `Roaming-RenPy-SCR-1758907360` — that's the live save folder.

### Common cases

**"the ecdsa module is required"** — run `savefix.cmd`, not `savefix.py` directly. The launcher uses `uv` to supply `ecdsa`. Without `uv`, run `pip install ecdsa`.

**"cannot locate resume point"** — the save's last line of dialogue isn't in the installed build, usually because that scene was rewritten or cut. The save is left untouched rather than guessed at. Nothing is lost; it just can't be automatically placed.

**A save still won't load after `fix`** — restore the backup and say so. The tool verifies before reporting success, so this shouldn't happen silently.

**Steam Cloud overwrote something** — run `savefix` to see which locations disagree, then `savefix sync` to push the live saves back out. Playing offline while sorting this out avoids a download clobbering your work.

---

## Files

| File | |
|---|---|
| `savefix.cmd` | **Run this.** Handles the `ecdsa` dependency. |
| `savefix.py` | All the logic. Self-contained, no other imports. |

`savefix.py` hardcodes no paths, no version numbers and no offsets, so it should handle the next update as well as it handled this one.
