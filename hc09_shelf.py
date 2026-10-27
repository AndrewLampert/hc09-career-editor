"""
The save shelf: career saves moved out of the game's save folder (and back), or copied, into a folder of your own, so the game's list of saves (it shows 10) is only as long as you want
and any number of saves and backups can wait on the shelf.

A save is a folder (RPCS3: savedata/BLUS30128-CAREER-<NAME> with USR-DATA, PARAM.SFO, ICON0.PNG; the PC versions: a folder with the save file in it). A shelved save is that folder, kept
under its own name (PARAM.SFO holds the folder's name, so it is never renamed), inside a wrapper folder that holds a small shelf.json (where it came from). The wrapper's name is the label
you see and can be anything; the shelf can have folders inside folders:

    <shelf>/Dynasty 2008/Bills week 3 2026-10-27 15-32/shelf.json
                                                       BLUS30128-CAREER-BILLS/USR-DATA ...

Moving is a rename when the shelf is on the same drive; otherwise the folder is copied, every file is checked (size and checksum), and only then is the original taken away. A failed check
leaves the original where it was. Nothing of yours is ever deleted from the shelf by this module (only the emptied wrapper of a save that was brought back).

Xenia saves are not moved: Xenia keeps a header file for each package in a folder of its own, so moving the package alone would leave a broken entry. No Tk here.
"""
import hashlib
import json
import os
import re
import shutil
import time
import uuid

META = "shelf.json"
TEMP_PREFIX = ".hc09-shelf-"             # the temporary folder of a copy that is being checked
VERSION = 1
MOVABLE = ("rpcs3", "pcport")            # platforms whose save is exactly one folder
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class ShelfError(Exception):
    """Something the shelf will not do (said in words for the person using the editor)."""


def default_shelf_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "hc09-save-shelf")


def clean_name(name, what="name"):
    """A folder or label name that is safe as a single path component on Windows and elsewhere."""
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(name or "")).strip().strip(".")
    n = re.sub(r"\s+", " ", n)
    if not n:
        raise ShelfError(f"The {what} is empty.")
    if n.lower() in _RESERVED:
        raise ShelfError(f"'{n}' cannot be used as a {what}.")
    return n[:80].rstrip(". ")


def fingerprint(folder):
    """{relative path: (size, sha256)} of every file below a folder."""
    out = {}
    for cur, _dirs, files in os.walk(folder):
        for f in files:
            p = os.path.join(cur, f)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
            out[os.path.relpath(p, folder).replace(os.sep, "/")] = (os.path.getsize(p), h.hexdigest())
    return out


def inside(path, root):
    """Is `path` below (or the same as) the folder `root`?"""
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    a, b = (x if x.endswith(os.sep) else x + os.sep for x in (a, b))          # a filesystem root (C:\ or /) already ends in a separator
    return a.startswith(b)


def in_entry(path, root):
    """Is `path` inside a SHELVED SAVE of the shelf at `root` (a folder with a shelf.json between the path and the shelf's top)? Only those are not saves of the game: a shelf folder may sit
    above or beside live save folders, whose saves must stay listed."""
    if not inside(path, root):
        return False
    top = os.path.normcase(os.path.abspath(root))
    cur = os.path.dirname(os.path.abspath(path))
    while os.path.normcase(cur) != top and len(cur) > len(top):
        if os.path.isfile(os.path.join(cur, META)):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return False


def _unique_dir(parent, label):
    """parent/label, or parent/label (2), (3)... when that exists."""
    path = os.path.join(parent, label)
    n = 2
    while os.path.exists(path):
        path = os.path.join(parent, f"{label} ({n})")
        n += 1
    return path


