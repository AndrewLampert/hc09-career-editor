"""
Find what the editor needs on this computer without asking: RPCS3's career saves and the game's files, Xenia's saves and the saves of the PC versions of the Xbox 360 game (see the sections at the end).

Standard library only, read-only. RPCS3 keeps the saves in <rpcs3>/dev_hdd0/home/<user>/savedata/<GAMEID>-CAREER-<NAME>/USR-DATA and
the folder each installed game was added from in <rpcs3>/config/games.yml, so from any one save the game's own files
(PS3_GAME/USRDIR/qkl_boot.ast and qkl_fe2ig.ast) can be found as well.
"""
import glob
import os
import re
import subprocess
import time

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)       # the editor runs under pythonw: a console program started without this opens a black window for as long as it runs (0 off Windows)
GAME_ID = "BLUS30128"                                   # NFL Head Coach 09 (USA)
GAME_FILES = ("qkl_boot.ast", "qkl_fe2ig.ast")


def emulator_search_roots():
    """The folders a search for a portable RPCS3 or Xenia looks in: the editor's Search this computer and Check My Save use this one list."""
    home = os.path.expanduser("~")
    return [r"C:\Emulators", r"C:\Games", os.path.join(home, "Documents"), os.path.join(home, "Desktop"), os.path.join(home, "Downloads")]


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
    # A standard RPCS3 install may exist in AppData while the user's actual
    # portable emulator (and saves) lives elsewhere, e.g. under C:\\Emulators.
    # Search the bounded roots as well; do not skip them just because another
    # RPCS3 installation was found.
    for found in search_rpcs3_dirs(search_roots, budget=search_budget):
        if found not in out:
            out.append(found)
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Xenia (Xbox 360). WRITTEN FROM WHAT XENIA IS KNOWN TO DO, NOT YET CHECKED AGAINST A REAL INSTALL: if someone's folders differ, change the constants below (and, if the shape
# of the folders is different, xenia_title_folders / _save_files). Everything else (finding the files, telling a career from a profile, pairing them) follows from these.
#
# Xenia keeps a game's saves in <xenia folder>/content/<profile id>/<title id>/<content type>/<package>/<files>. The save file is the game's own MC02 file (see the bridge): the
# letters MC02, a 28-byte header whose 32-bit big-endian value at offset 8 is the length of a metadata block, then the database, which starts with "DB". A career has 208 tables,
# a profile 43 (the number of tables is the 32-bit big-endian value 0x10 bytes into the database), which is how the two are told apart without relying on any file name.
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
XENIA_TITLE_ID = "45410841"                     # NFL Head Coach 09 (Xbox 360)
XENIA_CONTENT_DIR = "content"                   # the folder inside Xenia's folder that holds the profiles' content
XENIA_MAX_DEPTH = 5                             # how many levels below the title folder a save file may sit
MC02_MAGIC = b"MC02"
MC02_HEADER_SIZE = 28
TDB_SIGNATURE = b"DB\x00\x08\x01\x00\x00\x00"   # how the databases of this game start
CAREER_MIN_TABLES = 150                         # 208 in a career save
PROFILE_MIN_TABLES = 30                         # 43 in a profile save; a roster save has only 16 (it is neither a career nor a profile)
PROFILE_MAX_TABLES = 80
MIN_SAVE_SIZE = 50 * 1024                       # smaller files are not saves (headers, thumbnails)


def common_xenia_dirs():
    """Places Xenia's own folder (the one that holds `content`) is usually found, only those that exist."""
    home = os.path.expanduser("~")
    cands = [os.path.join(home, "Documents", "Xenia"), os.path.join(home, "Documents", "xenia"), os.path.join(home, "Xenia"), os.path.join(home, "xenia"),
             r"C:\Xenia", r"C:\xenia", r"C:\Emulators\Xenia", r"C:\Emulators\xenia", os.path.join(home, ".local", "share", "xenia"),
             os.path.join(home, ".local", "share", "Xenia")]
    for var in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(var):
            cands.append(os.path.join(os.environ[var], "Xenia"))
    parents = [home, os.path.join(home, "Documents"), os.path.join(home, "Desktop"), os.path.join(home, "Downloads"), "C:\\", r"C:\Emulators", r"C:\Games", "D:\\", r"D:\Emulators", r"D:\Games"]
    cands += xenia_named_dirs(parents)
    out = []
    for c in cands:
        if os.path.isdir(os.path.join(c, XENIA_CONTENT_DIR)) and c not in out:
            out.append(c)
    return out


