"""
Changing a play of the game itself (a stock play) in the game's own files, so that the game treats it as a normal play: it can be flipped, hot-routed and audibled, the quarterback
adjusts, and the CPU calls it with the chances the play already has. A custom play made in the profile and career is a "created play" for the game and has none of that.

The game's play database has no free rows (every table is exactly full), so a play is put IN PLACE of another: the same rows get other values. Nothing is added or taken out, which is
also why a change that needs another number of rows (a pass made a run: pass reads give way to a run hole) is refused. A play is built from a BASE play (what the Play creator shows) and
written over a TARGET play of the same set (the base itself, or another play of its set that the player gives up), with a new name. The database is kept in several places (the master in
qkl_boot.ast entry 40, a compact copy in entry 42, subsets in the Create-A-Play databases of qkl_fe2ig.ast, and the playbooks' own names for the plays in entry 46); every copy that holds
the play gets the same change, like the Set personnel tool.

Standard library only (no Tk). changes_for() works out what changes from the Play creator's state; targets_for() turns it into bridge entry-patch targets, one per copy.
"""
import csv
import os

import hc09_plays as P

PLPD_COLS = tuple(f"{a}{k}" for k in range(1, 6) for a in ("per", "rcv"))
PLCM_COLS = tuple(f"{a}{k}" for k in range(1, 6) for a in ("per", "dir", "ply"))
SCAN_TABLES = "PBPL,PLYL,PLYS,PLPD,PLRD,PLCM,SETP,SETG,SGFF,PBAI,PSLO,ARTO"          # PSLO / ARTO: the offense step lists (column PSAL) and art (column ARTL) a copy holds
NAMES_ENTRY = 46                     # the entry of qkl_boot.ast that holds PPPN: the names the playbooks give their plays (the play-call screen shows these)
PLAY_COLS = ("PLYT", "PLF_", "vpos", "risk", "motn")      # the columns of a play's own row that follow the play built (PBAI rows clone PLYT, PLF_ and vpos)


def clean_name(name):
    """A play's name as the game can hold it: 1 to 24 printable ASCII characters."""
    name = (name or "").strip()
    if not 1 <= len(name) <= 24 or any(ord(c) < 32 or ord(c) > 126 for c in name):
        raise ValueError("A play name is 1 to 24 letters, digits and ordinary signs.")
    return name


def _new_rows(lib, base, overrides, plan, reads, alignment):
    d = lib.detail(base)
    if d["side"] != "offense":
        raise ValueError("Only offensive plays can be written into the game files for now.")
    new, _summary = P.build_custom_play(lib, base, "x", overrides, {}, plan=plan, reads=reads, alignment=alignment)
    return d, new


def candidates(lib, base, overrides, plan=None, reads=None, alignment=None):
    """The plays that the play made from base can be written over: the base itself first, then the other plays of its set that have the same kind (the same play type and the same
    pass-read, run-hole and combination rows, because the tables have no free rows), fewest playbooks first. [(plyl, name, number of playbooks)]."""
    d, new = _new_rows(lib, base, overrides, plan, reads, alignment)
    setl, plyt = d["set"]["setl"], int(new["PBPL"][0]["PLYT"])
    shape = (bool(new.get("PLPD")), len(new.get("PLRD") or []), bool(new.get("PLCM")))
    out = []
    for q in lib.plays.values():
        if q["setl"] != setl or q["plyl"] == base or q["plyt"] != plyt:
            continue
        if (q["plyl"] in lib.passing, len(lib.running.get(q["plyl"]) or []), q["plyl"] in lib.combos) != shape:
            continue
        out.append((q["plyl"], q["name"], len(lib.books_of_play.get(q["plyl"], ()))))
    out.sort(key=lambda t: (t[2], t[1].lower(), t[0]))
    return [(base, lib.plays[base]["name"], len(lib.books_of_play.get(base, ())))] + out


