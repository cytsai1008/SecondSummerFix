#!/usr/bin/env python3
"""
CSE save fixer -- repairs Ren'Py saves broken by a game update, and keeps every
save location holding the same thing.

Why saves break
---------------
Ren'Py identifies each statement by (filename, name_version, name_serial).
When the developer recompiles the scripts for a new release, those identifiers
are regenerated. A save from the old build then references statements that no
longer exist, RollbackLog.rollback() scans the whole log without finding one,
and the game dies with:

    Couldn't find a place to stop rolling back.
    Perhaps the script changed in an incompatible way?

What this does
--------------
Rewrites the dead identifiers in the save's rollback log to the matching ones in
the installed build. The resume point is found by matching the save's last line
of dialogue against the current script, which yields the serial offset. Only
identifiers corroborated by the save's dialogue history are rewritten -- a dead
identifier merely caps rollback depth, but a wrong one would drop you at the
wrong line. The patched log is then re-signed with your own local save token,
because Ren'Py silently refuses saves whose signature does not match.

Usage
-----
    savefix                 check everything (safe, read-only)
    savefix fix             back up, then repair every broken save
    savefix sync            back up, then copy the live saves to all locations
    savefix backup          just take a backup

Add --dry-run to fix or sync to see the plan without writing anything.
Saves are backed up automatically before any write.

Restoring a backup is a plain file copy -- each backup folder contains a
WHERE.txt saying which folder every subfolder came from.
"""

import base64
import collections
import glob
import io
import os
import pickle
import pickletools
import shutil
import struct
import sys
import time
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


# --------------------------------------------------------------------------
# console
# --------------------------------------------------------------------------

def _colour():
    if os.environ.get("NO_COLOR"):
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            return False
    return sys.stdout.isatty()


COLOUR = _colour()


def c(t, code):
    return "\033[%sm%s\033[0m" % (code, t) if COLOUR else t


def ok(t):
    return c(t, "32")


def bad(t):
    return c(t, "31")


def warn(t):
    return c(t, "33")


def dim(t):
    return c(t, "90")


def head(t):
    print("\n" + c(t, "1;36"))
    print(c("-" * len(t), "36"))


def die(msg):
    print(bad("\nERROR: " + msg))
    sys.exit(1)


# --------------------------------------------------------------------------
# inert unpickler
#
# Save logs and .rpyc files are pickles. They are never given to the stock
# unpickler: find_class refuses to import anything and hands back an inert
# stub, so nothing inside a save or a script file can execute.
# --------------------------------------------------------------------------

class Stub(object):
    def __init__(self, *a, **kw):
        pass

    # NEWOBJ bypasses __init__, so containers are built lazily
    def __setitem__(self, k, v):
        self.__dict__.setdefault("_items", {})[k] = v

    def __getitem__(self, k):
        return self.__dict__.setdefault("_items", {})[k]

    def append(self, v):
        self.__dict__.setdefault("_list", []).append(v)

    def extend(self, vs):
        self.__dict__.setdefault("_list", []).extend(vs)

    def add(self, v):
        self.__dict__.setdefault("_list", []).append(v)

    def __setstate__(self, state):
        # Ren'Py AST nodes use __slots__: state is (instance_dict, slots_dict)
        if isinstance(state, tuple) and len(state) == 2:
            for part in state:
                if isinstance(part, dict):
                    self.__dict__.update(part)
        elif isinstance(state, dict):
            self.__dict__.update(state)
        else:
            self.__dict__["_state"] = state

    def __repr__(self):
        return "<%s>" % type(self).__name__


_stubs = {}


def _stub(module, name):
    if (module, name) not in _stubs:
        _stubs[(module, name)] = type(str(name), (Stub,), {})
    return _stubs[(module, name)]


class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        return _stub(module, name)

    def persistent_load(self, pid):
        return None


def loads(data):
    return SafeUnpickler(io.BytesIO(data)).load()