def xenia_named_dirs(parents):
    """Folders with "xenia" in their name (xenia_canary, Xenia Edge, xenia-canary-windows ...) directly in the given folders and one level inside them (a portable copy is often
    unzipped into a folder inside another one). The caller keeps the ones that hold `content`."""
    out = []
    for parent in parents:
        try:
            names = sorted(os.listdir(parent))
        except OSError:
            continue
        for n in names:
            d = os.path.join(parent, n)
            if "xenia" in n.lower() and os.path.isdir(d):
                out.append(d)
                try:
                    out += [os.path.join(d, c) for c in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, c))]
                except OSError:
                    pass
    return out


_running_cache = [0.0, []]                         # [when it was asked, the answer]
RUNNING_CACHE_SECONDS = 10


def running_xenia_dirs():
    """The folders of Xenia programs (Canary, Edge) that are running now, asked of Windows: a portable Xenia keeps `content` next to its program, wherever that is. [] elsewhere or on
    any failure. The answer is kept for RUNNING_CACHE_SECONDS: asking starts tasklist (and PowerShell when a Xenia runs), and a list of saves is rebuilt many times."""
    if os.name != "nt":
        return []
    if time.time() - _running_cache[0] < RUNNING_CACHE_SECONDS:
        return list(_running_cache[1])
    dirs = _ask_running_xenia_dirs()
    _running_cache[0], _running_cache[1] = time.time(), list(dirs)
    return dirs


def _ask_running_xenia_dirs():
    try:                                 # a quick look first: PowerShell is slow to start and is only needed when something called xenia* runs
        listing = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW).stdout
        if not any(line.lower().startswith('"xenia') for line in listing.splitlines()):
            return []
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.Name -like 'xenia*' } | ForEach-Object { $_.Path }"],
                             capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    dirs = []
    for line in out.splitlines():
        line = line.strip()
        if line and os.path.isfile(line) and os.path.dirname(line) not in dirs:
            dirs.append(os.path.dirname(line))
    return dirs


def search_xenia_dirs(roots, max_depth=4, budget=3.0):
    """Xenia folders (those holding `content/<profile id>/<title id>`) found by looking inside the given folders a few levels down, for at most `budget` seconds."""
    found, start = [], time.time()
    for root in roots:
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip("\\/").count(os.sep)
        for cur, dirs, _files in os.walk(root):
            if time.time() - start > budget:
                return found
            if os.path.basename(cur).lower() == XENIA_CONTENT_DIR and xenia_title_folders(os.path.dirname(cur)):
                found.append(os.path.dirname(cur))
                dirs[:] = []
                continue
            if cur.count(os.sep) - base_depth >= max_depth:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("node_modules", "windows", "$recycle.bin", "system volume information")]
    return found


def xenia_dir_of(path):
    """The Xenia folder a save (or any path inside its content folder) lives in, or None: the parent of the `content` folder on the way up, when that content folder holds this game
    (content/<profile id>/<title id>): any other folder that happens to be called content (a download, a fix pack) is not Xenia's."""
    cur = os.path.abspath(path)
    for _ in range(12):
        parent = os.path.dirname(cur)
        if os.path.basename(cur).lower() == XENIA_CONTENT_DIR and xenia_title_folders(parent):
            return parent
        if parent == cur:
            return None
        cur = parent
    return None


def xenia_title_folders(xenia_dir):
    """The folders of this game inside a Xenia folder: content/<profile id>/<title id>."""
    return [p for p in glob.glob(os.path.join(xenia_dir, XENIA_CONTENT_DIR, "*", XENIA_TITLE_ID)) if os.path.isdir(p)]


def title_folder_of(path):
    """The title folder (.../content/<profile id>/<title id>) a path lies in, or None."""
    cur = os.path.abspath(path)
    for _ in range(12):
        if os.path.basename(cur).upper() == XENIA_TITLE_ID and os.path.basename(os.path.dirname(os.path.dirname(cur))).lower() == XENIA_CONTENT_DIR:
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return None


TDB_SEARCH_LIMIT = 64 << 20                      # how far into a file a database is looked for when the header does not point at it (a save is a few megabytes)


