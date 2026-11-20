"""Read and safely replace files in an Xbox 360 XDVDFS disc image (.iso).

The editor extracts qkl_boot.ast for Recomp and can publish an edited copy into
a NEW ISO by appending the replacement file and updating its XDVDFS directory
entry. The source image is never modified. The writer has structural checks,
but still needs validation against a real Recomp installation/disc image.

The image holds an XDVDFS ("GDF") file system: 2,048-byte sectors, the volume descriptor in sector 32 of the data partition, which starts at an offset that depends on the disc's layout (XGD1, XGD2, XGD3; a
plain image is 0). The descriptor starts with MICROSOFT*XBOX*MEDIA and names the root directory (its first sector and its size); a directory is a table of entries, a binary tree whose links are in units of
four bytes: left (2 bytes), right (2), first sector (4), size (4), attributes (1, 0x10 = directory), name length (1), the name; entries are padded to four bytes with 0xFF."""
import os
import shutil
import struct
import tempfile

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
    """Copy a file out of the image to dest (written to a temporary .part file beside it first and renamed, so a stopped copy never leaves a file that looks complete). progress(done, total) is called now and then. Returns
    the number of bytes. Raises ValueError (see find) or OSError."""
    off, sector, size = find(path, name)
    if off + sector * SECTOR + size > os.path.getsize(path):                  # a damaged or cut-short image: say so before hundreds of megabytes are copied for nothing
        raise ValueError(f"The disc image ends before {name} does (it is cut short).")
    folder = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(folder, exist_ok=True)
    done, part = 0, None
    try:
        with open(path, "rb") as src:
            handle, part = tempfile.mkstemp(prefix=os.path.basename(dest) + ".", suffix=".part", dir=folder)      # its own name: two copies to the same place do not write into one file
            with os.fdopen(handle, "wb") as out:
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
    except BaseException:                                         # a failed or stopped copy leaves no half file behind (it may be hundreds of MB)
        if part:
            try:
                os.remove(part)
            except OSError:
                pass
        raise
    return done


def _locate_entry(f, off, name):
    """Return parent directory sector/size and the byte offset of a file entry."""
    sector, size = _root(f, off)
    parts = [p for p in name.replace("\\", "/").split("/") if p]
    if not parts:
        raise ValueError("No file name was given.")
    for i, part in enumerate(parts):
        table = _table(f, off, sector, size)
        found = None
        stack, seen = [0], set()
        while stack:
            pos = stack.pop()
            if pos in seen or pos + 14 > len(table):
                continue
            seen.add(pos)
            left, right, child_sector, child_size, attr, name_len = struct.unpack_from("<HHIIBB", table, pos)
            if (child_sector == 0xFFFFFFFF and child_size == 0xFFFFFFFF) or name_len == 0 or pos + 14 + name_len > len(table):
                continue
            entry_name = table[pos + 14:pos + 14 + name_len].decode("latin-1")
            if entry_name.lower() == part.lower():
                found = (pos, child_sector, child_size, bool(attr & DIRECTORY))
                break
            for child in (left, right):
                if child not in (0, 0xFFFF):
                    stack.append(child * 4)
        if found is None:
            raise ValueError(f"{name} is not in the disc image.")
        pos, child_sector, child_size, is_dir = found
        if i == len(parts) - 1:
            if is_dir:
                raise ValueError(f"{name} is a folder, not a file.")
            return sector, pos, child_sector, child_size
        if not is_dir:
            raise ValueError(f"{part} is a file, not a folder.")
        sector, size = child_sector, child_size
    raise ValueError("No file name was given.")


def replace_file(source_iso, name, replacement_path, destination_iso, progress=None):
    """Create a new XDVDFS image with one file replaced; never modifies source_iso.

    The replacement is appended at a sector-aligned location and the existing
    directory entry is redirected to it. All other image bytes remain intact.
    """
    source_iso = os.path.abspath(source_iso)
    replacement_path = os.path.abspath(replacement_path)
    destination_iso = os.path.abspath(destination_iso)
    if os.path.normcase(source_iso) == os.path.normcase(destination_iso):
        raise ValueError("Choose a new output filename; the original disc image is never overwritten.")
    if not os.path.isfile(source_iso) or not os.path.isfile(replacement_path):
        raise FileNotFoundError("The source disc image or replacement archive does not exist.")
    size = os.path.getsize(replacement_path)
    if size <= 0 or size > 0xFFFFFFFF:
        raise ValueError("The replacement archive has an unsupported size for XDVDFS.")
    with open(source_iso, "rb") as src:
        off = _partition(src)
        if off is None:
            raise ValueError("This is not an Xbox 360 disc image the editor can read.")
        parent_sector, entry_pos, old_sector, old_size = _locate_entry(src, off, name)
    if off + old_sector * SECTOR + old_size > os.path.getsize(source_iso):
        raise ValueError(f"The original {name} extends beyond the end of the disc image.")
    folder = os.path.dirname(destination_iso) or "."
    os.makedirs(folder, exist_ok=True)
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix=os.path.basename(destination_iso) + ".", suffix=".part", dir=folder)
        os.close(fd)
        shutil.copyfile(source_iso, temp)
        image_size = os.path.getsize(temp)
        data_offset = off + ((max(0, image_size - off) + SECTOR - 1) // SECTOR) * SECTOR
        new_sector = (data_offset - off) // SECTOR
        if new_sector > 0xFFFFFFFF:
            raise ValueError("The output image is too large for an XDVDFS sector address.")
        done = 0
        with open(temp, "r+b") as out:
            out.seek(0, os.SEEK_END)
            if out.tell() < data_offset:
                out.write(b"\x00" * (data_offset - out.tell()))
            with open(replacement_path, "rb") as repl:
                while True:
                    block = repl.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if progress:
                        progress(done, size)
            out.seek(off + parent_sector * SECTOR + entry_pos + 6)
            out.write(struct.pack("<II", new_sector, size))
            out.flush()
            os.fsync(out.fileno())
        check_off, check_sector, check_size = find(temp, name)
        if (check_off, check_sector, check_size) != (off, new_sector, size):
            raise ValueError("The output image failed its XDVDFS directory-entry verification.")
        shutil.copystat(source_iso, temp)
        os.replace(temp, destination_iso)
        temp = None
        return destination_iso
    finally:
        if temp and os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass
