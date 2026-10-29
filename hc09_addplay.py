"""
Adding a play to the game's own play database, so that the game treats it as a normal play (flip, hot routes, adjustments; the computer does not call it, see free_play_id): the rows of a new play go into the master
play database (qkl_boot.ast entry 40), its compact copy (entry 42), the playbooks' names for it (entry 46, PPPN) and the user-profile template's links (entry 47, PGPL), and the
playbook links go into the profile (a new career copies its links from the PROFILE, not from the game file) and into the careers that should have the play.

Every table of the game's database is exactly full and the archive's entries follow each other without a gap, so the bridge (add-play) writes bigger copies of the four entries at the
END of qkl_boot.ast and points the table of contents at them (proven in the game: the play shows in the playbook, runs, and can be flipped and have its routes changed). This module only
works out the ROWS from what the Play creator shows; the bridge puts them in, checks them and keeps what is needed to put the files back byte for byte. No Tk.

Scope of this first version: offense; the play keeps the stock formation (a moved player would change the alignment of every play of the set: use a custom play or Make a game play for
that); the play goes into playbooks that already hold the play it was made from (so its set is in them).
"""
import copy

import hc09_gamefiles as GF
import hc09_plays as P

ENTRIES = (40, 42, 46, 47)
PASS_COLS = tuple(f"{a}{k}" for k in range(1, 6) for a in ("per", "rcv"))
TEXT_COLS = {"name", "PPPM"}


def _num(row):
    """A row as the bridge takes it: numbers as numbers, the text columns as text."""
    return {k: (str(v) if k in TEXT_COLS else int(v)) for k, v in row.items()}


STOCK_MAX_PLYL = 7459           # the highest play id of the stock game (Man Blitz)
MAX_PLYL = 16383                # the play id field is 14 bits wide


def free_play_id(lib, taken=()):
    """The play id for a new play: the next id above the game's highest stock play (7459) and every id in use (7460 first). It must be ABOVE the stock maximum: found in the game (RPCS3,
    2026-10-29) that the game builds an in-memory list of plays from the compact copy (qkl_boot.ast entry 42) and reads only its FIRST 3,099 rows, the stock count. A play with an id below
    the stock maximum sorts in front of the last stock plays and pushes them out of that list; the game then asks for one of them (a side's current play, Man Blitz 7459) on the day before the
    first game, finds nothing and crashes (two added plays in one formation crashed, two in different formations did not, only because of which play was pushed out). With ids above 7459 the first
    3,099 rows are exactly the stock plays. The added plays are then not in that list, so the computer cannot call them (build writes no CPU rows)."""
    top = max([STOCK_MAX_PLYL] + [int(p) for p in lib.plays] + [int(t) for t in taken])
    if top + 1 > MAX_PLYL:
        raise ValueError("The game has no free play id left.")
    return top + 1


def check_play_id(plyl):
    """Raises ValueError for a play id that is not above the stock maximum (see free_play_id)."""
    if int(plyl) <= STOCK_MAX_PLYL:
        raise ValueError(f"A play added to the game files needs an id above {STOCK_MAX_PLYL}, the game's highest play: a lower id pushes a stock play out of the game's play list and the game crashes "
                         "on the day before the first game.")


def check_ids(plays):
    """Raises ValueError when an added play has an id that is not above the stock maximum: a play added by an older version of the editor (ids 7455 to 7458) crashes the game."""
    low = sorted(int(p["plyl"]) for p in plays if int(p["plyl"]) <= STOCK_MAX_PLYL)
    if low:
        raise ValueError(f"The plays {', '.join(str(i) for i in low)} were added by an older version of the editor with ids that crash the game on the day before the first game. Press Put the game files back "
                         "and add the plays again (they get ids above 7459).")


def books_of(lib, base):
    """The playbooks (BOKL) that hold the play."""
    return sorted(lib.books_of_play.get(base, ()))


def moved_players(lib, base, alignment):
    """The slots of an alignment that are not where the stock set has them (adding a play does not move players: the formation is shared by all plays of the set)."""
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


