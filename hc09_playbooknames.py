"""
Renaming the game's default playbooks ("Martz Air Attack", "West Coast", "3-4 Pressure" ...).

The names are in the table PLAB of qkl_boot.ast (entry 35 in the PS3 game), column BNAM: 89 rows, 46 offense and 43 defense playbooks. A row is identified by its playbook group (BGID) and its side
(BOFF, 1 offense, 0 defense): that pair is unique, PBGI (the playbook's own table key, the BOKL of the playbook tables) is NOT: ten playbooks are listed twice under one PBGI (the coach's playbook
and the same playbook as "<coach>'s Plays"), each row with its own name. A name is up to 21 printable ASCII characters (the field holds 21; a longer name does not read back, which the bridge's
entry-patch checks before it writes anything). The entry keeps its length, so the rename is an in-place patch of that one entry, like the other game-file changes: the bridge's entry-patch backs
the entry up the first time and puts it back byte for byte.

Standard library only (no Tk). books_from_rows() reads the exported rows, edits_for() checks the new names and works out the bridge edits, target_for() makes the entry-patch target.
"""
import re

TABLE = "PLAB"
MAX_NAME = 21
EXPORT_FIELDS = "PBGI,BNAM,BGID,BOFF"          # the columns the shipped-table-export must find (the other PLAB entry of the archive has none of them and no rows)
SIDES = {1: "offense", 0: "defense"}


def clean_name(name):
    """A playbook's name as the game can hold it: 1 to 21 printable ASCII characters (spaces at the ends are dropped)."""
    name = (name or "").strip()
    if not 1 <= len(name) <= MAX_NAME or any(ord(c) < 32 or ord(c) > 126 for c in name):
        raise ValueError(f"A playbook name is 1 to {MAX_NAME} letters, digits and ordinary signs.")
    if re.fullmatch(r"@+", name):
        raise ValueError("A playbook name cannot be only @ signs (the game's files use them as filler).")
    return name


def books_from_rows(rows):
    """The playbooks of the game's PLAB rows (dicts of text, as read from the exported CSV): [{key (BGID, BOFF), bgid, boff, side, bord, pbgi, name (as shown), raw (as the game holds it, with any
    trailing space), asset}], offense first, in the order the game lists them (BORD). Rows without a playbook group or side are left out."""
    out = []
    for r in rows:
        try:
            bgid, boff = int(str(r["BGID"]).strip()), int(str(r["BOFF"]).strip())
        except (KeyError, ValueError):
            continue
        if boff not in SIDES:
            continue
        try:
            bord = int(str(r.get("BORD", "")).strip())
        except ValueError:
            bord = bgid
        try:
            pbgi = int(str(r.get("PBGI", "")).strip())
        except ValueError:
            pbgi = None
        raw = r.get("BNAM") or ""
        out.append({"key": (bgid, boff), "bgid": bgid, "boff": boff, "side": SIDES[boff], "bord": bord, "pbgi": pbgi, "name": raw.strip() or f"Playbook {bgid}", "raw": raw,
                    "asset": (r.get("PBAN") or "").strip()})
    out.sort(key=lambda b: (-b["boff"], b["bord"], b["bgid"]))
    return out


def also_listed_as(books, book):
    """The names the same playbook (same PBGI and side) has in its other row(s): the coach's playbook is also listed as "<coach>'s Plays", for ten of them."""
    if book["pbgi"] is None:
        return []
    return [b["name"] for b in books if b["boff"] == book["boff"] and b["pbgi"] == book["pbgi"] and b["key"] != book["key"]]


def edits_for(books, renames):
    """Bridge entry-patch edits for {(BGID, BOFF): new name}: [{table, match, expect, set}], only for the playbooks whose name changes. Raises ValueError for a name the game cannot hold, a playbook that is
    not there, or a name another playbook of the same side would have too (the Playbooks tab and the game's menus tell playbooks apart by name)."""
    by_key = {b["key"]: b for b in books}
    wanted = {}
    for key, name in renames.items():
        if key not in by_key:
            raise ValueError(f"There is no playbook {key} in the game files that were read.")
        wanted[key] = clean_name(name)
    final = {b["key"]: wanted.get(b["key"], b["name"]) for b in books}
    for key, name in wanted.items():
        for other_key, other_name in final.items():
            if other_key != key and other_key[1] == key[1] and other_name.lower() == name.lower():
                raise ValueError(f"Another {SIDES[key[1]]} playbook is already called {other_name}: give each playbook its own name.")
    edits = []
    for key, name in sorted(wanted.items(), key=lambda kv: (-kv[0][1], kv[0][0])):
        b = by_key[key]
        if name == b["name"] and name == b["raw"]:
            continue
        edits.append({"table": TABLE, "match": {"BGID": key[0], "BOFF": key[1]}, "expect": {"BNAM": b["raw"]}, "set": {"BNAM": name}})
    return edits


def target_for(entry, edits):
    """The bridge entry-patch target for the PLAB entry ({ast, index, start, size} from entry-locate) and the edits of edits_for()."""
    return {"ast": entry["ast"], "index": entry["index"], "start": entry["start"], "size": entry["size"], "edits": edits}


def restore_target_for(entry):
    """The target that puts the entry back from its backup (entry-patch restore)."""
    return target_for(entry, [])
