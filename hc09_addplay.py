"""
Adding a play to the game's own play database, so that the game treats it as a normal play (flip, hot routes, adjustments, the CPU calls it): the rows of a new play go into the master
play database (qkl_boot.ast entry 40), its compact copy (entry 42), the playbooks' names for it (entry 46, PPPN) and the user-profile template's links (entry 47, PGPL), and the
playbook links go into the profile (a new career copies its links from the PROFILE, not from the game file) and into the careers that should have the play.

Every table of the game's database is exactly full and the archive's entries follow each other without a gap, so the bridge (add-play) writes bigger copies of the four entries at the
END of qkl_boot.ast and points the table of contents at them (proven in the game: the play shows in the playbook, runs, and can be flipped and have its routes changed). This module only
works out the ROWS from what the Play creator shows; the bridge puts them in, checks them and keeps what is needed to put the files back byte for byte. No Tk.

A play whose players line up somewhere else than in the stock formation (set) needs a formation of its own: every play of a set shares its alignment, so moving a player in the stock set
would move him in all of them (the set "Big" has 86 plays). Such a play gets a NEW set, a copy of the stock one with only the moved players' places changed (its slots, the places in each
alignment group, the groups, the quick-sub packages; NOT the compact copy's slots, which crash the game: see new_set_rows), linked into the same playbooks as the stock set.
"""
import copy

import hc09_gamefiles as GF
import hc09_plays as P

ENTRIES = (40, 42, 46, 47)
PASS_COLS = tuple(f"{a}{k}" for k in range(1, 6) for a in ("per", "rcv"))
TEXT_COLS = {"name", "PPPM"}
LINK_TABLES = {"PGPL": ("BOKL", "SETL", "PLYL", "PLTP"), "PGSL": ("BOKL", "SETL", "PBFM"), "PGSS": ("BOKL", "SETL")}      # the playbook link tables of a save and their columns
LINK_KEYS = {"PGPL": ("BOKL", "SETL", "PLYL"), "PGSL": ("BOKL", "SETL"), "PGSS": ("BOKL", "SETL")}


def _num(row):
    """A row as the bridge takes it: numbers as numbers, the text columns as text."""
    return {k: (str(v) if k in TEXT_COLS else int(v)) for k, v in row.items()}


def _highest_free(used, count, top):
    """`count` ids below `top` that are not in `used`, the highest first."""
    out = []
    for i in range(top - 1, 0, -1):
        if i not in used:
            out.append(i)
            if len(out) == count:
                return out
    raise ValueError("The game has no free ids left for that.")


def free_play_id(lib, taken=()):
    """The play id for a new play: the highest id below the game's highest that no play uses (the proven way: 7455 to 7458 were free), so the ids that custom plays take (the small
    numbers) and the ones the game gives to plays made in it later are left alone."""
    used = set(lib.plays) | {int(t) for t in taken}
    return _highest_free(used, 1, max(used))[0]


MAX_SETL = 511                  # the set id field is 9 bits wide
STOCK_MAX_SETL = 500            # the game's highest set


def _block_above(used, count):
    """`count` consecutive ids, ascending, above every id in `used`."""
    start = (max(used) if used else 0) + 1
    return list(range(start, start + count))


def free_set_ids(lib, slots=11, groups=1, packages=0, taken=None):
    """The ids of a new set in the game's own tables: {"SETL": n, "SETP": [one per slot], "SGF_": [one per alignment group], "SPF_": [one per quick-sub package]}. EVERY id is above all ids in use,
    so that the new rows come AFTER every stock row in the tables (which are sorted by set): found in the game (2026-10-28) that rows put BEFORE stock rows crash it (one set inserted before the
    last stock set survived, two did not; two appended after the last one play). The set id field is 9 bits wide and the game's highest set is 500, so there is room for 11 sets of our own (501 to
    511). The slot, group and package ids are consecutive ascending blocks in the order of the rows, as the game's own sets number them (the id of a slot is the first one plus its number: 239 of 240
    sets). `taken` = {"SETL": ids, "SETP": ..., "SGF_": ..., "SPF_": ...} that must not be used either (earlier added sets, ids a save holds)."""
    taken = taken or {}
    quick = getattr(lib, "quick_subs", None) or {}
    used = {"SETL": {int(k) for k in lib.sets}, "SETP": {int(r["SETP"]) for r in lib.tables["SETP"]}, "SGF_": {int(r["SGF_"]) for r in lib.tables["SGFF"]},
            "SPF_": {int(r["SPF_"]) for r in quick.get("SPKF", [])}}
    for k in used:
        used[k] |= {int(x) for x in taken.get(k, ())}
    setl = _block_above(used["SETL"], 1)[0]
    if setl > MAX_SETL:
        raise ValueError(f"The game has room for {MAX_SETL - STOCK_MAX_SETL} formations of its own (set ids {STOCK_MAX_SETL + 1} to {MAX_SETL}) and they are all taken. Take a play with its own formation out first.")
    return {"SETL": setl, "SETP": _block_above(used["SETP"], slots), "SGF_": _block_above(used["SGF_"], groups), "SPF_": _block_above(used["SPF_"], packages) if packages else []}