def _find_signature(f, limit=TDB_SEARCH_LIMIT, chunk=4 << 20):
    """The offset of the first TDB_SIGNATURE in an open file, looking at most `limit` bytes in, `chunk` bytes at a time (a large file is not read into memory); -1 when there is none."""
    f.seek(0)
    pos, tail, scanned = 0, b"", 0                  # pos: the file offset of the first byte of tail + the block read next
    keep = len(TDB_SIGNATURE) - 1
    while scanned < limit:
        block = f.read(chunk)
        if not block:
            return -1
        data = tail + block
        i = data.find(TDB_SIGNATURE)
        if i >= 0:
            return pos + i
        tail = data[-keep:]
        pos += len(data) - len(tail)
        scanned += len(block)
    return -1


def _db_start_in(f):
    """Database offset for a bare DB, an MC02 container, or a PS3 HC09 save header."""
    head = f.read(12)
    if head[:2] == b"DB":
        return 0
    if head[:4] == MC02_MAGIC and len(head) >= 12:
        start = MC02_HEADER_SIZE + int.from_bytes(head[8:12], "big")
        f.seek(start)
        if f.read(2) == b"DB":
            return start
        found = _find_signature(f)                  # tolerate an incorrect MC02 metadata length, as the converter does
        return found if found >= 0 else None
    # HC09's PS3 USR-DATA has a four-byte offset header. HC09Helper reads
    # uint32be(header) + 4 to locate the database; it is not encrypted in
    # RPCS3's savedata directory. Validate the full database signature before
    # accepting the offset so unrelated files are not misclassified.
    if len(head) >= 4:
        start = int.from_bytes(head[:4], "big") + 4
        if 0 < start < os.fstat(f.fileno()).st_size:
            f.seek(start)
            if f.read(len(TDB_SIGNATURE)) == TDB_SIGNATURE:
                return start
    return None


def mc02_db_start(path):
    """Where the database starts inside an MC02 Xbox 360/Xenia save; None otherwise."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != MC02_MAGIC:
                return None
            f.seek(0)
            return _db_start_in(f)
    except OSError:
        return None


def ps3_db_start(path):
    """Where the database starts inside an HC09 PS3 USR-DATA save; None otherwise."""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
            if len(head) != 4 or head == TDB_SIGNATURE[:4] or head == MC02_MAGIC:
                return None
            start = int.from_bytes(head, "big") + 4
            if start <= 4 or start >= os.fstat(f.fileno()).st_size:
                return None
            f.seek(start)
            return start if f.read(len(TDB_SIGNATURE)) == TDB_SIGNATURE else None
    except OSError:
        return None


def db_table_count(path):
    """The number of tables in a save's database (43 in a profile, 208 in a career), or None when it cannot be read. The file is opened once."""
    try:
        with open(path, "rb") as f:
            start = _db_start_in(f)
            if start is None:
                return None
            f.seek(start + 0x10)
            raw = f.read(4)
        return int.from_bytes(raw, "big") if len(raw) == 4 else None
    except OSError:
        return None


def classify_save(path):
    """("career" | "profile" | "other", table count): a career has 208 tables and a profile 43; anything else, a roster save (16 tables) for one, is "other"."""
    n = db_table_count(path)
    if n is None:
        return "other", None
    return ("career" if n >= CAREER_MIN_TABLES else "profile" if PROFILE_MIN_TABLES <= n <= PROFILE_MAX_TABLES else "other"), n


def is_xbox_save(path):
    """True for a save of the Xbox 360 game: one below a Xenia content folder or a PC version's saves folder, or one in the MC02 container those use (a PS3 save is a bare database). The game (Xenia,
    HC09 for PC) reads EVERY file next to the saves of a folder as a save and reports all of them as damaged when one is a copy, so nothing but the save may sit beside it."""
    if xenia_dir_of(path) or pcport_root_of(path):
        return True
    start = mc02_db_start(path)
    return start is not None and start > 0


