#!/bin/sh
# make-junction.sh -- point Steam Cloud's save folder at the one the game uses.
#
# Steam Auto-Cloud for this game syncs
#     <install>/CSE-1.0-pc/game/saves
# which belongs to the OLD 1.0 install. The current build never reads or writes
# it. Ren'Py does keep
#     <install>/CSE-2.1.0-pc/game/saves
# up to date on its own. Linking the first at the second means Steam always sees
# current saves, and anything Steam downloads lands where the game already looks.
#
# Both paths live inside the game install, so no Wine prefix is involved.
#
# On Linux/Wine use a normal symlink, NOT `mklink` under wine cmd: junctions are
# an NTFS reparse point, and the filesystem under a Wine prefix is usually ext4
# or btrfs, which has no such thing. Wine presents a symlinked directory to
# Windows programs as an ordinary directory, and the Steam client follows it too,
# so a symlink is both the working and the correct mechanism here.
#
# Usage:
#     ./make-junction.sh [install-dir] [--dry-run] [--undo]
#
# With no install-dir it looks next to this script, then in the usual Steam
# library locations. Nothing is deleted without a backup.

set -eu

OLD_REL="CSE-1.0-pc/game/saves"          # what Steam syncs
NEW_REL="CSE-2.1.0-pc/game/saves"        # what the game actually uses
LINK_TARGET="../../CSE-2.1.0-pc/game/saves"   # relative: survives the install moving

DRY=0
UNDO=0
ROOT=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY=1 ;;
        --undo)    UNDO=1 ;;
        -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)        echo "unknown option: $arg" >&2; exit 2 ;;
        *)         ROOT="$arg" ;;
    esac
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- find install

if [ -z "$ROOT" ]; then
    here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    for cand in \
        "$(dirname -- "$here")" \
        "$HOME/.steam/steam/steamapps/common/CSE-1.0-pc" \
        "$HOME/.local/share/Steam/steamapps/common/CSE-1.0-pc" \
        "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/CSE-1.0-pc" \
        "/run/media/mmcblk0p1/steamapps/common/CSE-1.0-pc"
    do
        if [ -d "$cand/$NEW_REL" ] || [ -d "$cand/CSE-2.1.0-pc" ]; then
            ROOT=$cand
            break
        fi
    done
fi

[ -n "$ROOT" ] || die "could not find the game install. Pass it explicitly:
       $0 /path/to/steamapps/common/CSE-1.0-pc"

ROOT=$(CDPATH= cd -- "$ROOT" && pwd) || die "cannot enter $ROOT"
OLD="$ROOT/$OLD_REL"
NEW="$ROOT/$NEW_REL"

step "Install"
say "  $ROOT"
[ -d "$ROOT/CSE-2.1.0-pc" ] || die "no CSE-2.1.0-pc inside $ROOT -- is this the right folder?"

# ------------------------------------------------------------------------ undo

if [ "$UNDO" -eq 1 ]; then
    step "Undo"
    if [ -L "$OLD" ]; then
        [ "$DRY" -eq 1 ] && { say "  would remove symlink $OLD"; exit 0; }
        rm -- "$OLD"
        mkdir -p -- "$OLD"
        cp -p -- "$NEW"/*.save "$NEW"/persistent "$OLD"/ 2>/dev/null || true
        say "  replaced the symlink with a real folder holding a copy of the saves"
    else
        say "  $OLD is not a symlink; nothing to undo"
    fi
    exit 0
fi

# --------------------------------------------------------------- already done?

if [ -L "$OLD" ]; then
    current=$(readlink -- "$OLD")
    resolved=$(CDPATH= cd -- "$(dirname -- "$OLD")" && CDPATH= cd -- "$current" 2>/dev/null && pwd || true)
    if [ "$resolved" = "$NEW" ]; then
        step "Nothing to do"
        say "  already linked: $OLD -> $current"
        exit 0
    fi
    die "$OLD is already a symlink, but points at:
         $current
       Refusing to touch it. Remove it yourself if that is wrong."
fi

# The game creates this on first run; make it so a fresh install can be linked.
if [ ! -d "$NEW" ]; then
    say "  target does not exist yet, creating: $NEW"
    [ "$DRY" -eq 1 ] || mkdir -p -- "$NEW"
fi

# ---------------------------------------------------------------------- backup

step "Backup"
if [ -d "$OLD" ]; then
    n=$(find "$OLD" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
    if [ "$n" -gt 0 ]; then
        stamp=$(date +%Y%m%d-%H%M%S)
        dest="$ROOT/_save_backup_${stamp}_prelink"
        if [ "$DRY" -eq 1 ]; then
            say "  would copy $n files -> $dest"
        else
            mkdir -p -- "$dest/CSE-1.0-pc-game-saves"
            cp -p -- "$OLD"/* "$dest/CSE-1.0-pc-game-saves"/ 2>/dev/null || true
            printf 'Backup taken %s\n\nCSE-1.0-pc-game-saves\n    came from: %s\n' \
                "$(date '+%Y-%m-%d %H:%M:%S')" "$OLD" > "$dest/WHERE.txt"
            say "  copied $n files -> $dest"
        fi
    else
        say "  $OLD is empty, nothing to back up"
    fi
else
    say "  $OLD does not exist yet, nothing to back up"
fi

# ------------------------------------------------------------------------ link

step "Link"
if [ "$DRY" -eq 1 ]; then
    say "  would replace $OLD"
    say "  with a symlink -> $LINK_TARGET"
    say ""
    say "  dry run, nothing written"
    exit 0
fi

[ ! -e "$OLD" ] || rm -rf -- "$OLD"
mkdir -p -- "$(dirname -- "$OLD")"
ln -s -- "$LINK_TARGET" "$OLD"
say "  $OLD"
say "    -> $LINK_TARGET"

# ---------------------------------------------------------------------- verify

step "Verify"
[ -L "$OLD" ] || die "not a symlink after creation -- something is wrong"
[ -d "$OLD" ] || die "symlink does not resolve to a directory (dangling target?)"

probe="$OLD/.linktest"
: > "$probe"
if [ -e "$NEW/.linktest" ]; then
    say "  write through the link appears in the target: yes"
else
    rm -f -- "$probe"
    die "write through the link did NOT appear in the target"
fi
rm -f -- "$NEW/.linktest"
[ -e "$probe" ] && die "cleanup through the target did not take effect"

say "  link resolves to : $(CDPATH= cd -- "$OLD" && pwd -P)"
say "  files visible    : $(find "$OLD/" -maxdepth 1 -type f | wc -l | tr -d ' ')"

step "Done"
say "  Steam now syncs the folder the game actually uses."
say "  Launch and quit through Steam, then check that this file updates:"
say "    ~/.steam/steam/userdata/<accountid>/4309030/remotecache.vdf"