def build(lib, base, name, books, plyl, overrides=None, plan=None, reads=None, alignment=None):
    """What the bridge needs for a new play id `plyl`, made from the stock play `base` as the Play creator shows it (overrides, plan, reads as in hc09_gamefiles.changes_for), put into
    the playbooks `books`: {"plyl", "name", "base", "setl", "plyt", "books", "rows": {"40": {table: [row]}, "42": ..., "46": ..., "47": ...}}. Raises ValueError for what cannot be added."""
    name = GF.clean_name(name)
    d = lib.detail(base)
    if d["side"] != "offense":
        raise ValueError("Only offensive plays can be added for now.")
    if plyl in lib.plays:
        raise ValueError(f"The game already has a play {plyl}.")
    check_play_id(plyl)
    if moved_players(lib, base, alignment):
        raise ValueError("A player was moved: that changes the formation (the set), which every play of it shares. Use a custom play, or Make a game play, for a changed formation.")
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
    setl = int(st["setl"])
    base_play = lib.plays[base]
    pbpl = {"SETL": setl, "PLYL": plyl, "SITT": int(base_play["sitt"]), "PLYT": plyt, "PLF_": int(nb["PLF_"]), "name": name, "risk": int(nb["risk"]), "motn": int(nb["motn"]), "vpos": int(nb["vpos"])}
    plys = [{"PSAL": int(r["PSAL"]), "ARTL": int(r["ARTL"]), "PLYL": plyl, "PLRR": int(r["PLRR"]), "poso": int(r["poso"])} for r in new["PLYS"]]
    r40 = {"PBPL": [pbpl], "PLYS": plys}
    for table in ("PLPD", "PLRD", "PLCM"):
        if new.get(table):
            r40[table] = [{**{k: v for k, v in row.items() if k != "PLYL"}, "PLYL": plyl} for row in new[table]]
    # No CPU rows (PBAI): the game's play list (the first 3,099 rows of the compact copy) cannot hold an added play, and a CPU pick of a play that is not in it would crash the game.
    row42 = compact_row(setl, plyl, plyt, (r40.get("PLPD") or [None])[0], (r40.get("PLRD") or [None])[0])
    r42 = {"PBPL": [row42], "PLYS": [{"PLYL": plyl, "PLRR": r["PLRR"], "poso": r["poso"]} for r in plys]}
    rows = {"40": r40, "42": r42, "46": {"PPPN": [{"BOKL": b, "PLYL": plyl, "PPPM": name} for b in books]},
            "47": {"PGPL": [{"BOKL": b, "SETL": setl, "PLYL": plyl, "PLTP": plyt} for b in books]}}
    rows = {e: {t: [_num(r) for r in rs] for t, rs in tables.items()} for e, tables in rows.items()}
    warnings = ["The computer will not call this play (the game's play list holds only the stock plays); you can call it yourself."]
    return {"plyl": plyl, "name": name, "base": base, "setl": setl, "plyt": plyt, "books": books, "rows": rows, "warnings": warnings}


def merge(plays):
    """The spec for the bridge: the rows of all the plays that are to be in the game files (a play with the same id as an earlier one replaces it)."""
    by_id = {}
    for p in plays:
        by_id[p["plyl"]] = p
    plays = [by_id[k] for k in sorted(by_id)]
    check_ids(plays)
    rows = {}
    for p in plays:
        for entry, tables in p["rows"].items():
            for table, rs in tables.items():
                rows.setdefault(entry, {}).setdefault(table, []).extend(copy.deepcopy(rs))
    return {"rows": rows, "plays": plays}


def links_of(plays):
    """The playbook links (PGPL rows) a save needs for the plays: [{BOKL, SETL, PLYL, PLTP}]."""
    return [dict(r) for p in plays for r in p["rows"]["47"]["PGPL"]]


def insert_links(rows, links):
    """The save's PGPL rows (dicts of strings) with the links added: a link that is there is not added twice. The game's own links come first in (BOKL, SETL, PLYL) order and the player's
    own after them; a new link goes into the sorted block. Returns (rows, number added)."""
    have = {(int(r["BOKL"]), int(r["SETL"]), int(r["PLYL"])) for r in rows}
    key = lambda r: (int(r["BOKL"]), int(r["SETL"]), int(r["PLYL"]))
    block = 0
    while block + 1 < len(rows) and key(rows[block]) <= key(rows[block + 1]):
        block += 1
    block += 1 if rows else 0                                                    # the length of the sorted block at the start
    out, added = [dict(r) for r in rows], 0
    for link in sorted(links, key=lambda r: (int(r["BOKL"]), int(r["SETL"]), int(r["PLYL"]))):
        if (int(link["BOKL"]), int(link["SETL"]), int(link["PLYL"])) in have:
            continue
        i = block
        while i > 0 and key(out[i - 1]) > key(link):
            i -= 1
        out.insert(i, {"BOKL": str(link["BOKL"]), "SETL": str(link["SETL"]), "PLYL": str(link["PLYL"]), "PLTP": str(link["PLTP"])})
        block += 1
        added += 1
    return out, added


def remove_links(rows, plyls):
    """The save's PGPL rows without the links of these plays. Returns (rows, number removed)."""
    gone = {int(p) for p in plyls}
    out = [dict(r) for r in rows if int(r["PLYL"]) not in gone]
    return out, len(rows) - len(out)