def _save_files(title_folder):
    """Candidate save files below a title folder: files of a useful size (the type and package folders are not assumed); the editor's own backup folder and *.bak files are not saves."""
    base_depth = title_folder.rstrip("\\/").count(os.sep)
    for cur, dirs, files in os.walk(title_folder):
        dirs[:] = [d for d in dirs if d.lower() != BACKUP_DIR_NAME]
        if cur.count(os.sep) - base_depth >= XENIA_MAX_DEPTH:
            dirs[:] = []
        for name in files:
            if name.lower().endswith(".bak"):
                continue
            path = os.path.join(cur, name)
            try:
                if os.path.getsize(path) >= MIN_SAVE_SIZE:
                    yield path
            except OSError:
                continue


def list_xenia_saves(xenia_dirs):
    """Every save of this game in the given Xenia folders, newest first: [{name, path, mtime, size, root (the title folder), kind ("career" | "profile"), tables, xuid, package}].
    Files that are not saves (headers, other games' folders) are left out. The name is the package folder's (what the game or Xenia called the save), else the file's."""
    out, seen = [], set()
    for xd in xenia_dirs:
        for title in xenia_title_folders(xd):
            xuid = os.path.basename(os.path.dirname(title))
            for path in _save_files(title):
                key = os.path.normcase(os.path.abspath(path))
                if key in seen:
                    continue
                try:
                    st = os.stat(path)                                   # first: a save that Xenia replaces or deletes at this moment is left out, not an error
                except OSError:
                    continue
                kind, tables = classify_save(path)
                if kind == "other":
                    continue
                seen.add(key)
                rel = os.path.relpath(path, title).split(os.sep)
                package = rel[-2] if len(rel) >= 3 else ""             # <type>/<package>/<file>; a file straight in the type folder has no package folder
                shown = re.sub(r"^(CAREER|PROFILE)-", "", package, flags=re.I)                      # CAREER-ME is shown as ME, as the PS3 saves are
                out.append({"name": shown or package or os.path.splitext(os.path.basename(path))[0], "path": path, "mtime": st.st_mtime, "size": st.st_size, "root": title, "kind": kind,
                            "tables": tables, "xuid": xuid, "package": package})
    return sorted(out, key=lambda s: -s["mtime"])


def xenia_profiles_for(career_path):
    """The profile saves that go with a career save found by Xenia's layout: the ones in the same title folder, newest first; [] when the career is not inside a Xenia folder."""
    title = title_folder_of(career_path)
    if not title:
        return []
    xd = xenia_dir_of(title)
    if not xd:
        return []
    return [s["path"] for s in list_xenia_saves([xd]) if s["kind"] == "profile" and os.path.normcase(s["root"]) == os.path.normcase(title)]


