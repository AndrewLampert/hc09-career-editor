"""
Find what the editor needs on this computer without asking: RPCS3's career saves and the game's files.

Standard library only, read-only. RPCS3 keeps the saves in <rpcs3>/dev_hdd0/home/<user>/savedata/<GAMEID>-CAREER-<NAME>/USR-DATA and
the folder each installed game was added from in <rpcs3>/config/games.yml, so from any one save the game's own files
(PS3_GAME/USRDIR/qkl_boot.ast and qkl_fe2ig.ast) can be found as well.
"""
import glob
import os
import re
import time

GAME_ID = "BLUS30128"                                   # NFL Head Coach 09 (USA)
GAME_FILES = ("qkl_boot.ast", "qkl_fe2ig.ast")


def common_rpcs3_dirs():
    """Places RPCS3 is usually found (only those that exist)."""
    home = os.path.expanduser("~")
    cands = []
    for var in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(var):
            cands.append(os.path.join(os.environ[var], "rpcs3"))
    cands += [os.path.join(home, ".config", "rpcs3"), os.path.join(home, ".var", "app", "net.rpcs3.RPCS3", "config", "rpcs3"),
              os.path.join(home, "Library", "Application Support", "rpcs3"), r"C:\rpcs3", r"C:\Emulators\rpcs3",
              os.path.join(home, "rpcs3"), os.path.join(home, "Documents", "rpcs3"), os.path.join(home, "Downloads", "rpcs3")]
    return [c for c in cands if os.path.isdir(os.path.join(c, "dev_hdd0"))]


def search_rpcs3_dirs(roots, max_depth=4, budget=3.0):
    """RPCS3 folders (those holding dev_hdd0) found by looking inside the given folders a few levels down, for at most `budget`
    seconds. This is how an install in a folder of the user's choosing (say C:\\Emulators\\Rpcs3\\rpcs3-v0.0.32-...) is found."""
    found, start = [], time.time()
    for root in roots:
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip("\\/").count(os.sep)
        for cur, dirs, _files in os.walk(root):
            if time.time() - start > budget:
                return found
            if "dev_hdd0" in dirs:
                found.append(cur)
                dirs[:] = []
                continue
            if cur.count(os.sep) - base_depth >= max_depth:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("node_modules", "windows", "$recycle.bin", "system volume information")]
    return found


def rpcs3_dir_of(path):
    """The RPCS3 folder a save (or savedata folder) lives in, or None: the folder that has dev_hdd0 as a child on the way up."""
    cur = os.path.abspath(path)
    for _ in range(8):
        parent = os.path.dirname(cur)
        if os.path.basename(cur).lower() == "dev_hdd0":
            return parent
        if parent == cur:
            return None
        cur = parent
    return None


def savedata_roots(rpcs3_dirs):
    """Every savedata folder under the given RPCS3 folders (one per user: dev_hdd0/home/<user>/savedata)."""
    out = []
    for d in rpcs3_dirs:
        for p in glob.glob(os.path.join(d, "dev_hdd0", "home", "*", "savedata")):
            if os.path.isdir(p) and p not in out:
                out.append(p)
    return out


def list_saves(roots, game_id=GAME_ID):
    """The career saves in the given savedata folders, newest first: [{name, folder, path (the USR-DATA file), mtime, size, root}].
    Profile saves and other games' saves are left out."""
    out, seen = [], set()
    for root in roots:
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for folder in names:
            prefix = f"{game_id}-CAREER-"
            if not folder.upper().startswith(prefix):
                continue
            path = os.path.join(root, folder, "USR-DATA")
            try:
                st = os.stat(path)
            except OSError:
                continue
            if os.path.normcase(os.path.abspath(path)) in seen:
                continue
            seen.add(os.path.normcase(os.path.abspath(path)))
            out.append({"name": folder[len(prefix):] or folder, "folder": folder, "path": path, "mtime": st.st_mtime, "size": st.st_size, "root": root})
    return sorted(out, key=lambda s: -s["mtime"])


def game_dir_from_rpcs3(rpcs3_dir, game_id=GAME_ID):
    """The folder RPCS3 booted the game from, read from config/games.yml (a line "BLUS30128: <path>"), or None. A disc image
    (an .iso) is not a folder, so it is skipped."""
    try:
        with open(os.path.join(rpcs3_dir, "config", "games.yml"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(rf"^\s*{re.escape(game_id)}\s*:\s*(.+?)\s*$", text, re.M)
    if not m:
        return None
    path = m.group(1).strip().strip("'\"")
    path = os.path.normpath(path)
    return path if os.path.isdir(path) else None


def find_game_files(rpcs3_dirs, game_id=GAME_ID):
    """{"qkl_boot.ast": path, "qkl_fe2ig.ast": path} for the files found in the game folders of the given RPCS3 installs."""
    out = {}
    for d in rpcs3_dirs:
        game = game_dir_from_rpcs3(d, game_id)
        if not game:
            continue
        for name in GAME_FILES:
            for sub in (("PS3_GAME", "USRDIR"), ("USRDIR",), ()):
                p = os.path.join(game, *sub, name)
                if os.path.isfile(p):
                    out.setdefault(name, p)
                    break
    return out


def candidate_rpcs3_dirs(recent_paths=(), extra_dirs=(), search_roots=(), search_budget=3.0):
    """RPCS3 folders to look at, best first: the ones the recent saves live in, the ones the user added, the usual places, and (only
    if none of those turned up) a bounded search of search_roots."""
    out = []
    for p in list(recent_paths) + list(extra_dirs):
        d = p if os.path.isdir(os.path.join(p, "dev_hdd0")) else rpcs3_dir_of(p)     # the RPCS3 folder itself, or something inside it
        if d and d not in out and os.path.isdir(d):
            out.append(d)
    for d in common_rpcs3_dirs():
        if d not in out:
            out.append(d)
    if not out:
        out = search_rpcs3_dirs(search_roots, budget=search_budget)
    return out