def move_folder(src, dst, copy=False):
    """Move (or, with copy=True, copy) the folder src to the not yet existing dst. Same drive: one rename. Otherwise: copy next to the destination, check every file against the original,
    rename into place, and only then take the original away. Raises ShelfError and leaves src as it was if anything fails."""
    if os.path.exists(dst):
        raise ShelfError(f"{dst} already exists.")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not copy:
        try:
            os.rename(src, dst)
            return
        except OSError:
            pass                                                   # another drive (or a locked file): copy, check, then remove
    # a temporary folder of this operation's own (never an existing path: the destination may be the game's save folder, which can hold anything), named so that no save list picks it up
    part = os.path.join(os.path.dirname(dst), f"{TEMP_PREFIX}{uuid.uuid4().hex[:10]}-{os.path.basename(dst)}")
    try:
        shutil.copytree(src, part)
        if fingerprint(src) != fingerprint(part):
            raise ShelfError("The copy does not match the original, so nothing was moved.")
        os.rename(part, dst)
    except ShelfError:
        shutil.rmtree(part, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(part, ignore_errors=True)
        raise ShelfError(f"The folder could not be copied: {e}")
    if not copy:
        try:
            shutil.rmtree(src)
        except OSError as e:
            raise ShelfError(f"The save was copied to the new place, but the original could not be removed ({e}). Both exist now; remove the original by hand.")


class Shelf:
    def __init__(self, root):
        self.root = os.path.abspath(root)

    # ---- the tree of folders and shelved saves
    def _abs(self, rel):
        rel = (rel or "").replace("\\", "/").strip("/")
        parts = [p for p in rel.split("/") if p]
        if any(p in (".", "..") for p in parts):
            raise ShelfError("That folder is not inside the shelf.")
        return os.path.join(self.root, *parts)

    def is_entry(self, path):
        return os.path.isfile(os.path.join(path, META))

    def read_meta(self, path):
        try:
            with open(os.path.join(path, META), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def entry(self, path):
        """The shelved save in the wrapper folder `path`, or None."""
        meta = self.read_meta(path)
        if not meta or not meta.get("folder"):
            return None
        save_dir = os.path.join(path, meta["folder"])
        if not os.path.isdir(save_dir):
            return None
        size, newest = 0, 0.0
        for cur, _d, files in os.walk(save_dir):
            for f in files:
                try:
                    st = os.stat(os.path.join(cur, f))
                except OSError:
                    continue
                size += st.st_size
                newest = max(newest, st.st_mtime)
        rel = os.path.relpath(path, self.root).replace(os.sep, "/")
        return {"label": os.path.basename(path), "path": path, "rel": rel, "folder_rel": os.path.dirname(rel).replace("\\", "/") if "/" in rel else "", "save_dir": save_dir, "meta": meta,
                "size": size, "mtime": newest or meta.get("source_mtime", 0), "shelved_at": meta.get("shelved_at", 0)}

    def folders(self, rel=""):
        """The sub folders (not shelved saves) directly inside a shelf folder, by name."""
        base = self._abs(rel)
        if not os.path.isdir(base):
            return []
        return sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)) and not self.is_entry(os.path.join(base, n)) and not n.startswith(TEMP_PREFIX))

    def entries(self, rel=""):
        """The shelved saves directly inside a shelf folder."""
        base = self._abs(rel)
        if not os.path.isdir(base):
            return []
        out = []
        for n in sorted(os.listdir(base), key=str.lower):
            e = self.entry(os.path.join(base, n)) if os.path.isdir(os.path.join(base, n)) else None
            if e:
                out.append(e)
        return out

    def walk(self):
        """Every folder (relative path) and shelved save of the shelf: ([folder rel paths], [entries])."""
        folders, entries = [], []

        def go(rel):
            entries.extend(self.entries(rel))
            for n in self.folders(rel):
                sub = f"{rel}/{n}" if rel else n
                folders.append(sub)
                go(sub)
        if os.path.isdir(self.root):
            go("")
        return folders, entries

    # ---- folders
    def new_folder(self, rel, name):
        name = clean_name(name, "folder name")
        path = os.path.join(self._abs(rel), name)
        if os.path.exists(path):
            raise ShelfError(f"There is already a folder or save called '{name}' there.")
        os.makedirs(path)
        return f"{rel.strip('/')}/{name}".strip("/")

    def rename(self, rel, new_name):
        """Rename a shelf folder or a shelved save's label (the save folder inside keeps its name)."""
        path = self._abs(rel)
        if path == self.root or not os.path.isdir(path):
            raise ShelfError("Nothing to rename.")
        new_name = clean_name(new_name, "name")
        dst = os.path.join(os.path.dirname(path), new_name)
        if os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(path):
            raise ShelfError(f"There is already something called '{new_name}' there.")
        os.rename(path, dst)
        return os.path.relpath(dst, self.root).replace(os.sep, "/")

    def move_within(self, rel, to_rel):
        """Move a shelf folder or a shelved save into another shelf folder ('' = the top)."""
        src = self._abs(rel)
        dst_dir = self._abs(to_rel)
        if src == self.root or not os.path.isdir(src):
            raise ShelfError("Nothing to move.")
        if not os.path.isdir(dst_dir):
            raise ShelfError("That folder does not exist.")
        if os.path.normcase(dst_dir + os.sep).startswith(os.path.normcase(src + os.sep)):
            raise ShelfError("A folder cannot go inside itself.")
        if self.is_entry(dst_dir):
            raise ShelfError("A shelved save cannot hold other things.")
        dst = os.path.join(dst_dir, os.path.basename(src))
        if os.path.exists(dst):
            raise ShelfError(f"There is already something called '{os.path.basename(src)}' in that folder.")
        os.rename(src, dst)
        return os.path.relpath(dst, self.root).replace(os.sep, "/")

    def set_note(self, rel, note):
        path = self._abs(rel)
        meta = self.read_meta(path)
        if meta is None:
            raise ShelfError("That is not a shelved save.")
        meta["note"] = str(note)[:500]
        with open(os.path.join(path, META), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)

    # ---- saves
    def put_away(self, save, folder_rel="", label=None, copy=False):
        """Put a save of the game on the shelf. save = {"path" (the save file), "platform" ("rpcs3" or "pcport"), "name"} as the editor's detection gives it. Moves the save's folder (or copies it
        with copy=True, a backup). Returns the shelved save."""
        platform = save.get("platform", "rpcs3")
        if platform not in MOVABLE:
            raise ShelfError("Xenia saves cannot be moved yet: Xenia keeps a header file for each save in another folder, and moving the save alone would break it.")
        src = os.path.dirname(os.path.abspath(save["path"]))
        if not os.path.isdir(src):
            raise ShelfError("The save is not there any more.")
        if inside(src, self.root):
            raise ShelfError("That save is already inside the shelf.")
        if inside(self.root, os.path.dirname(src)):
            raise ShelfError("The shelf is inside the game's save folder, where the game and the editor would list the shelved saves as saves of the game; choose another shelf folder.")
        stamp = time.strftime("%Y-%m-%d %H-%M")
        name = save.get("name") or os.path.basename(src)
        label = clean_name(label, "label") if label else clean_name(f"{name} {stamp}" if copy else name, "label")
        parent = self._abs(folder_rel)
        os.makedirs(parent, exist_ok=True)
        wrapper = _unique_dir(parent, label)
        os.makedirs(wrapper)
        meta = {"version": VERSION, "platform": platform, "root": os.path.dirname(src), "folder": os.path.basename(src), "name": name, "shelved_at": time.time(),
                "source_mtime": self._newest(src), "copy": bool(copy), "note": ""}
        meta_path = os.path.join(wrapper, META)
        try:
            with open(meta_path, "w", encoding="utf-8") as f:                # first, so a save on the shelf always says where it came from
                json.dump(meta, f, indent=1)
            move_folder(src, os.path.join(wrapper, os.path.basename(src)), copy=copy)
        except Exception:
            if not os.path.exists(os.path.join(wrapper, os.path.basename(src))):
                try:
                    os.remove(meta_path)
                    os.rmdir(wrapper)                                       # the wrapper and note made for nothing
                except OSError:
                    pass
            raise
        return self.entry(wrapper)

    @staticmethod
    def _newest(folder):
        newest = 0.0
        for cur, _d, files in os.walk(folder):
            for f in files:
                try:
                    newest = max(newest, os.stat(os.path.join(cur, f)).st_mtime)
                except OSError:
                    pass
        return newest

    def bring_back(self, entry, target_root=None, copy=False, replace=False, game_save=None):
        """Put a shelved save back into the game: into target_root (default: the folder it came from). Moves it (it leaves the shelf) or copies it (it stays: a restore of a backup).
        If the game already has a save of that name the call refuses, unless replace=True: then the game's save is first put on the shelf (next to this one, labelled 'replaced') and
        nothing is lost. game_save = the detection's dict of that save in the game (needed for replace). Returns the path of the save file in the game."""
        meta = entry["meta"]
        if meta.get("platform") not in MOVABLE:
            raise ShelfError("That save cannot be put back by the shelf.")
        root = os.path.abspath(target_root or meta["root"])
        if not os.path.isdir(root):
            raise ShelfError(f"The folder it came from is not there any more ({root}). Choose where to put it.")
        dst = os.path.join(root, meta["folder"])
        if os.path.exists(dst):
            if not replace:
                raise ShelfError(f"The game already has a save called {meta['folder']}. Put that one on the shelf first, or use Replace (it is shelved, not lost).")
            if not game_save:
                raise ShelfError("The save in the game was not found, so it cannot be shelved before replacing it.")
            self.put_away(game_save, folder_rel=entry["folder_rel"], label=f"{meta.get('name') or meta['folder']} replaced {time.strftime('%Y-%m-%d %H-%M')}")
        move_folder(entry["save_dir"], dst, copy=copy)
        if not copy:
            self._remove_empty_wrapper(entry["path"])
        return os.path.join(dst, self._save_file_name(dst, meta))

    @staticmethod
    def _save_file_name(folder, meta):
        for name in ("USR-DATA", meta.get("folder", "")):
            if name and os.path.isfile(os.path.join(folder, name)):
                return name
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        return max(files, key=lambda f: os.path.getsize(os.path.join(folder, f)), default="")

    def _remove_empty_wrapper(self, wrapper):
        """After a save left the shelf the wrapper only holds shelf.json: that is removed with its empty folder (the wrapper held nothing else)."""
        left = [n for n in os.listdir(wrapper) if n != META]
        if not left:
            try:
                os.remove(os.path.join(wrapper, META))
                os.rmdir(wrapper)
            except OSError:
                pass