def walk(obj, visit):
    """Call visit(stub) for every stub reachable from obj."""
    seen, stack = set(), [obj]
    while stack:
        o = stack.pop()
        if id(o) in seen:
            continue
        seen.add(id(o))
        if isinstance(o, (list, tuple)):
            stack.extend(o)
        elif isinstance(o, dict):
            stack.extend(o.keys())
            stack.extend(o.values())
        elif isinstance(o, Stub):
            visit(o)
            stack.extend(o.__dict__.values())


# --------------------------------------------------------------------------
# locating the install and the save folders
# --------------------------------------------------------------------------

def find_gamedirs():
    """Every Ren'Py 'game' folder under ROOT that still has compiled scripts."""
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "*", "game"))) + [os.path.join(ROOT, "game")]:
        if os.path.isdir(p) and (
            os.path.exists(os.path.join(p, "scripts.rpa")) or glob.glob(os.path.join(p, "*.rpyc"))
        ):
            out.append(p)
    return out


def pick_gamedir():
    dirs = find_gamedirs()
    if not dirs:
        die("no installed game found under %s" % ROOT)
    dirs.sort(key=os.path.getmtime)
    return dirs[-1]


def script_version(gamedir):
    try:
        return open(os.path.join(gamedir, "script_version.txt")).read().strip()
    except Exception:
        return "?"


def find_locations():
    """(live savedir, [mirrors that should hold the same saves])."""
    base = os.path.join(os.environ.get("APPDATA", ""), "RenPy")
    cands = [
        d for d in (os.path.join(base, e) for e in sorted(os.listdir(base)))
        if os.path.isdir(d) and glob.glob(os.path.join(d, "*.save"))
    ] if os.path.isdir(base) else []
    if not cands:
        die(r"no Ren'Py save folder found in %APPDATA%\RenPy")
    cands.sort(key=lambda d: max(os.path.getmtime(f) for f in glob.glob(os.path.join(d, "*.save"))))
    primary = cands[-1]

    # every <root>/*/game/saves, whether or not that install still has scripts:
    # an old install's saves folder is often what Steam Cloud syncs
    mirrors = []
    for p in (os.path.join(ROOT, "*", "game", "saves"), os.path.join(ROOT, "game", "saves")):
        mirrors.extend(sorted(d for d in glob.glob(p) if os.path.isdir(d)))
    sync = os.path.join(primary, "sync")
    if os.path.isdir(sync):
        mirrors.append(sync)

    # Collapse duplicates: a junction or symlink can make two paths name one
    # folder, and copying a file onto itself is at best pointless.
    seen, unique = {os.path.realpath(primary)}, []
    for m in mirrors:
        real = os.path.realpath(m)
        if real not in seen:
            seen.add(real)
            unique.append(m)
    return primary, unique


def slots(d):
    """Real save slots -- crash dumps are not save points."""
    return sorted(
        f for f in glob.glob(os.path.join(d, "*.save"))
        if not os.path.basename(f).startswith("_trace")
    )


def payload(d):
    """What a location should hold: every slot, plus persistent."""
    files = slots(d)
    p = os.path.join(d, "persistent")
    if os.path.exists(p):
        files.append(p)
    return files


def is_steam(d):
    """Steam marks the folder it syncs with steam_autocloud.vdf."""
    return os.path.exists(os.path.join(d, "steam_autocloud.vdf"))


# --------------------------------------------------------------------------
# reading the installed script
# --------------------------------------------------------------------------

def read_rpa(path):
    with open(path, "rb") as f:
        parts = f.readline().split()
        offset = int(parts[1], 16)
        key = int(parts[2], 16) if len(parts) > 2 else 0
        f.seek(offset)
        index = loads(zlib.decompress(f.read()))
        out = {}
        for name, entries in index.items():
            e = entries[0]
            f.seek(e[0] ^ key)
            out[name] = f.read(e[1] ^ key)
        return out


def load_rpyc(data):
    if data[:10] != b"RENPY RPC2":
        raise ValueError("not a RENPY RPC2 file")
    pos, chunks = 10, {}
    while True:
        slot, start, length = struct.unpack("III", data[pos:pos + 12])
        pos += 12
        if slot == 0:
            break
        chunks[slot] = data[start:start + length]
    return loads(zlib.decompress(chunks[1]))