def changes_for(lib, base, overrides, plan=None, reads=None, alignment=None, target=None, name=None):
    """What has to change in the game's rows for the play TARGET (default: the base play itself) to become the play the Play creator shows for base (overrides: {slot: (PSAL, ARTL, PLRR)},
    plan: a kind conversion, reads: [(slot, chance)] x5, alignment: {slot: (x, y)} yards), with the new name if one is given. Returns {"plyl" (the target), "base", "setl", "name",
    "plys": {slot: {col: value}}, "play": {col: value}, "plpd", "plrd", "plcm": {col: value}, "setp": {slot: {col: v}}, "setg": {slot: {col: v}}, "default_group", "shared_with":
    [(plyl, name)], "playbooks": number of playbooks that have the target} with only the values that differ from the target's rows. Raises ValueError for a play that cannot be changed in
    place."""
    target = base if target is None else target
    d, new = _new_rows(lib, base, overrides, plan, reads, alignment)
    st = d["set"]
    if target not in lib.plays or lib.plays[target]["setl"] != st["setl"]:
        raise ValueError("A play can only be written over a play of the same set (the set is the formation's alignment).")
    tplay = lib.plays[target]
    out = {"plyl": target, "base": base, "setl": st["setl"], "name": None, "plys": {}, "play": {}, "plpd": {}, "plrd": {}, "plcm": {}, "setp": {}, "setg": {}, "default_group": None,
           "shared_with": [], "playbooks": len(lib.books_of_play.get(target, ())), "target_name": tplay["name"]}
    if name is not None:
        want = clean_name(name)
        if want != tplay["name"].strip():
            out["name"] = want
    for nr in new["PLYS"]:
        poso = int(nr["poso"])
        old = lib.slot_rows[target][poso]
        diff = {c: int(nr[c]) for c, o in (("PSAL", old["psal"]), ("ARTL", old["artl"]), ("PLRR", old["plrr"])) if int(nr[c]) != o}
        if diff:
            out["plys"][poso] = diff
    nb = new["PBPL"][0]
    stock = {"PLYT": tplay["plyt"], "PLF_": tplay["plf"], "vpos": tplay["vpos"], "risk": tplay["risk"], "motn": tplay["motn"]}
    for col in PLAY_COLS:
        if col == "PLYT":
            want_it = plan is not None or target != base
        elif col == "vpos":
            want_it = reads is not None or plan is not None or target != base          # the primary receiver follows the reads (see build_custom_play)
        else:
            want_it = target != base                                                    # flags, risk, motion: the target keeps its own unless the play of another is written over it
        if want_it and int(nb[col]) != stock[col]:
            out["play"][col] = int(nb[col])
    for key, table, have, cols in (("plpd", "PLPD", lib.passing.get(target), PLPD_COLS), ("plcm", "PLCM", lib.combos.get(target), PLCM_COLS)):
        want = (new.get(table) or [None])[0]
        if (have is None) != (want is None):
            raise ValueError(f"Making the play this kind needs {'a' if want else 'no'} {table} row and the game's play has {'none' if have is None else 'one'}: the game's tables have no free rows, so it cannot be done in place. "
                             "Make it a custom play instead.")
        if have is not None:
            diff = {c: int(want[c]) for c in cols if int(want[c]) != int(have[c])}
            if diff:
                out[key] = diff
    have_run, want_run = lib.running.get(target) or [], new.get("PLRD") or []
    if len(have_run) != len(want_run):
        raise ValueError("Making the play this kind needs another number of run-hole rows (PLRD) than the game's play has, so it cannot be done in place. Make it a custom play instead.")
    if have_run and int(want_run[0]["hole"]) != int(have_run[0]["hole"]):
        out["plrd"] = {"hole": int(want_run[0]["hole"])}
    slots = {s["poso"]: s for s in st["slots"]}
    stock_al = lib.alignment(st["setl"])
    moved = {poso for poso, (x, y) in (alignment or {}).items() if poso in stock_al and (abs(float(x) - stock_al[poso]["x"]) > 0.001 or abs(float(y) - stock_al[poso]["y"]) > 0.001)}
    for nr in new["SETP"]:
        poso = int(nr["poso"])
        if poso not in moved:
            continue                          # only the diagram's place of a moved player (artx, arty); the formation columns (fmtx, fmty) are design-time values of the stock set and stay
        sl = slots[poso]
        diff = {c: int(nr[c]) for c, o in (("artx", sl["x"]), ("arty", sl["y"])) if int(nr[c]) != o}
        if diff:
            out["setp"][poso] = diff
    dflt = next((int(g["SGF_"]) for g in lib.tables["SGFF"] if int(g["SETL"]) == st["setl"] and g["dflt"] == "1"), None)
    out["default_group"] = dflt
    if dflt is not None and out["setp"]:
        poso_of_new = {int(r["SETP"]): int(r["poso"]) for r in new["SETP"]}
        new_dflt = next((int(g["SGF_"]) for g in new["SGFF"] if g["dflt"] == "1"), None)
        setp_of = {s["setp"]: s["poso"] for s in st["slots"]}
        stock_rows = {setp_of[int(r["SETP"])]: r for r in lib.tables["SETG"] if int(r["SGF_"]) == dflt and int(r["SETP"]) in setp_of}
        for nr in new["SETG"]:
            if int(nr["SGF_"]) != new_dflt:
                continue
            poso = poso_of_new[int(nr["SETP"])]
            old = stock_rows.get(poso)
            if old is None:
                continue
            diff = {c: int(nr[c]) for c in ("x___", "y___", "fx__", "fy__") if int(nr[c]) != int(old[c])}
            if diff:
                out["setg"][poso] = diff
    out["shared_with"] = sorted(((q["plyl"], q["name"]) for q in lib.plays.values() if q["setl"] == st["setl"] and q["plyl"] != target), key=lambda t: (t[1].lower(), t[0]))
    return out