def candidate_xenia_dirs(recent_paths=(), extra_dirs=(), search_roots=(), search_budget=3.0):
    """Xenia folders to look at, best first: the ones the recent saves live in, the ones the user added (the Xenia folder itself, its content folder, or anything inside), the usual
    places, a Xenia that is running now, and (only if none of those turned up) a bounded search of search_roots."""
    out = []

    def add(d):
        if d and os.path.isdir(d) and xenia_title_folders(d) and d not in out:
            out.append(d)

    for p in list(recent_paths):
        add(xenia_dir_of(p))
    for p in extra_dirs:
        add(p if os.path.isdir(os.path.join(p, XENIA_CONTENT_DIR)) else xenia_dir_of(p))
    if search_roots:                     # a search of the folders the user added is part of the search, and shares its time (it used to run on every call, 3 seconds for each folder)
        for d in search_xenia_dirs(list(extra_dirs), budget=search_budget):
            add(d)
    for d in common_xenia_dirs():
        add(d)
    for d in running_xenia_dirs():       # a portable Xenia that is running elsewhere is added even when other folders were found
        add(d)
    if not out:
        for d in search_xenia_dirs(search_roots, budget=search_budget):
            add(d)
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
# HC09 for PC: the Xbox 360 game recompiled to run natively on Windows (ibukun5588/nfl-head-coach-09-pc and tools81/nfl-head-coach-09-static-recomp). WRITTEN FROM THEIR README PAGES,
# NOT YET CHECKED AGAINST A REAL INSTALL: if the folders differ, change the constants below. The save itself is the same MC02 package as Xenia's (so classify_save works), but the
# folders around it are not Xenia's content/<profile id>/<title id>/<type>/ tree:
#   ibukun5588:  <Documents>\NFL Head Coach 09\Saves\<game version, 1.0 or 1.2>\<package>\<package>   (one folder per save, named CAREER-<name>, ROSTER-<name> or PROFILE-HeadCoach,
#                holding one file of the same name; a <name>.name file sits beside it; replaced saves are copied to Saves\Backups first, which is not a save)
#   tools81:     <install folder>\build\userdata\content\<type>\<package>\<package>   (type 00000001; HC27.exe, the game with today's rosters, keeps its own saves in build\userdata-hc27\content,
#                its README gives ...\content\00000001\CAREER-<name>\CAREER-<name>); the game reads the disc image named by IsoPath in <install folder>\hc09.ini while you play, so qkl_boot.ast
#                is not a loose file there (hc09_iso reads it out of the image)
# A package folder is therefore recognised by what is in it: a file of the same name as the folder that is a career or profile save.
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
PCPORT_DOCS_DIR = "NFL Head Coach 09"           # <Documents>\NFL Head Coach 09
PCPORT_SAVES_DIR = "Saves"
PCPORT_VERSIONS = ("1.0", "1.2")                # the game versions the ibukun5588 port keeps apart
PCPORT_MAX_DEPTH = 4                            # how many levels below a saves folder a package folder may sit
BACKUP_DIR_NAME = "hc09-editor-backups"         # where the editor keeps the copy it makes of an Xbox 360 save before writing it (see is_xbox_save)
PCPORT_SKIP_DIRS = {"backups", BACKUP_DIR_NAME}  # folders whose saves are old copies, not saves to open
TOOLS81_USERDATA = ("userdata", "userdata-hc27")                 # HC09.exe's saves and HC27.exe's
TOOLS81_INI = "hc09.ini"                                        # in the install folder: IsoPath=<the disc image>
PCPORT_INSTALL_DIRS = (r"C:\Games\HC09Recomp", r"C:\HC09Recomp", r"D:\Games\HC09Recomp")      # the tools81 README suggests C:\Games\HC09Recomp
PCPORT_PROGRAMS = ("hc09", "hc09-launcher", "hc27")  # process names (without .exe) of the PC versions (HC27.exe is the recompiled game with today's rosters): they rewrite the saves they have open


def documents_dirs():
    """The user's Documents folders that exist: the one Windows says (it may be inside OneDrive) and the usual ones."""
    home = os.path.expanduser("~")
    cands = []
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:          # CSIDL_PERSONAL = My Documents
                cands.append(buf.value)
        except (OSError, AttributeError, ImportError):
            pass
    cands += [os.path.join(home, "Documents")]
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(var):
            cands.append(os.path.join(os.environ[var], "Documents"))
    cands.append(os.path.join(home, "OneDrive", "Documents"))
    out = []
    for c in cands:
        if c and os.path.isdir(c) and os.path.normcase(c) not in [os.path.normcase(o) for o in out]:
            out.append(c)
    return out


def pcport_roots_in(path):
    """The folders to look for PC-version saves in, given a folder the user (or a recent save) points at: the saves folder itself, or a folder above it that holds it
    (the Documents folder, the NFL Head Coach 09 folder, a tools81 install folder). Nothing is guessed about other folders (a Xenia or RPCS3 folder gives none)."""
    if not path or not os.path.isdir(path):
        return []
    path = os.path.abspath(path)
    name = os.path.basename(path).lower()
    parent = os.path.basename(os.path.dirname(path)).lower()
    cands = []
    if name == PCPORT_SAVES_DIR.lower() or (name == "content" and parent in TOOLS81_USERDATA) or (name in PCPORT_VERSIONS and parent == PCPORT_SAVES_DIR.lower()):
        cands.append(path)
    cands += [os.path.join(path, PCPORT_SAVES_DIR), os.path.join(path, PCPORT_DOCS_DIR, PCPORT_SAVES_DIR)]
    for d in TOOLS81_USERDATA:
        cands += [os.path.join(path, "build", d, "content"), os.path.join(path, d, "content")]
    return [c for c in cands if os.path.isdir(c)]


def common_pcport_roots():
    """The usual places of the PC versions' saves that exist."""
    out = []
    for d in documents_dirs():
        out += pcport_roots_in(os.path.join(d, PCPORT_DOCS_DIR))
    for d in PCPORT_INSTALL_DIRS + (os.path.join(os.path.expanduser("~"), "HC09Recomp"),):
        out += pcport_roots_in(d)
    return out


