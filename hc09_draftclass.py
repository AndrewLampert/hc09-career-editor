"""
Draft classes of the game files: plan a change of ratings for every player of one shipped class.

The game keeps a library of draft classes in the tables DPL1 to DPL4 of qkl_boot.ast (entry 46 in the PS3 game; the editor takes the entry from the archive, never a fixed number): 16 classes
per table (5,600 players each, one row per player, 217 columns). DFCL is the class number, PGID the player (unique inside a table), PPOS the position. Class 1 is an identical copy in all four tables.
Which class a career holds changes over time: its DCIC row names it (DFCL, strength tier DCSI, place in the tier DCYR) and a career is moved on to the next class id of its tier when the regular season starts (seen in the game for the first step: class 1 -> class 2).
Read from saves on 2026-11-24: the Bills and Raiders careers hold class 19 (DPL2), DOLPHINS2 class 3, QQETBROWNS class 5, MAINSALCAP class 48; a new career made in the in-game test (Falcons,
starting point off-season) held class 1 (tier 1, place 0), and an edit of class 1 reached its 350 players exactly (seen in the game); the class loaded at the start of that career's regular season (class 2) showed an edit too (seen in the
game). Which class a new career starts with in general was not worked out, and classes 3 and later were not run. A class that is already inside a save does not change; a class a career has not loaded yet (a new career's first class, an existing
career's next one) is read from the game files when it is loaded and shows an edit. About 50 players of a class are moved to the free-agent pool when the game loads it.

This module only plans: it reads the exported rows (dicts of text, as the bridge writes them), works out new values and returns bridge entry-patch edits. Standard library only (no Tk).
A rating is edited together with its maximum (PSPD with PSDX): both move by the same amount, stay inside 0 to 99, and the maximum never falls below the rating.
"""
import math

TIERS = ("DPL1", "DPL2", "DPL3", "DPL4")
RATING_MIN, RATING_MAX = 0, 99
MAX_DELTA = 40                                 # one step of the window; the plan itself accepts any whole number

# The ratings the window offers: the ones every position has. (Position-specific ratings are in the data too and can be added to this list; each needs the partner column that holds its maximum.)
RATINGS = (
    ("PSPD", "Speed", "PSDX"),
    ("PACC", "Acceleration", "PACX"),
    ("PAGI", "Agility", "PAGX"),
    ("PSTR", "Strength", "PSTX"),
    ("PJMP", "Jump", "PJMX"),
    ("PAWR", "Awareness", "PAWX"),
    ("PSTA", "Stamina", "PSAX"),
    ("PTGH", "Toughness", "PTGX"),
)
RATING_LABEL = {code: label for code, label, _mx in RATINGS}
RATING_MAX_FIELD = {code: mx for code, _label, mx in RATINGS}

# PPOS -> position, as the editor's own tables name them (guiHC09.POSITIONS; a test keeps the two equal).
POSITION_NAMES = {0: "QB", 1: "HB", 2: "FB", 3: "WR", 4: "TE", 5: "LT", 6: "LG", 7: "C", 8: "RG", 9: "RT",
                  10: "LE", 11: "RE", 12: "DT", 13: "LOLB", 14: "MLB", 15: "ROLB", 16: "CB", 17: "FS", 18: "SS", 19: "K", 20: "P"}
POSITION_ORDER = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 11, 13, 14, 15, 16, 17, 18, 19, 20)       # as the editor lists them (QB HB FB WR TE OL DL LB DB K P)

EXPORT_FIELDS = ",".join(["PGID", "DFCL", "PPOS"] + [c for code, _l, mx in RATINGS for c in (code, mx)])     # the columns the shipped-table-export must find in every table
BASE_FIELDS = ("PGID", "DFCL", "PPOS")