def is_empty(changes):
    return not (changes["name"] or any(changes[k] for k in ("plys", "play", "plpd", "plrd", "plcm", "setp", "setg")))


def _read(cache_dir, base, table):
    path = os.path.join(cache_dir, f"{table.lower()}_{base}.csv")
    if not os.path.isfile(path):
        return None
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _text(value):
    """Text of a column as the database holds it: up to the first control character (the pool the strings sit in runs on past the text)."""
    for i, ch in enumerate(value or ""):
        if ord(ch) < 32:
            return value[:i].strip()
    return (value or "").strip()


def is_master(c, copies):
    """Is this copy the master play database? By what it holds when the scan says (the copy with the most PLYS rows, as the Play creator's library picks it), else by the PS3 game's entry number
    (qkl_boot.ast entry 40): another version of the game numbers its entries differently."""
    if all(isinstance(x.get("tables"), dict) for x in copies) and copies:
        return c is max(copies, key=lambda x: x["tables"].get("PLYS", 0))
    return c["file"] == "qkl_boot.ast" and c["index"] == 40


def targets_for(copies, cache_dir, changes, names_entry=None, names_rows=None):
    """Bridge entry-patch targets (one per copy of the play database that holds the play or its set) for the changes of changes_for(), read from the scan the bridge made of the copies
    (play-sets-scan with SCAN_TABLES, into cache_dir). Each edit carries the value the copy has now (expect) so that nothing is written over a row that is not what was read. The
    new name also goes into the playbooks' own names for the play: names_entry = {ast, index, start, size} of the entry that holds PPPN and names_rows its rows [{BOKL, PLYL, PPPM}].
    Returns (targets, report) where report is [(copy name, number of values)]. Raises ValueError when the master copy does not hold the play."""
    plyl, setl, dflt = changes["plyl"], changes["setl"], changes["default_group"]
    targets, report, master_has, skipped = [], [], False, []
    for c in copies:
        edits = []

        def add(table, match, want, row):
            want = {k: v for k, v in want.items() if k in row}            # a compact copy may lack some columns
            cur = {k: int(row[k]) for k in want}
            set_ = {k: int(v) for k, v in want.items() if int(v) != cur[k]}
            if set_:
                edits.append({"table": table, "match": {k: int(v) for k, v in match.items()}, "expect": {k: cur[k] for k in set_}, "set": set_})
        play_table, play_rows = None, None
        for table in ("PBPL", "PLYL"):
            rows = _read(cache_dir, c["base"], table)
            if rows is not None and rows and "PLYL" in rows[0]:
                play_table, play_rows = table, rows
                break
        mine = next((r for r in (play_rows or []) if int(r["PLYL"]) == plyl), None)      # None: this copy does not hold the play (it may still hold its set)
        if mine is not None and is_master(c, copies):
            master_has = True
        if mine is not None:
            if changes["play"]:
                add(play_table, {"PLYL": plyl}, changes["play"], mine)
            if changes["name"] and "name" in mine and _text(mine["name"]) != changes["name"]:
                edits.append({"table": play_table, "match": {"PLYL": plyl}, "expect": {"name": _text(mine["name"])}, "set": {"name": changes["name"]}})
            plys = {(int(r["PLYL"]), int(r["poso"])): r for r in (_read(cache_dir, c["base"], "PLYS") or [])}
            steps, arts = _read(cache_dir, c["base"], "PSLO"), _read(cache_dir, c["base"], "ARTO")      # PSAL and ARTL are COLUMNS; the tables are PSLO (offense step lists) and ARTO (offense art)
            have_steps = {int(r["PSAL"]) for r in steps} if steps else None        # None: the copy has no such table (a Create-A-Play copy) and cannot be checked
            have_arts = {int(r["ARTL"]) for r in arts} if arts else None
            for poso, want in changes["plys"].items():
                row = plys.get((plyl, poso))
                if row is None:
                    continue
                # a CHANGED step list or drawing is written only where the copy is known to hold it: a play must not point at one the copy lacks (or cannot be checked for)
                new_step = "PSAL" in want and "PSAL" in row and int(want["PSAL"]) != int(row["PSAL"])
                new_art = "ARTL" in want and "ARTL" in row and int(want["ARTL"]) != int(row["ARTL"])
                if (new_step and (have_steps is None or int(want["PSAL"]) not in have_steps)) or (new_art and (have_arts is None or int(want["ARTL"]) not in have_arts)):
                    skipped.append((f"{c['file']} #{c['index']}", poso))
                    continue
                add("PLYS", {"PLYL": plyl, "poso": poso}, want, row)
            for key, table in (("plpd", "PLPD"), ("plcm", "PLCM"), ("plrd", "PLRD")):
                if changes[key]:
                    rows = [r for r in (_read(cache_dir, c["base"], table) or []) if int(r["PLYL"]) == plyl]
                    if len(rows) == 1:
                        add(table, {"PLYL": plyl}, changes[key], rows[0])
        setp_rows = {(int(r["SETL"]), int(r["poso"])): r for r in (_read(cache_dir, c["base"], "SETP") or [])}
        setg_rows = {(int(r["SETP"]), int(r["SGF_"])): r for r in (_read(cache_dir, c["base"], "SETG") or [])}
        for poso in sorted(set(changes["setp"]) | set(changes["setg"])):
            row = setp_rows.get((setl, poso))
            if row is None:
                continue
            art = {k: v for k, v in changes["setp"].get(poso, {}).items() if k in row}
            if art:
                add("SETP", {"SETL": setl, "poso": poso}, art, row)
            yards = changes["setg"].get(poso, {})
            if yards:
                if "x___" in row:                                    # the compact copy holds the yards in the slot's own row
                    add("SETP", {"SETL": setl, "poso": poso}, {k: v for k, v in yards.items() if k in ("x___", "y___")}, row)
                elif "SETP" in row and dflt is not None and (int(row["SETP"]), dflt) in setg_rows:
                    add("SETG", {"SETP": int(row["SETP"]), "SGF_": dflt}, yards, setg_rows[(int(row["SETP"]), dflt)])
        if changes["play"] and mine is not None:
            for r in (_read(cache_dir, c["base"], "PBAI") or []):
                if int(r["PBPL"]) == plyl:
                    add("PBAI", {k: r[k] for k in ("BOKL", "PBPL", "SETL", "AIGR", "prct")}, {k: v for k, v in changes["play"].items() if k in ("PLYT", "PLF_", "vpos") and k in r}, r)
        if edits:
            targets.append({"ast": c["ast"], "index": c["index"], "start": c["start"], "size": c["size"], "edits": edits})
            report.append((f"{c['file']} #{c['index']}", sum(len(e["set"]) for e in edits)))
    if not master_has:
        raise ValueError("The play is not in the master play database of the game files that were read.")
    if changes["name"] and names_entry and names_rows:
        edits = [{"table": "PPPN", "match": {"BOKL": int(r["BOKL"]), "PLYL": plyl}, "expect": {"PPPM": _text(r["PPPM"])}, "set": {"PPPM": changes["name"]}}
                 for r in names_rows if int(r["PLYL"]) == plyl and _text(r["PPPM"]) != changes["name"]]
        if edits:
            targets.append({"ast": names_entry["ast"], "index": names_entry["index"], "start": names_entry["start"], "size": names_entry["size"], "edits": edits})
            report.append((f"{os.path.basename(names_entry['ast'])} #{names_entry['index']} (the playbooks' names for the play)", len(edits)))
    if skipped:
        report.append(("not written (the copy does not hold that step list or drawing, or has none to check against): " + ", ".join(f"{n} slot {p}" for n, p in skipped), 0))
    return targets, report