def books_of(lib, base):
    """The playbooks (BOKL) that hold the play."""
    return sorted(lib.books_of_play.get(base, ()))


def moved_players(lib, base, alignment):
    """The slots of an alignment that are not where the stock set has them."""
    stock = lib.alignment(lib.detail(base)["set"]["setl"])
    return sorted(poso for poso, (x, y) in (alignment or {}).items() if poso in stock and (abs(float(x) - stock[poso]["x"]) > 0.001 or abs(float(y) - stock[poso]["y"]) > 0.001))


def check_name(name):
    return GF.clean_name(name)


def compact_row(setl, plyl, plyt, plpd=None, plrd=None):
    """A play's row in the compact copy of the database (qkl_boot.ast entry 42): the pass reads (PLPD) and the run hole (PLRD) sit in the play's own row, zeros where the play has none. Checked
    against all 3,099 stock plays: it reproduces every one."""
    row = {"SETL": setl, "PLYL": plyl, "PLYT": plyt, "hole": int(plrd["hole"]) if plrd else 0}
    for c in PASS_COLS:
        row[c] = int(plpd[c]) if plpd else 0
    return row


def set_ids_needed(lib, base):
    """How many ids a copy of the base play's set needs: (slots, alignment groups, quick-sub packages)."""
    setl = lib.detail(base)["set"]["setl"]
    quick = getattr(lib, "quick_subs", None) or {}
    return (len([r for r in lib.tables["SETP"] if int(r["SETL"]) == setl]), len([g for g in lib.tables["SGFF"] if int(g["SETL"]) == setl]),
            len([r for r in quick.get("SPKF", []) if int(r["SETL"]) == setl]))


def new_set_rows(lib, base, new, alignment, ids, set_name):
    """The rows of a copy of the base play's set with the moved players' places changed: ({"40": {SETL, SETP, SETG, SGFF, SPKF, SPKG}, "42": {}}, the new set's id). The copy is the stock set's
    own rows with only these values changed: the diagram places (SETP artx, arty) and the yards of the normal alignment group (SETG x___, y___, fx__, fy__, the flipped partner's too) of the players
    that moved. Nothing goes into the compact copy (entry 42): its slot table cannot take another set (found in the game: even one extra set of slot rows there crashes it)."""
    d = lib.detail(base)
    st = d["set"]
    setl = int(st["setl"])
    set_name = GF.clean_name(set_name)
    setp_diff, setg_diff, dflt = GF.alignment_changes(lib, d, new, alignment)
    stock_setl = next(r for r in lib.tables["SETL"] if int(r["SETL"]) == setl)
    stock_setp = sorted((r for r in lib.tables["SETP"] if int(r["SETL"]) == setl), key=lambda r: int(r["poso"]))
    groups = [g for g in lib.tables["SGFF"] if int(g["SETL"]) == setl]
    quick = getattr(lib, "quick_subs", None) or {}
    packages = [r for r in quick.get("SPKF", []) if int(r["SETL"]) == setl]
    if len(ids["SETP"]) != len(stock_setp) or len(ids["SGF_"]) != len(groups) or len(ids["SPF_"]) != len(packages):
        raise ValueError("The ids do not fit the set.")
    new_setl = ids["SETL"]
    setp_map = {int(r["SETP"]): ids["SETP"][i] for i, r in enumerate(stock_setp)}
    group_map = {int(g["SGF_"]): ids["SGF_"][i] for i, g in enumerate(groups)}
    pack_map = {int(r["SPF_"]): ids["SPF_"][i] for i, r in enumerate(packages)}
    poso_of = {int(r["SETP"]): int(r["poso"]) for r in stock_setp}
    r40 = {"SETL": [{**stock_setl, "SETL": new_setl, "name": set_name}]}
    clean = lambda row: {**row, "name": GF._text(row["name"])} if "name" in row else row
    setp_rows = []
    for r in stock_setp:
        row = {**r, "SETL": new_setl, "SETP": setp_map[int(r["SETP"])]}
        row.update({k: v for k, v in setp_diff.get(int(r["poso"]), {}).items()})
        setp_rows.append(row)
    r40["SETP"] = setp_rows
    r40["SGFF"] = [clean({**g, "SETL": new_setl, "SGF_": group_map[int(g["SGF_"])]}) for g in groups]
    setg_rows = []
    for g in lib.tables["SETG"]:
        if int(g["SETP"]) in setp_map and int(g["SGF_"]) in group_map:
            row = {**g, "SETP": setp_map[int(g["SETP"])], "SGF_": group_map[int(g["SGF_"])]}
            if dflt is not None and int(g["SGF_"]) == dflt:
                row.update(setg_diff.get(poso_of[int(g["SETP"])], {}))
            setg_rows.append(row)
    r40["SETG"] = setg_rows
    if packages:
        r40["SPKF"] = [clean({**r, "SETL": new_setl, "SPF_": pack_map[int(r["SPF_"])]}) for r in packages]
        r40["SPKG"] = [{**r, "SPF_": pack_map[int(r["SPF_"])]} for r in quick.get("SPKG", []) if int(r["SPF_"]) in pack_map]
    # The compact copy (entry 42, the simulation's playbooksim data) gets NO slot rows of the new set: found in the game (2026-10-28), eleven more SETP rows there (2640 = 240 sets x 11 is what it
    # holds) crash the game on the day before the first game, even when the new set has no play and no links (a fixed-size area the simulation reads them into). The main database takes the whole set.
    return {"40": r40, "42": {}}, new_setl