def to_int(value):
    """A whole number from an exported cell, or None for an empty or non-numeric one."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def clamp(value):
    return max(RATING_MIN, min(RATING_MAX, value))


def class_label(table, dfcl, current=False):
    """How the window names a class: its number and the table it is in; current: it is the class the open career holds now (its DCIC)."""
    text = "Class 1 (the same copy in all four tables)" if dfcl == 1 else f"Class {dfcl} ({table})"
    return text + (" - the class your open career has now" if current else "")


def career_class_from_rows(dcic_rows):
    """(class number DFCL, strength tier DCSI) from the rows of a career's DCIC table, or None when it has no readable row."""
    for r in dcic_rows or ():
        dfcl, tier = to_int(r.get("DFCL")), to_int(r.get("DCSI"))
        if dfcl is not None and tier is not None:
            return dfcl, tier
    return None


def classes_in(rows_by_table):
    """{table: {class number: players}} for the exported rows {table: [row dict]} (a row without a readable class is left out)."""
    out = {}
    for table, rows in rows_by_table.items():
        counts = out.setdefault(table, {})
        for r in rows:
            c = to_int(r.get("DFCL"))
            if c is not None:
                counts[c] = counts.get(c, 0) + 1
    return out


def tables_holding(rows_by_table, dfcl):
    """The tables that hold the class, in DPL order. Class 1 is in all four (identical copies): an edit of it has to go to every copy or the game would show one of them depending on the career."""
    held = classes_in(rows_by_table)
    return [t for t in TIERS if dfcl in held.get(t, {})]


def class_choices(rows_by_table, current=None):
    """The classes the window lists: [(label, table, class number)], the class the open career holds now first (current = (DFCL, DCSI) from career_class_from_rows), then the others in table order;
    class 1 is listed once (its four copies change together)."""
    held = classes_in(rows_by_table)
    first_one = next((t for t in TIERS if 1 in held.get(t, {})), None)
    out = []
    for table in TIERS:
        for dfcl in sorted(held.get(table, {})):
            if dfcl == 1 and table != first_one:
                continue
            out.append((class_label(table, dfcl, current=bool(current) and dfcl == current[0]), table, dfcl))
    if current:
        out.sort(key=lambda c: 0 if c[2] == current[0] else 1)             # stable: the rest keep table order
    return out


def class_rows(rows, dfcl):
    return [r for r in rows if to_int(r.get("DFCL")) == dfcl]


def position_means(rows, rating):
    """{PPOS: (players, mean)} of the rating for the players whose value reads as a number."""
    sums = {}
    for r in rows:
        pos, v = to_int(r.get("PPOS")), to_int(r.get(rating))
        if pos is None or v is None:
            continue
        n, s = sums.get(pos, (0, 0))
        sums[pos] = (n + 1, s + v)
    return {pos: (n, s / n) for pos, (n, s) in sums.items()}


def reference_from_rows(rows, ratings=None):
    """{rating: {PPOS: mean}} over the given rows (the veterans of a career, or every class of the library: pass each class once, class 1 only from one table)."""
    ratings = ratings or [c for c, _l, _m in RATINGS]
    return {rating: {pos: mean for pos, (_n, mean) in position_means(rows, rating).items()} for rating in ratings}


def library_rows(rows_by_table):
    """Every player of the library once: class 1 is in all four tables, only the first table's copy counts."""
    out, class_one_from = [], None
    for table in TIERS:
        for r in rows_by_table.get(table, []):
            if to_int(r.get("DFCL")) == 1:
                if class_one_from is None:
                    class_one_from = table
                if table != class_one_from:
                    continue
            out.append(r)
    return out


def suggest_deltas(rows, dfcl, reference, ratings=None):
    """The whole-number change per rating and position that moves the class's mean to the reference's: {rating: {PPOS: delta}} (positions the reference lacks are left alone)."""
    ratings = ratings or [c for c, _l, _m in RATINGS]
    mine = class_rows(rows, dfcl)
    out = {}
    for rating in ratings:
        ref = reference.get(rating, {})
        deltas = {}
        for pos, (_n, mean) in position_means(mine, rating).items():
            if pos in ref:
                d = math.floor(ref[pos] - mean + 0.5)                   # rounds half up, also below zero
                if d:
                    deltas[pos] = d
        out[rating] = deltas
    return out


def _delta_for(deltas, rating, pos):
    spec = deltas.get(rating, 0)
    if isinstance(spec, dict):
        return int(spec.get(pos, 0))
    return int(spec)