class Script(object):
    """Index of every statement in the installed build."""

    def __init__(self, gamedir):
        self.nodes = collections.defaultdict(dict)   # file -> serial -> (ver, line, kind)
        self.texts = collections.defaultdict(list)   # file -> [(dialogue, serial)]

        blobs = {}
        rpa = os.path.join(gamedir, "scripts.rpa")
        if os.path.exists(rpa):
            blobs.update(read_rpa(rpa))
        for p in glob.glob(os.path.join(gamedir, "**", "*.rpyc"), recursive=True):
            blobs[os.path.relpath(p, gamedir)] = open(p, "rb").read()

        for name, data in blobs.items():
            if name.endswith(".rpyc"):
                try:
                    walk(load_rpyc(data)[1], self._note)
                except Exception:
                    continue
        if not self.nodes:
            die("could not read any statements from %s" % gamedir)

    def _note(self, o):
        d = o.__dict__
        fn, ver, ser = d.get("filename"), d.get("name_version"), d.get("name_serial")
        if isinstance(fn, str) and isinstance(ver, int) and isinstance(ser, int):
            self.nodes[fn][ser] = (ver, d.get("linenumber"), type(o).__name__)
            if isinstance(d.get("what"), str) and d["what"].strip():
                self.texts[fn].append((d["what"], ser))

    def alive(self, name):
        """Does this (file, version, serial) still exist?"""
        if not (isinstance(name, tuple) and len(name) == 3):
            return False
        fn, ver, ser = name
        e = self.nodes.get(fn, {}).get(ser)
        return e is not None and e[0] == ver

    def find_text(self, text):
        return [(fn, ser) for fn, lst in self.texts.items() for t, ser in lst if t == text]


# --------------------------------------------------------------------------
# reading a save
# --------------------------------------------------------------------------

class Save(object):
    def __init__(self, path):
        import json

        self.path, self.name = path, os.path.basename(path)
        with zipfile.ZipFile(path) as z:
            self.members = {i.filename: z.read(i.filename) for i in z.infolist()}
        self.meta = json.loads(self.members["json"].decode("utf-8"))
        self.roots, self.log = loads(self.members["log"])

        cur = self.log.__dict__.get("current")
        self.ctx = cur.__dict__.get("context").__dict__ if cur is not None else {}
        self.current = self.ctx.get("current")

        hist = self.roots.get("store._history_list")
        if isinstance(hist, Stub):
            hist = hist.__dict__.get("_list", [])
        self.history = [
            h.__dict__.get("what") for h in (hist or [])
            if isinstance(getattr(h, "__dict__", {}).get("what"), str)
        ]
        self.last_what = self.roots.get("store._last_say_what")

    @property
    def version(self):
        return self.meta.get("_version", "?")

    def names(self):
        """{serial: {(filename, version)}} for every identifier in the log."""
        found, seen, stack = {}, set(), [self.log]
        while stack:
            x = stack.pop()
            if id(x) in seen:
                continue
            seen.add(id(x))
            if isinstance(x, tuple) and len(x) == 3 and isinstance(x[0], str) and isinstance(x[1], int):
                found.setdefault(x[2], set()).add((x[0], x[1]))
            elif isinstance(x, (list, tuple)):
                stack.extend(x)
            elif isinstance(x, dict):
                stack.extend(x.keys())
                stack.extend(x.values())
            elif isinstance(x, Stub):
                stack.extend(x.__dict__.values())
        return found

    def rollback_names(self):
        out = []
        for rb in reversed(self.log.__dict__.get("log") or []):
            ctx = rb.__dict__.get("context")
            if ctx is not None:
                out.append(ctx.__dict__.get("current"))
        return out

    def status(self, script):
        """Reproduce the check Ren'Py performs when loading."""
        names = self.rollback_names()
        depth = 0
        for n in names:
            if not script.alive(n):
                break
            depth += 1
        calls = all(script.alive(l) for l in (self.ctx.get("call_location_stack") or []))
        loadable = script.alive(self.current) and bool(names) and script.alive(names[0]) and calls
        return dict(loadable=loadable, depth=depth, total=len(names))

    def where(self, script):
        if not script.alive(self.current):
            return "?"
        fn, _, ser = self.current
        return "%s:%s" % (os.path.basename(fn), script.nodes[fn][ser][1])

    def write(self, log_bytes, signatures):
        self.members["log"] = log_bytes
        if signatures is not None:
            self.members["signatures"] = signatures
        tmp = self.path + ".new"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for k, v in self.members.items():
                z.writestr(k, v)
        os.replace(tmp, self.path)