def build(lib, base, name, books, plyl, overrides=None, plan=None, reads=None, alignment=None, set_name=None, set_ids=None, book_pbfm=None, new_set=False):
    """What the bridge needs for a new play id `plyl`, made from the stock play `base` as the Play creator shows it (overrides, plan, reads, alignment as in hc09_gamefiles.changes_for), put into
    the playbooks `books`: {"plyl", "name", "base", "setl", "new_set", "plyt", "books", "rows": {"40": {table: [row]}, "42": ..., "46": ..., "47": ...}}. When players are moved (or new_set is
    asked for) the play gets a set of its own: set_name (its name), set_ids (free_set_ids) and book_pbfm ({playbook: the formation id the playbook gives the stock set}, the PBFM of its PGSL row)
    are needed. Raises ValueError for what cannot be added."""
    name = GF.clean_name(name)
    d = lib.detail(base)
    if d["side"] != "offense":
        raise ValueError("Only offensive plays can be added for now.")
    if plyl in lib.plays:
        raise ValueError(f"The game already has a play {plyl}.")
    own_set = bool(moved_players(lib, base, alignment)) or new_set
    have = set(books_of(lib, base))
    books = sorted({int(b) for b in books})
    if not books:
        raise ValueError("Choose at least one playbook.")
    if any(b not in have for b in books):
        raise ValueError("The play can only go into playbooks that already have the play it was made from (they hold its formation).")
    st = d["set"]
    _d, new = GF._new_rows(lib, base, overrides or {}, plan, reads, alignment)
    nb = new["PBPL"][0]
    plyt = int(nb["PLYT"])
    stock_setl = int(st["setl"])
    setl = stock_setl
    extra40, extra42, extra47 = {}, {}, {}
    if own_set:
        if not set_name or not set_ids or book_pbfm is None:
            raise ValueError("A play whose players are somewhere else than in the stock formation needs a formation of its own: a name for it and free ids are needed.")
        if any(b not in book_pbfm for b in books):
            raise ValueError("The formation of the play was not found in every playbook chosen.")
        sets, setl = new_set_rows(lib, base, new, alignment, set_ids, set_name)
        extra40, extra42 = sets["40"], sets["42"]
        extra47 = {"PGSL": [{"BOKL": b, "SETL": setl, "PBFM": book_pbfm[b]} for b in books], "PGSS": [{"BOKL": b, "SETL": setl} for b in books]}
    base_play = lib.plays[base]
    pbpl = {"SETL": setl, "PLYL": plyl, "SITT": int(base_play["sitt"]), "PLYT": plyt, "PLF_": int(nb["PLF_"]), "name": name, "risk": int(nb["risk"]), "motn": int(nb["motn"]), "vpos": int(nb["vpos"])}
    plys = [{"PSAL": int(r["PSAL"]), "ARTL": int(r["ARTL"]), "PLYL": plyl, "PLRR": int(r["PLRR"]), "poso": int(r["poso"])} for r in new["PLYS"]]
    r40 = {"PBPL": [pbpl], "PLYS": plys}
    for table in ("PLPD", "PLRD", "PLCM"):
        if new.get(table):
            r40[table] = [{**{k: v for k, v in row.items() if k != "PLYL"}, "PLYL": plyl} for row in new[table]]
    warnings = []
    if own_set:
        # no CPU rows (PBAI): the simulation (which also plays the quarterback's offensive coordinator) would look the new set up in the compact copy, which cannot hold it
        warnings.append("The computer will not call this play (a play in a formation of its own is not in the simulation's data); you can call it yourself.")
    else:
        pbai = []
        for r in lib.tables["PBAI"]:
            if int(r["PBPL"]) == base and int(r["BOKL"]) in books:
                pbai.append({"BOKL": int(r["BOKL"]), "PBPL": plyl, "SETL": setl, "AIGR": int(r["AIGR"]), "PLYT": plyt, "PLF_": pbpl["PLF_"], "vpos": pbpl["vpos"], "prct": int(r["prct"])})
        if not pbai:
            raise ValueError("The play has no CPU rows (PBAI) in those playbooks.")
        r40["PBAI"] = pbai
    row42 = compact_row(setl, plyl, plyt, (r40.get("PLPD") or [None])[0], (r40.get("PLRD") or [None])[0])
    r42 = {"PBPL": [row42], "PLYS": [{"PLYL": plyl, "PLRR": r["PLRR"], "poso": r["poso"]} for r in plys]}
    r47 = {"PGPL": [{"BOKL": b, "SETL": setl, "PLYL": plyl, "PLTP": plyt} for b in books]}
    r40.update(extra40)
    r42.update(extra42)
    r47.update(extra47)
    rows = {"40": r40, "42": r42, "46": {"PPPN": [{"BOKL": b, "PLYL": plyl, "PPPM": name} for b in books]}, "47": r47}
    rows = {e: {t: [_num(r) for r in rs] for t, rs in tables.items()} for e, tables in rows.items()}
    return {"plyl": plyl, "name": name, "base": base, "setl": setl, "new_set": setl if own_set else None, "plyt": plyt, "books": books, "rows": rows, "warnings": warnings}