def pcport_root_of(path):
    """The PC-version saves folder a save lies in (found by its shape on the way up), or None: <...>\\NFL Head Coach 09\\Saves, or <...>\\userdata\\content (userdata-hc27 for HC27.exe)."""
    cur = os.path.abspath(path)
    for _ in range(8):
        parent = os.path.dirname(cur)
        name, pname = os.path.basename(cur).lower(), os.path.basename(parent).lower()
        if name == PCPORT_SAVES_DIR.lower() and pname == PCPORT_DOCS_DIR.lower():
            return cur
        if name == "content" and pname in TOOLS81_USERDATA:
            return cur
        if parent == cur:
            return None
        cur = parent
    return None


def _pcport_package_files(root):
    """The files of a saves folder that sit in a folder of the same name (the PC versions' packages), of a useful size, never inside a Backups folder."""
    base_depth = root.rstrip("\\/").count(os.sep)
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in PCPORT_SKIP_DIRS]
        if cur.count(os.sep) - base_depth >= PCPORT_MAX_DEPTH:
            dirs[:] = []
        folder = os.path.basename(cur).lower()
        for name in files:
            if name.lower() != folder:
                continue
            path = os.path.join(cur, name)
            try:
                if os.path.getsize(path) >= MIN_SAVE_SIZE:
                    yield path
            except OSError:
                continue


def list_pcport_saves(roots):
    """Every career and profile save of the PC versions in the given saves folders, newest first: [{name, path, mtime, size, root, kind ("career" | "profile"), tables, package, version
    ("1.0" or "1.2" for the ibukun5588 port, else ""), variant ("HC27" for the saves of HC27.exe, else "")}]. Roster saves and anything that is not a save are left out."""
    out, seen = [], set()
    for root in roots:
        for path in _pcport_package_files(root):
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                continue
            try:
                st = os.stat(path)                                       # first: a save that is replaced or deleted at this moment is left out, not an error
            except OSError:
                continue
            kind, tables = classify_save(path)
            if kind == "other":
                continue
            seen.add(key)
            package = os.path.basename(os.path.dirname(path))
            group = os.path.basename(os.path.dirname(os.path.dirname(path)))
            shown = re.sub(r"^(CAREER|PROFILE)-", "", package, flags=re.I)
            out.append({"name": shown or package, "path": path, "mtime": st.st_mtime, "size": st.st_size, "root": os.path.dirname(os.path.dirname(path)), "kind": kind, "tables": tables,
                        "package": package, "version": group if group in PCPORT_VERSIONS else "", "variant": "HC27" if os.sep + "userdata-hc27" + os.sep in os.path.abspath(path).lower() + os.sep else ""})
    return sorted(out, key=lambda s: -s["mtime"])


def pcport_profiles_for(career_path):
    """The profile saves that go with a career save of a PC version: the ones in the same folder (the game version's folder), newest first; [] when the career is not in a PC version's
    saves folder."""
    if not pcport_root_of(career_path):
        return []
    group = os.path.dirname(os.path.dirname(os.path.abspath(career_path)))
    return [s["path"] for s in list_pcport_saves([group]) if s["kind"] == "profile"]


