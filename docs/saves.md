# Save repair, save locations and the Steam Cloud junction

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

Ren'Py keeps saves in more than one place, and Steam Cloud may sync a different one than the game reads:

| Location | Role |
|---|---|
| `%APPDATA%\RenPy\SCR-1758907360\` | **Live.** What the game actually reads and writes. |
| `CSE-2.1.0-pc\game\saves\` | Mirror, current install. The game writes here too. |
| `CSE-1.0-pc\game\saves\` | **Junction** to the folder above. Steam Cloud syncs this. |
| `%APPDATA%\RenPy\SCR-1758907360\sync\` | Ren'Py Sync staging. Not scanned on load. |

> The junction was created on 2026-08-10, so the last two rows are one folder under
> two names. `savefix` detects this (via `realpath`) and lists it once.

The old-install folder is a trap: CSE 2.1.0 never reads it, so repairing your saves does nothing for what Steam Cloud holds. `savefix sync` pushes the live saves to all of them, which is what makes the cloud copy worth having.

`savefix` finds these itself — including old installs with no scripts left — so this table is background, not something you need to act on.

### What Steam actually syncs

App ID **4309030**, cloud root `GameInstall`, and exactly one folder:

```
<Steam>\steamapps\common\CSE-1.0-pc\CSE-1.0-pc\game\saves\
```

That's 11 save slots plus `persistent`. The path is hardcoded to the **old** install and was never updated for the 2.1.0 layout, so Steam is syncing a folder the current build neither reads nor writes.

You can confirm this yourself — Steam records every file it tracks in:

```
<Steam>\userdata\<accountid>\4309030\remotecache.vdf
```

Steam also drops a `steam_autocloud.vdf` marker in the folder it syncs, which is how `savefix pull` identifies it.

---

## Playing on two machines

Because Steam syncs a folder the game doesn't read, the chain is broken in the middle and needs a copy step at each end:

```
   live savedir  %APPDATA%\RenPy\SCR-...     <- the game reads/writes here
        ^  |                                     (nothing connects these)
        |  v
   Steam cloud   CSE-1.0-pc\game\saves       <- Steam reads/writes here
```

### The manual way

On the machine you just played, run `savefix sync`, then quit Steam so it uploads. On the other machine, after Steam has downloaded, copy the files from `CSE-1.0-pc\game\saves\` into `%APPDATA%\RenPy\SCR-1758907360\` and play.

That works, but the outbound half goes stale the moment you play again, so it is easy to forget.

### The junction (better)

Ren'Py genuinely reads and writes `CSE-2.1.0-pc\game\saves` — the game keeps it current by itself. So making Steam's folder a junction to it removes both manual steps:

```
mklink /J "<...>\CSE-1.0-pc\CSE-1.0-pc\game\saves" "<...>\CSE-1.0-pc\CSE-2.1.0-pc\game\saves"
```

`tools/make-junction.cmd` (Windows) and `tools/make-junction.sh` (Linux/macOS + Wine) do this for you, including finding the install, backing up the folder they replace, and `--dry-run` / `--undo`. On Linux and macOS they make a plain symlink rather than a junction: a junction is an NTFS reparse point, the filesystem under a Wine prefix isn't NTFS, and Wine presents a symlinked directory to Windows programs — Steam included — as an ordinary directory. Same result, correct mechanism.

> Both scripts hardcode the folder names `CSE-1.0-pc` (Steam's) and
> `CSE-2.1.0-pc` (the game's). After the next update, edit the two variables at
> the top — `OLD_REL`/`NEW_REL` in the `.sh`, `OLD`/`NEW` in the `.cmd` — to the
> new folder name. `savefix.py` needs no such edit; it globs for whatever install
> is there.

Outbound, Steam always sees current saves with no `sync` needed. Inbound, Steam's download lands in a folder the game already reads, so the saves simply appear.

Do it with **Steam and the game both closed**, take a backup first, and make sure the folder holds current saves before linking — link while it holds older ones and Steam's first sync may push those stale files back at you.

A junction is the right tool here (`mklink /J`, no admin required). What matters is that it points at the *mirror*, not at `%APPDATA%`. Linking Steam to `%APPDATA%` would wire your source of truth into Steam's conflict resolution, so a bad download — or an uninstall deleting through the link — would take your real saves. Pointing at the mirror keeps `%APPDATA%` entirely out of Steam's reach, so the worst case is a replaceable copy and a `savefix sync` to put it right.

### Notes

- The first load on the other machine shows Ren'Py's **"unknown token"** prompt, because saves are signed with the originating machine's key. Accept it, and accept the offer to trust the key, and it won't ask again.
- `persistent` is synced too, so unlocks and gallery progress travel with you.
- If the two machines are on different game versions, the saves will show as `BROKEN`. Run `savefix fix`. That's expected, not a failure.
- With the junction in place, the crash dumps in the mirror (`_tracesave-*.save`, a few hundred KB) get uploaded too. Harmless, and safe to delete.
- **Under CrossOver, a junction made by `mklink /J` looks like an empty directory from macOS** — Wine stores the reparse point in a `user.WINEREPARSE` extended attribute (`xattr -l <dir>` shows it). It resolves correctly for the game and for Steam inside the bottle. Run natively on macOS, `savefix` cannot follow it, so it simply does not list the `CSE-1.0-pc\game\saves` path at all — it reports the real folder, correctly tagged `<- Steam Cloud syncs this` from the `steam_autocloud.vdf` marker that lands there through the link.

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
| `make-junction.cmd` / `.sh` | Create (or `--undo`) the Steam Cloud junction. |

`savefix.py` hardcodes no paths, no version numbers and no offsets, so it should handle the next update as well as it handled this one.