def merge(plays):
    """The spec for the bridge: the rows of all the plays that are to be in the game files (a play with the same id as an earlier one replaces it)."""
    by_id = {}
    for p in plays:
        by_id[p["plyl"]] = p
    plays = [by_id[k] for k in sorted(by_id)]
    rows = {}
    for p in plays:
        for entry, tables in p["rows"].items():
            for table, rs in tables.items():
                rows.setdefault(entry, {}).setdefault(table, []).extend(copy.deepcopy(rs))
    return {"rows": rows, "plays": plays}


def taken_ids(plays):
    """The set ids the added plays already use: {"SETL": ..., "SETP": ..., "SGF_": ..., "SPF_": ...} (for free_set_ids)."""
    out = {"SETL": [], "SETP": [], "SGF_": [], "SPF_": []}
    for p in plays:
        t = p["rows"]["40"]
        out["SETL"] += [r["SETL"] for r in t.get("SETL", [])]
        out["SETP"] += [r["SETP"] for r in t.get("SETP", [])]
        out["SGF_"] += [r["SGF_"] for r in t.get("SGFF", [])]
        out["SPF_"] += [r["SPF_"] for r in t.get("SPKF", [])]
    return out


def links_of(plays):
    """The playbook links a save needs for the plays: {"PGPL": [...], "PGSL": [...], "PGSS": [...]} (the last two only for plays with a set of their own)."""
    out = {t: [] for t in LINK_TABLES}
    for p in plays:
        for t in LINK_TABLES:
            out[t] += [dict(r) for r in p["rows"]["47"].get(t, [])]
    return out


def insert_rows(rows, new, keys):
    """A link table's rows (dicts of strings) with the new rows added: one that is there is not added twice. The game's own rows come first in sorted order and the player's own after them; a new row
    goes into the sorted block. Returns (rows, number added)."""
    key = lambda r: tuple(int(r[k]) for k in keys)
    have = {key(r) for r in rows}
    block = 0
    while block + 1 < len(rows) and key(rows[block]) <= key(rows[block + 1]):
        block += 1
    block += 1 if rows else 0
    out, added = [dict(r) for r in rows], 0
    for n in sorted(new, key=key):
        if key(n) in have:
            continue
        i = block
        while i > 0 and key(out[i - 1]) > key(n):
            i -= 1
        out.insert(i, {k: str(v) for k, v in n.items()})
        have.add(key(n))
        block += 1
        added += 1
    return out, added


def insert_links(rows, links):
    """insert_rows for PGPL (kept under its first name)."""
    return insert_rows(rows, links, LINK_KEYS["PGPL"])


def remove_links(rows, plyls):
    """The save's PGPL rows without the links of these plays. Returns (rows, number removed)."""
    gone = {int(p) for p in plyls}
    out = [dict(r) for r in rows if int(r["PLYL"]) not in gone]
    return out, len(rows) - len(out)


def remove_set_links(rows, setls):
    """The save's PGSL or PGSS rows without the links of these (added) sets. Returns (rows, number removed)."""
    gone = {int(s) for s in setls}
    out = [dict(r) for r in rows if int(r["SETL"]) not in gone]
    return out, len(rows) - len(out)