def plan(rows_by_table, dfcl, deltas):
    """What changing the class by `deltas` does. deltas: {rating: whole number for every position, or {PPOS: whole number}}.

    Returns {"dfcl", "tables", "edits": {table: [bridge edit]}, "players": players changed (in one copy), "values": values changed (in one copy), "ratings": [per rating: {"rating", "label",
    "lines": [per position: {"ppos", "name", "players", "old_mean", "new_mean", "changed", "clamped"}]}]}.
    A bridge edit is {table, match: {PGID, DFCL}, expect: the old values, set: the new ones}; players whose values do not change get none. 'clamped' counts the players whose new value hit 0 or 99
    (or whose maximum was lifted to the rating) so the window can say that some did not move by the full amount."""
    unknown = [r for r in deltas if r not in RATING_MAX_FIELD]
    if unknown:
        raise ValueError("Not a rating of this editor: " + ", ".join(unknown))
    tables = tables_holding(rows_by_table, dfcl)
    if not tables:
        raise ValueError(f"Class {dfcl} is not in the draft class tables of this archive.")
    edits, summaries = {}, None
    for t_i, table in enumerate(tables):
        t_edits, t_players, t_values = [], set(), 0
        per_rating = {}
        for r in class_rows(rows_by_table[table], dfcl):
            pgid, pos = to_int(r.get("PGID")), to_int(r.get("PPOS"))
            if pgid is None or pos is None:
                continue
            expect, new = {}, {}
            for rating in deltas:
                d = _delta_for(deltas, rating, pos)
                base, mx = to_int(r.get(rating)), to_int(r.get(RATING_MAX_FIELD[rating]))
                if base is None or mx is None:
                    continue
                nb, nm = clamp(base + d), clamp(mx + d)
                if nm < nb:
                    nm = nb
                line = per_rating.setdefault(rating, {}).setdefault(pos, {"n": 0, "old": 0, "new": 0, "changed": 0, "clamped": 0})
                line["n"] += 1
                line["old"] += base
                line["new"] += nb
                if nb != base + d or nm != mx + d:
                    line["clamped"] += 1
                if nb != base:
                    new[rating] = nb
                    expect[rating] = base
                    line["changed"] += 1
                if nm != mx:
                    new[RATING_MAX_FIELD[rating]] = nm
                    expect[RATING_MAX_FIELD[rating]] = mx
            if new:
                t_edits.append({"table": table, "match": {"PGID": pgid, "DFCL": dfcl}, "expect": expect, "set": new})
                t_players.add(pgid)
                t_values += len(new)
        edits[table] = t_edits
        if t_i == 0:
            summaries = (len(t_players), t_values, per_rating)
    players, values, per_rating = summaries
    ratings = []
    for code, label, _mx in RATINGS:
        if code not in per_rating:
            continue
        lines = []
        for pos in POSITION_ORDER:
            ln = per_rating[code].get(pos)
            if ln:
                lines.append({"ppos": pos, "name": POSITION_NAMES.get(pos, str(pos)), "players": ln["n"], "old_mean": ln["old"] / ln["n"], "new_mean": ln["new"] / ln["n"],
                              "changed": ln["changed"], "clamped": ln["clamped"]})
        ratings.append({"rating": code, "label": label, "lines": lines})
    return {"dfcl": dfcl, "tables": tables, "edits": edits, "players": players, "values": values, "ratings": ratings}


def restore_target_for(table_entry):
    """The target that puts the entry back from its backup (entry-patch restore)."""
    return target_for(table_entry, [])


def all_edits(plan_result):
    """Every edit of a plan(), the four tables' edits in one list (the tables are in one entry of the archive, so one target holds them all)."""
    return [e for table in TIERS for e in plan_result["edits"].get(table, [])]


def target_for(table_entry, edits):
    """The bridge entry-patch target for one copy of the library: table_entry = {ast, index, start, size} (the bridge's entry-locate) and the edits of one table of plan()."""
    return {"ast": table_entry["ast"], "index": table_entry["index"], "start": table_entry["start"], "size": table_entry["size"], "edits": edits}