# --------------------------------------------------------------------------
# save tokens
# --------------------------------------------------------------------------

class Token(object):
    """The local ECDSA key Ren'Py signs saves with."""

    def __init__(self):
        self.ecdsa, self.signing, self.verifying = None, [], []
        try:
            import ecdsa
        except ImportError:
            return
        self.ecdsa = ecdsa
        path = os.path.join(os.environ.get("APPDATA", ""), "RenPy", "tokens", "security_keys.txt")
        if not os.path.exists(path):
            return
        for line in open(path):
            kind, a, _ = self._decode(line)
            if kind == "signing-key":
                self.signing.append(a)
            elif kind == "verifying-key":
                self.verifying.append(a)
        # a signing key's own public half is what the game signs with
        for k in self.signing:
            vk = ecdsa.SigningKey.from_der(k).verifying_key
            if vk is not None and vk.to_der() not in self.verifying:
                self.verifying.append(vk.to_der())

    @staticmethod
    def _decode(line):
        line = line.strip()
        if not line or line[0] == "#":
            return "", b"", None
        p = line.split(None, 2)
        try:
            if len(p) == 2:
                return p[0], base64.b64decode(p[1]), None
            return p[0], base64.b64decode(p[1]), base64.b64decode(p[2])
        except Exception:
            return "", b"", None

    @property
    def usable(self):
        return bool(self.ecdsa and self.signing)

    def sign(self, data):
        out = ""
        for k in self.signing:
            sk = self.ecdsa.SigningKey.from_der(k)
            if sk is not None and sk.verifying_key is not None:
                out += "signature %s %s\n" % (
                    base64.b64encode(sk.verifying_key.to_der()).decode(),
                    base64.b64encode(sk.sign(data)).decode(),
                )
        return out.encode("utf-8")

    def valid(self, data, signatures):
        if not self.ecdsa:
            return None
        if isinstance(signatures, bytes):
            signatures = signatures.decode("utf-8", "replace")
        for line in signatures.splitlines():
            kind, key, sig = self._decode(line)
            if kind != "signature" or key is None or key not in self.verifying:
                continue
            try:
                if self.ecdsa.VerifyingKey.from_der(key).verify(sig, data):
                    return True
            except Exception:
                continue
        return False


# --------------------------------------------------------------------------
# the repair
# --------------------------------------------------------------------------

def anchor(save, script):
    """Find the statement the save is sitting on, in the installed build."""
    if not save.last_what:
        return None, "save has no last line of dialogue to match on"
    cands = script.find_text(save.last_what)
    if len(cands) == 1:
        return cands[0], "unique dialogue match"
    if not cands:
        return None, "last line of dialogue is not in this build"
    scored = []
    for fn, ser in cands:
        n = sum(
            1 for t in save.history[-12:-1]
            if any(f == fn and ser - 80 < s < ser for f, s in script.find_text(t))
        )
        scored.append((n, fn, ser))
    scored.sort(key=lambda x: -x[0])
    if scored[0][0] >= 3 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return (scored[0][1], scored[0][2]), "disambiguated by %d preceding lines" % scored[0][0]
    return None, "last line is ambiguous (%d candidates)" % len(cands)