def recomp_install_of(path):
    """The install folder of a recompiled PC version (tools81) a path lies in: the nearest folder above it that holds hc09.ini, or None."""
    cur = os.path.abspath(path) if path else ""
    for _ in range(10):
        if not cur:
            return None
        if os.path.isfile(os.path.join(cur, TOOLS81_INI)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return None


def recomp_iso(install_dir):
    """The disc image a tools81 install plays from: IsoPath in its hc09.ini (any section, quotes allowed), when that file exists; else ""."""
    try:
        with open(os.path.join(install_dir, TOOLS81_INI), encoding="utf-8", errors="replace") as f:
            for line in f:
                key, sep, value = line.partition("=")
                if sep and key.strip().lower() == "isopath":
                    value = value.strip().strip("'\"")
                    iso = os.path.normpath(value if os.path.isabs(value) else os.path.join(install_dir, value))          # a relative path is relative to the install folder
                    return iso if os.path.isfile(iso) else ""
    except OSError:
        pass
    return ""


def find_recomp_isos(recent_paths=(), extra_dirs=()):
    """The disc images of the tools81 installs this computer has, best first: the install a recent save belongs to, the ones the user added (the install folder or anything inside), the usual places."""
    out = []

    def add(install):
        iso = recomp_iso(install) if install else ""
        if iso and os.path.normcase(iso) not in [os.path.normcase(o) for o in out]:
            out.append(iso)

    for p in list(recent_paths) + list(extra_dirs):
        add(recomp_install_of(p))
    for d in PCPORT_INSTALL_DIRS + (os.path.join(os.path.expanduser("~"), "HC09Recomp"),):
        add(d if os.path.isdir(d) else None)
    return out


PCPORT_SEARCH_SKIP = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin", "system volume information", "node_modules", ".git", "__pycache__"}


def pcport_search_places():
    """Where a search for a PC version of the game looks, as [(folder, how many levels down)]: the user's folder first (an install is often in it: C:\\Users\\<name>\\HC09Recomp\\build\\userdata-hc27\\content
    is four levels down), then the top of every drive (C:\\Games\\HC09Recomp\\build\\userdata-hc27\\content is five)."""
    places = [(os.path.expanduser("~"), 6)]
    if os.name == "nt":
        places += [(root, 5) for root in drive_roots()]
    return [p for p in places if os.path.isdir(p[0])]


def drive_roots():
    """The root of every local or removable drive (C:\\, D:\\ ... any letter): Windows is asked which drives there are (nothing is read from them); network and disc drives are left out (a disconnected
    one can stall a search) and so are the floppy letters A and B. If Windows cannot be asked, C to H that exist."""
    roots = []
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(2, 26):
            root = chr(65 + i) + ":\\"
            if mask & (1 << i) and ctypes.windll.kernel32.GetDriveTypeW(root) in (2, 3):      # 2 removable, 3 fixed
                roots.append(root)
    except (OSError, AttributeError, ImportError):
        roots = [d + ":\\" for d in "CDEFGH" if os.path.isdir(d + ":\\")]
    return roots


def search_pcport_roots(places, budget=20.0):
    """Saves folders of the PC versions (<install>\\build\\userdata[-hc27]\\content, or <Documents>\\NFL Head Coach 09\\Saves) found by looking inside [(folder, how many levels down)] for at most `budget`
    seconds, wherever the game was put. Returns (the folders found, True when the time ran out before every folder was looked at). Windows, Program Files, AppData and the like are not entered, nor
    are folders whose name starts with a dot (.cargo, .gradle) or a place that was walked already (the user's folder is not walked again when the drive it is on is). Each place gets an equal share
    of the time that is left, so a large first folder cannot use up the whole budget before the drives are looked at."""
    found, start, cut, walked = [], time.time(), False, []
    for i, (root, depth) in enumerate(places):
        if not os.path.isdir(root):
            continue
        now = time.time()
        limit = now + max(0.0, budget - (now - start)) / (len(places) - i)
        base = root.rstrip("\\/").count(os.sep)
        for cur, dirs, _files in os.walk(root):
            if time.time() >= limit:
                cut = True
                break
            name, parent = os.path.basename(cur).lower(), os.path.basename(os.path.dirname(cur)).lower()
            if (name == "content" and parent in TOOLS81_USERDATA) or (name == PCPORT_SAVES_DIR.lower() and parent == PCPORT_DOCS_DIR.lower()):
                if os.path.normcase(cur) not in [os.path.normcase(f) for f in found]:
                    found.append(cur)
                dirs[:] = []
                continue
            if cur.count(os.sep) - base >= depth:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if d.lower() not in PCPORT_SEARCH_SKIP and not d.startswith(".") and os.path.normcase(os.path.join(cur, d)) not in walked]
        walked.append(os.path.normcase(root))
    return found, cut


def candidate_pcport_roots(recent_paths=(), extra_dirs=()):
    """The saves folders of the PC versions to look at, best first: the ones the recent saves live in, the ones the user added (the saves folder or a folder that holds it), the usual
    places."""
    out = []

    def add(d):
        if d and os.path.isdir(d) and os.path.normcase(os.path.abspath(d)) not in [os.path.normcase(o) for o in out]:
            out.append(os.path.abspath(d))

    for p in recent_paths:
        add(pcport_root_of(p))
    for p in extra_dirs:
        for d in pcport_roots_in(p):
            add(d)
    for d in common_pcport_roots():
        add(d)
    return out
