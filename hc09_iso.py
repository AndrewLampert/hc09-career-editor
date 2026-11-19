"""Read files out of an Xbox 360 disc image (an .iso), read only: the editor needs the game's qkl_boot.ast, and the recompiled PC versions of the game (tools81/nfl-head-coach-09-static-recomp) read the game
from the disc image while you play, so the file is not lying loose in a folder. WRITTEN FROM THE FORMAT, NOT YET TRIED ON A REAL DISC IMAGE: if an image is refused, hc09_iso.describe() says what was found.

The image holds an XDVDFS ("GDF") file system: 2,048-byte sectors, the volume descriptor in sector 32 of the data partition, which starts at an offset that depends on the disc's layout (XGD1, XGD2, XGD3; a
plain image is 0). The descriptor starts with MICROSOFT*XBOX*MEDIA and names the root directory (its first sector and its size); a directory is a table of entries, a binary tree whose links are in units of
four bytes: left (2 bytes), right (2), first sector (4), size (4), attributes (1, 0x10 = directory), name length (1), the name; entries are padded to four bytes with 0xFF."""
import os
import struct

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
PARTITION_OFFSETS = (0x00000000, 0x0FD90000, 0x02080000, 0x18300000)        # plain image, XGD2 (the Xbox 360 discs of 2007 on), XGD3, XGD1
DIRECTORY = 0x10
CHUNK = 8 << 20
MAX_TABLE = 16 << 20                                           # a folder's table is a few kilobytes; more than this means the descriptor is damaged


def _partition(f):
    """The offset of the data partition of an open image: the first of PARTITION_OFFSETS whose sector 32 holds the descriptor, else None."""
    for off in PARTITION_OFFSETS:
        f.seek(off + 32 * SECTOR)
        if f.read(len(MAGIC)) == MAGIC:
            return off
    return None


def _root(f, off):
    f.seek(off + 32 * SECTOR + len(MAGIC))
    raw = f.read(8)
    if len(raw) < 8:
        raise ValueError("The disc image is cut short: it ends inside the volume descriptor.")
    return struct.unpack("<II", raw)


def _entries(table):
    """The entries of one directory table: [{name, sector, size, directory}] (every entry of the tree, in no particular order)."""
    out, stack, seen = [], [0], set()
    while stack:
        pos = stack.pop()
        if pos in seen or pos + 14 > len(table):
            continue
        seen.add(pos)
        left, right, sector, size, attr, name_len = struct.unpack_from("<HHIIBB", table, pos)
        if (sector == 0xFFFFFFFF and size == 0xFFFFFFFF) or name_len == 0 or pos + 14 + name_len > len(table):
            continue                                              # the 0xFF padding at the end of a table, or an empty directory (a leaf with both links 0xFFFF is a real entry: it has a sector and a size)
        out.append({"name": table[pos + 14: pos + 14 + name_len].decode("latin-1"), "sector": sector, "size": size, "directory": bool(attr & DIRECTORY)})
        for child in (left, right):
            if child not in (0, 0xFFFF):
                stack.append(child * 4)
    return out


def _table(f, off, sector, size):
    if size > MAX_TABLE:
        raise ValueError("The disc image looks damaged: a folder in it claims to be " + f"{size:,} bytes.")
    f.seek(off + sector * SECTOR)
    data = f.read(size)
    if len(data) < size:
        raise ValueError("The disc image is cut short: it ends inside a folder.")
    return data


def find(path, name):
    """(partition offset, sector, size) of a file in the image: name is a path inside it ("qkl_boot.ast", "folder/file"), compared without regard to case. Raises ValueError with the reason when the image
    is not an Xbox 360 disc image or the file is not in it."""
    with open(path, "rb") as f:
        off = _partition(f)
        if off is None:
            raise ValueError("This is not an Xbox 360 disc image the editor can read (no Xbox file system was found in it).")
        sector, size = _root(f, off)
        parts = [p for p in name.replace("\\", "/").split("/") if p]
        for i, part in enumerate(parts):
            table = _table(f, off, sector, size)
            hit = next((e for e in _entries(table) if e["name"].lower() == part.lower()), None)
            if hit is None:
                raise ValueError(f"{name} is not in the disc image.")
            if i == len(parts) - 1:
                if hit["directory"]:
                    raise ValueError(f"{name} is a folder, not a file.")
                return off, hit["sector"], hit["size"]
            if not hit["directory"]:
                raise ValueError(f"{part} is a file, not a folder.")
            sector, size = hit["sector"], hit["size"]
    raise ValueError("No file name was given.")


def list_root(path):
    """The names in the root folder of the image, [(name, size, is_folder)], or raises ValueError (see find)."""
    with open(path, "rb") as f:
        off = _partition(f)
        if off is None:
            raise ValueError("This is not an Xbox 360 disc image the editor can read (no Xbox file system was found in it).")
        sector, size = _root(f, off)
        return sorted((e["name"], e["size"], e["directory"]) for e in _entries(_table(f, off, sector, size)))


def describe(path):
    """A line saying what the image is, for an error message: its size and whether the descriptor was found at any of the known places."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            off = _partition(f)
        return f"{os.path.basename(path)}: {size:,} bytes, " + (f"Xbox file system found at offset {off:#x}" if off is not None else "no Xbox file system found")
    except OSError as e:
        return f"{path}: {e}"


def extract(path, name, dest, progress=None):
    """Copy a file out of the image to dest (written as dest + '.part' first and renamed, so a stopped copy never leaves a file that looks complete). progress(done, total) is called now and then. Returns
    the number of bytes. Raises ValueError (see find) or OSError."""
    off, sector, size = find(path, name)
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    part = dest + ".part"
    done = 0
    with open(path, "rb") as src, open(part, "wb") as out:
        src.seek(off + sector * SECTOR)
        while done < size:
            block = src.read(min(CHUNK, size - done))
            if not block:
                raise ValueError(f"The disc image ends before {name} does (it is cut short).")
            out.write(block)
            done += len(block)
            if progress:
                progress(done, size)
    os.replace(part, dest)
    return done