def plan(save, script):
    """Map every dead identifier to its replacement. Returns (mapping, notes)."""
    cur = save.current
    if not (isinstance(cur, tuple) and len(cur) == 3):
        return None, ["save has no current statement"]
    if script.alive(cur):
        return None, ["already valid for this build"]

    hit, how = anchor(save, script)
    if hit is None:
        return None, ["cannot locate resume point: " + how]
    notes = ["anchor: " + how]

    hit_fn, hit_ser = hit
    cur_fn, delta = cur[0], hit_ser - cur[2]
    notes.append("resume: %s %d -> %d (offset %+d), now line %s"
                 % (os.path.basename(cur_fn), cur[2], hit_ser, delta, script.nodes[hit_fn][hit_ser][1]))

    # only rewrite identifiers the dialogue history corroborates
    verified = set()
    for t in save.history:
        m = script.find_text(t)
        if len(m) == 1 and m[0][0] == cur_fn:
            verified.add(m[0][1] - delta)
    low = min(verified) if verified else cur[2]
    notes.append("verified window: %d..%d (%d lines)" % (low, cur[2], len(verified)))

    mapping = {}
    for serial, refs in save.names().items():
        for fn, ver in refs:
            if script.alive((fn, ver, serial)):
                continue
            if fn == cur_fn and serial < low:
                continue  # leave dead on purpose: caps rollback, never misplaces
            target = serial + delta if fn == cur_fn else serial
            entry = script.nodes.get(fn, {}).get(target)
            if entry is not None:
                mapping[(fn, ver, serial)] = (entry[0], target)

    # a call location must still be a Call, or returning from it breaks
    for loc in save.ctx.get("call_location_stack") or []:
        if not (isinstance(loc, tuple) and len(loc) == 3) or script.alive(loc):
            continue
        if loc not in mapping:
            notes.append(warn("call location %s:%d could not be remapped"
                              % (os.path.basename(loc[0]), loc[2])))
            continue
        kind = script.nodes[loc[0]][mapping[loc][1]][2]
        if kind != "Call":
            return None, notes + ["refusing: call location would become a %s, not a Call" % kind]
        notes.append("call location %s:%d -> %d (Call, ok)"
                     % (os.path.basename(loc[0]), loc[2], mapping[loc][1]))

    return (mapping or None), notes


_WIDTH = {"BININT1": 1, "BININT2": 2, "BININT": 4}


def patch(data, mapping):
    """Rewrite identifiers in the pickle in place -- same byte widths, so the
    memo table and every offset stay valid."""
    by_serial = {}
    for (fn, ver, ser), tgt in mapping.items():
        by_serial.setdefault((ver, ser), set()).add(tgt)

    ops = list(pickletools.genops(io.BytesIO(data)))
    out = bytearray(data)
    done = skipped = 0

    for i, (op, arg, pos) in enumerate(ops):
        if op.name != "BININT" or i + 2 >= len(ops):
            continue
        sop, sarg, spos = ops[i + 1]
        if ops[i + 2][0].name != "TUPLE3" or sop.name not in _WIDTH:
            continue
        targets = by_serial.get((arg, sarg))
        if not targets:
            continue
        if len(targets) != 1:
            skipped += 1  # same identifier means two things; refuse to guess
            continue
        newver, newser = next(iter(targets))
        width = _WIDTH[sop.name]
        if not 0 <= newser < (1 << (8 * width)):
            skipped += 1  # would need a wider opcode; never resize the stream
            continue
        out[pos + 1:pos + 5] = struct.pack("<i", newver)
        out[spos + 1:spos + 1 + width] = newser.to_bytes(width, "little")
        done += 1

    assert len(out) == len(data)
    return bytes(out), done, skipped


# --------------------------------------------------------------------------
# backups
# --------------------------------------------------------------------------

def label_for(path):
    """A backup subfolder name that stays unique across similar paths.

    Two installs both ending in \\game\\saves would otherwise collide and one
    would silently overwrite the other.
    """
    parts = [p for p in os.path.normpath(path).replace("\\", "/").split("/") if p and not p.endswith(":")]
    return "-".join(parts[-3:]) or "saves"