def describe(lib, changes):
    """The changes in words, one line each (for the window that asks before anything is written)."""
    d = lib.detail(changes["base"])
    label = {s["poso"]: s["label"] for s in d["slots"]}
    lines = []
    if changes["plyl"] != changes["base"]:
        lines.append(f"The play \"{changes['target_name']}\" is given up: its place in {changes['playbooks']} playbook{'s' if changes['playbooks'] != 1 else ''} is taken by the new play.")
    if changes["name"]:
        lines.append(f"The name becomes \"{changes['name']}\" (in the play's own row and in the playbooks' names for it).")
    if changes["plys"]:
        lines.append("What these players do: " + ", ".join(label[p] for p in sorted(changes["plys"])) + ".")
    if changes["play"].get("PLYT") is not None:
        lines.append(f"The kind of play (play type) becomes {changes['play']['PLYT']}. Careers that exist keep the old kind in their playbook links (harmless to play, new careers are right).")
    if changes["plpd"] or changes["play"].get("vpos") is not None:
        lines.append("The pass reads and the first read change.")
    if changes["plrd"]:
        lines.append(f"The run hole becomes {changes['plrd']['hole']}.")
    if changes["plcm"]:
        lines.append("The play combination row changes.")
    moved = sorted(changes["setp"])
    if moved:
        lines.append("Where these players line up: " + ", ".join(label[p] for p in moved) + ".")
        n = len(changes["shared_with"])
        lines.append(f"That is in the SET \"{d['set']['name']}\", which {n} other play{'s' if n != 1 else ''} also use{'' if n != 1 else 's'}: all of them line up that way (the set is the formation's alignment, not the play's)." if n else
                     f"The set \"{d['set']['name']}\" has only this play, so nothing else changes.")
    return lines