def backup(primary, mirrors, tag):
    dest = os.path.join(ROOT, "_save_backup_%s_%s" % (time.strftime("%Y%m%d-%H%M%S"), tag))
    used, manifest, n = {}, [], 0
    for src in [primary] + mirrors:
        label = label_for(src)
        if label in used:  # last-ditch guard; label_for should prevent this
            used[label] += 1
            label = "%s-%d" % (label, used[label])
        else:
            used[label] = 1
        d = os.path.join(dest, label)
        os.makedirs(d, exist_ok=True)
        for f in glob.glob(os.path.join(src, "*")):
            if os.path.isfile(f):
                shutil.copy2(f, d)
                n += 1
        manifest.append("%s\n    came from: %s\n" % (label, src))

    with open(os.path.join(dest, "WHERE.txt"), "w", encoding="utf-8") as f:
        f.write("Backup taken %s\n\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("To restore, copy a subfolder's files back into the folder it came from.\n\n")
        f.write("\n".join(manifest))

    print("  backed up %d files into %d folders -> %s" % (n, len(manifest), dim(dest)))
    return dest


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def read_saves(primary):
    out = []
    for p in slots(primary):
        try:
            out.append(Save(p))
        except Exception as e:
            print("  %-22s %s" % (os.path.basename(p), bad("unreadable: %s" % e)))
    return out


def compare(primary, mirrors):
    """Report which mirrors differ from the live folder. Returns files differing."""
    import hashlib

    def h(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()

    wanted = {os.path.basename(f): f for f in payload(primary)}
    total = 0
    for m in mirrors:
        diff = [
            n for n, src in wanted.items()
            if not os.path.exists(os.path.join(m, n)) or h(os.path.join(m, n)) != h(src)
        ]
        total += len(diff)
        tag = dim(" (Steam Cloud)") if is_steam(m) else ""
        print("  %-58s %s%s" % (m, ok("in sync") if not diff else warn("%d differ" % len(diff)), tag))
    return total


def cmd_status(primary, mirrors, gamedir, script, args):
    head("Installed build")
    print("  %s  %s" % (gamedir, dim("script_version " + script_version(gamedir))))

    head("Save locations")
    print("  %s  %s" % (ok("live  "), primary))
    for m in mirrors:
        print("  %s  %s%s" % (dim("mirror"), m, dim("  <- Steam Cloud syncs this") if is_steam(m) else ""))

    head("Saves")
    saves = read_saves(primary)
    broken = []
    for s in saves:
        st = s.status(script)
        if st["loadable"]:
            note = "resume %s, rollback %d/%d" % (s.where(script), st["depth"], st["total"])
        else:
            note = "dead statement ids"
            broken.append(s)
        print("  %s %-22s v%-7s %s" % (ok("OK    ") if st["loadable"] else bad("BROKEN"),
                                       s.name, s.version, dim(note)))

    head("Signatures")
    token = Token()
    if not token.ecdsa:
        print("  " + warn("ecdsa unavailable -- run savefix.cmd, or: pip install ecdsa"))
    elif not token.usable:
        print("  " + dim("no local signing key; this game does not sign saves"))
    else:
        n = sum(1 for s in saves if not token.valid(s.members["log"], s.members["signatures"]))
        print("  " + (ok("all %d valid" % len(saves)) if not n else bad("%d of %d invalid" % (n, len(saves)))))

    head("Mirrors")
    stale = compare(primary, mirrors) if mirrors else 0
    if not mirrors:
        print("  " + dim("none"))

    head("What to do")
    if broken:
        print("  %d save(s) need repair -> %s" % (len(broken), c("savefix fix", "1")))
    if stale:
        print("  %d file(s) differ between locations -> %s" % (stale, c("savefix sync", "1")))
    if not broken and not stale:
        print("  " + ok("nothing to do -- everything is healthy and in sync"))
    return 0


def cmd_fix(primary, mirrors, gamedir, script, args):
    dry = "--dry-run" in args
    todo = [s for s in read_saves(primary) if not s.status(script)["loadable"]]
    if not todo:
        print("\n" + ok("Every save already loads in this build. Nothing to repair."))
        return 0

    token = Token()
    if not token.ecdsa:
        die("the ecdsa module is required to re-sign repaired saves.\n"
            "       Run savefix.cmd instead of savefix.py, or: pip install ecdsa")

    print("\n%d save(s) need repair." % len(todo))
    if not dry:
        head("Backup")
        backup(primary, mirrors, "prefix")

    head("Repair")
    fixed = failed = 0
    for s in todo:
        print("\n  %s %s" % (c(s.name, "1"), dim("(v%s)" % s.version)))
        mapping, notes = plan(s, script)
        for n in notes:
            print("     " + dim(n))
        if not mapping:
            print("     " + bad("skipped"))
            failed += 1
            continue

        data, done, skipped = patch(s.members["log"], mapping)
        print("     rewrote %d identifiers%s" % (done, dim(" (%d skipped)" % skipped) if skipped else ""))
        if dry:
            print("     " + dim("dry run, not written"))
            fixed += 1
            continue

        s.write(data, token.sign(data) if token.usable else None)
        st = Save(s.path).status(script)
        if st["loadable"]:
            print("     " + ok("repaired, verified loadable (rollback %d/%d)" % (st["depth"], st["total"])))
            fixed += 1
        else:
            print("     " + bad("still not loadable -- restore from the backup"))
            failed += 1

    head("Result")
    print("  %s repaired, %s skipped" % (ok(str(fixed)), (bad if failed else dim)(str(failed))))
    if fixed and not dry:
        print("  " + dim("run 'savefix sync' to copy these to every location"))
    return 1 if failed else 0


def cmd_sync(primary, mirrors, gamedir, script, args):
    dry = "--dry-run" in args
    if not mirrors:
        print("\n" + dim("no mirror locations found; nothing to sync"))
        return 0

    broken = [s.name for s in read_saves(primary) if not s.status(script)["loadable"]]
    if broken:
        print("\n" + warn("These live saves are broken and would be copied as-is:"))
        for n in broken:
            print("    " + n)
        print("  " + dim("run 'savefix fix' first if you want them repaired"))

    files = payload(primary)
    if not dry:
        head("Backup")
        backup(primary, mirrors, "presync")

    head("Copy")
    for m in mirrors:
        if dry:
            print("  %-58s %s" % (m, dim("would receive %d files" % len(files))))
            continue
        os.makedirs(m, exist_ok=True)
        for f in files:
            shutil.copy2(f, os.path.join(m, os.path.basename(f)))
        print("  %-58s %s" % (m, ok("%d files" % len(files))))
    if dry:
        return 0

    head("Verify")
    stale = compare(primary, mirrors)
    print("\n  " + (ok("all locations identical") if not stale else bad("%d file(s) still differ" % stale)))
    return 1 if stale else 0


def cmd_backup(primary, mirrors, gamedir, script, args):
    head("Backup")
    backup(primary, mirrors, "manual")
    return 0


COMMANDS = {
    "status": cmd_status,
    "fix": cmd_fix,
    "sync": cmd_sync,
    "backup": cmd_backup,
}


def main(argv):
    args = argv[1:]
    if any(a in ("-h", "--help", "help", "/?") for a in args):
        print(__doc__)
        return 0

    cmd = "status"
    for a in args:
        if not a.startswith("-"):
            cmd, args = a, [x for x in args if x is not a]
            break
    if cmd not in COMMANDS:
        print(__doc__)
        die("unknown command: %s" % cmd)

    if cmd != "status":
        print(dim("Close the game before writing saves, or it may overwrite them."))
    print(c("CSE save fixer", "1;36"))

    primary, mirrors = find_locations()
    gamedir = pick_gamedir()
    return COMMANDS[cmd](primary, mirrors, gamedir, Script(gamedir), args)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print("\naborted")
        sys.exit(130)
