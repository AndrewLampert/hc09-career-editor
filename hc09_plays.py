"""
The game's plays as data, and building custom plays from them (a prototype of the in-game Create-A-Play, done outside the game).

Standard library only (no Tk), so it can be tested on its own. The data is exported from the game's archives by the bridge
(play-sets-scan --tables ...) and read here from CSV. How a play is stored (see docs/hc09_play_data.md):

- PBPL: one row per play (SETL the set it is run from, PLYL the play, PLYT the play type, name, motion flag, ...).
- SETL / SETP / SETG / SGFF: the set (formation alignment): 11 slots with a position (EPos) and depth (DPos), where each lines up (artx / arty in
  the diagram's units, SETG in yards as floats), and the alignment variants for pre-snap motion.
- PLYS: one row per slot of a play: PSAL (the assignment: a step list in PSLO for offense, PSLD for defense), ARTL (the diagram art in ARTO / ARTD)
  and PLRR (a role code).
- PSLO / PSLD: the step lists, rows (PSAL, step, code, val1, val2, val3), each list ending with code 255.
- ARTO / ARTD: the art, up to 12 numbered records of (sp, ls, at, ct, lt, au, av, ax, ay); (ax, ay) is where the line goes, as a signed offset from the
  player's position, ct 3 on defense is a zone, at 1 an arrowhead. The columns are signed integers of different widths (see ART_BITS); the bridge
  exports them as raw unsigned numbers, so they are sign-extended here.
- PLPD (pass plays: the read order, 5 x percent + receiver slot), PLRD (run plays: the hole), PLCM (combinations, option decisions).

A custom play (what the in-game Create-A-Play writes to the profile save) is a PBPL row and a SETL row in the formation 8190 ("Created Plays"), 11 SETP,
SETG and PLYS rows, a SGFF row per alignment group, and the PLPD / PLRD / PLCM row of its type; every PSAL and ARTL in its PLYS rows is one of the game's
own (the in-game editor offers 138 of the 1,403 step lists; the stock plays use the others, including the option reads). In the career, the play is linked
into a custom playbook by PGPL, PGSS, PGSL and PGFM rows. build_custom_play() and career_link_rows() make those rows.
"""
import collections
import csv
import os
import struct

ART_TAGS = ("10", "01", "11", "02", "12", "03", "04", "05", "06", "07", "08", "09")
# bit widths of the signed columns of each art record (from the table definition): (au, av, ax, ay)
ART_BITS = {"10": (8, 3, 8, 7), "11": (2, 2, 8, 7), "12": (2, 2, 8, 5), "01": (9, 8, 8, 8), "02": (9, 8, 9, 8), "03": (9, 8, 9, 8),
            "04": (8, 8, 9, 8), "05": (8, 7, 8, 8), "06": (6, 8, 8, 8), "07": (4, 7, 8, 8), "08": (2, 2, 8, 8), "09": (2, 2, 8, 7)}
POSITIONS = {0: "QB", 1: "HB", 2: "FB", 3: "WR", 4: "TE", 5: "LT", 6: "LG", 7: "C", 8: "RG", 9: "RT",
             10: "LE", 11: "RE", 12: "DT", 13: "LOLB", 14: "MLB", 15: "ROLB", 16: "CB", 17: "FS", 18: "SS"}
CREATED_FORMATION = 8190          # "Created Plays": the formation the game files its custom plays under
OPTION_CODES = (36, 37, 42, 43)   # step codes found (almost) only in option plays: 42 and 43 in 100% of their uses, 36 and 37 in 96%
# What a step code does, where it could be told from the plays that use it. These are read from the data, not from the game's code: "likely".
STEP_HINTS = {
    23: "deep zone", 22: "curl / flat zone", 24: "hook zone", 41: "pass rush", 15: "block", 14: "run block (likely)",
    8: "run a route leg", 9: "cut (turn)", 10: "end of route (likely)", 255: "end of list",
    42: "option read (option plays only)", 43: "option pitch path (option plays only)", 36: "option (option plays only)", 37: "option (option plays only)",
}


def signed(value, bits):
    value = int(value)
    return value - (1 << bits) if value >= (1 << (bits - 1)) else value


def read_csv(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def float_bits(u):
    """The float stored in a SETG column that the bridge exports as its raw 32 bits."""
    return struct.unpack(">f", struct.pack(">I", int(u) & 0xFFFFFFFF))[0]


def bits_of_float(x):
    return struct.unpack(">I", struct.pack(">f", float(x)))[0]


def decode_art(row):
    """The points of an art row: [{"tag", "sp", "ls", "at", "ct", "lt", "au", "av", "ax", "ay"}] for the records that are used (sp not 0), in
    drawing order, with the offsets as signed numbers."""
    pts = []
    for tag in ART_TAGS:
        sp = int(row.get("sp" + tag, 0) or 0)
        if sp == 0:
            continue
        bau, bav, bax, bay = ART_BITS[tag]
        pts.append({"tag": tag, "sp": sp, "ls": int(row["ls" + tag]), "at": int(row["at" + tag]), "ct": int(row["ct" + tag]), "lt": int(row["lt" + tag]),
                    "au": signed(row["au" + tag], bau), "av": signed(row["av" + tag], bav), "ax": signed(row["ax" + tag], bax), "ay": signed(row["ay" + tag], bay)})
    return pts


def step_text(steps):
    return " ".join(("end" if code == 255 else f"{code}({v1},{v2},{v3})" if (v1 or v2 or v3) else f"{code}") for code, v1, v2, v3 in steps if code != 255) or "-"


class PlayLibrary:
    """Plays, sets, assignments and art of the game, from the tables of the master play database (qkl_boot.ast entry 40)."""

    def __init__(self, tables):
        t = {k: tables.get(k, []) for k in ("PBPL", "SETL", "SETP", "SETG", "SGFF", "PLYS", "PSLO", "PSLD", "ARTO", "ARTD", "PLPD", "PLRD", "PLCM", "PBAI", "FORM")}
        self.tables = t
        self.sets = {}
        for r in t["SETL"]:
            self.sets[int(r["SETL"])] = {"setl": int(r["SETL"]), "name": r["name"], "form": int(r["FORM"]), "motn": int(r["MOTN"]), "sett": int(r["SETT"]),
                                         "sitt": int(r["SITT"]), "slots": []}
        for r in sorted(t["SETP"], key=lambda r: (int(r["SETL"]), int(r["poso"]))):
            s = self.sets.get(int(r["SETL"]))
            if s is not None:
                s["slots"].append({"setp": int(r["SETP"]), "poso": int(r["poso"]), "epos": int(r["EPos"]), "dpos": int(r["DPos"]), "x": int(r["artx"]), "y": int(r["arty"]),
                                   "fmtx": int(r["fmtx"]), "fmty": int(r["fmty"]), "sgt": int(r["SGT_"]), "arti": int(r["arti"]), "tabo": int(r["tabo"])})
        for s in self.sets.values():
            epos = [x["epos"] for x in s["slots"]]
            s["side"] = "offense" if 0 in epos else ("defense" if epos and all(10 <= e <= 18 for e in epos) else "other")
        self.form_names = {int(r["FORM"]): r["name"] for r in t["FORM"]}
        self.plays = {}
        for r in t["PBPL"]:
            self.plays[int(r["PLYL"])] = {"plyl": int(r["PLYL"]), "setl": int(r["SETL"]), "name": r["name"], "plyt": int(r["PLYT"]), "plf": int(r["PLF_"]), "risk": int(r["risk"]),
                                          "motn": int(r["motn"]), "vpos": int(r["vpos"]), "sitt": int(r["SITT"])}
        self.slot_rows = collections.defaultdict(dict)
        for r in t["PLYS"]:
            self.slot_rows[int(r["PLYL"])][int(r["poso"])] = {"psal": int(r["PSAL"]), "artl": int(r["ARTL"]), "plrr": int(r["PLRR"])}
        self.steps, self.step_side = {}, {}
        for side, rows in (("offense", t["PSLO"]), ("defense", t["PSLD"])):
            by = collections.defaultdict(list)
            for r in rows:
                by[int(r["PSAL"])].append((int(r["step"]), int(r["code"]), int(r["val1"]), int(r["val2"]), int(r["val3"])))
            for psal, lst in by.items():
                self.steps[psal] = [x[1:] for x in sorted(lst)]
                self.step_side[psal] = side
        self.art_rows, self.art_side = {}, {}
        for side, rows in (("offense", t["ARTO"]), ("defense", t["ARTD"])):
            for r in rows:
                self.art_rows[int(r["ARTL"])] = r
                self.art_side[int(r["ARTL"])] = side
        self.passing = {int(r["PLYL"]): r for r in t["PLPD"]}
        self.running = collections.defaultdict(list)
        for r in t["PLRD"]:
            self.running[int(r["PLYL"])].append(r)
        self.combos = {int(r["PLYL"]): r for r in t["PLCM"]}
        self.books_of_play = collections.defaultdict(set)
        for r in t["PBAI"]:
            self.books_of_play[int(r["PBPL"])].add(int(r["BOKL"]))
        self._usage = None

    # ---- plays
    def play_side(self, plyl):
        return self.sets[self.plays[plyl]["setl"]]["side"] if self.plays[plyl]["setl"] in self.sets else "other"

    def play_list(self, side=None):
        out = []
        for plyl, p in self.plays.items():
            s = self.sets.get(p["setl"])
            if s is None or (side and s["side"] != side):
                continue
            out.append({"plyl": plyl, "name": p["name"], "set": s["name"], "form": self.form_names.get(s["form"], f"formation {s['form']}"), "plyt": p["plyt"], "motn": p["motn"],
                        "option": self.play_is_option(plyl), "books": len(self.books_of_play.get(plyl, ())), "side": s["side"]})
        return sorted(out, key=lambda r: (r["name"].lower(), r["plyl"]))

    def play_is_option(self, plyl):
        return any(c in OPTION_CODES for poso in self.slot_rows.get(plyl, {}).values() for c, *_ in self.steps.get(poso["psal"], ()))

    def detail(self, plyl):
        """A play with its slots: [{poso, epos, dpos, label, x, y, psal, artl, plrr, steps, text, art}] and the play's own columns."""
        p = self.plays[plyl]
        s = self.sets[p["setl"]]
        slots = []
        for sl in s["slots"]:
            row = self.slot_rows.get(plyl, {}).get(sl["poso"])
            if row is None:
                continue
            steps = self.steps.get(row["psal"], [])
            art = decode_art(self.art_rows[row["artl"]]) if row["artl"] in self.art_rows else []
            slots.append({**sl, "label": POSITIONS.get(sl["epos"], str(sl["epos"])) + (str(sl["dpos"]) if sl["epos"] in (1, 2, 3, 4) or 10 <= sl["epos"] <= 18 else ""),
                          "psal": row["psal"], "artl": row["artl"], "plrr": row["plrr"], "steps": steps, "text": step_text(steps), "art": art})
        return {"play": p, "set": s, "slots": slots, "side": s["side"], "passing": self.passing.get(plyl), "running": self.running.get(plyl, []), "combo": self.combos.get(plyl),
                "option": any(c in OPTION_CODES for sl in slots for c, *_ in sl["steps"])}

    def drawing(self, slots, side):
        """What to draw for a play's slots, in the diagram's units: {"players": [{poso, label, x, y}], "lines": [{poso, points, arrow, ct, lt}], "zones": [{poso, x, y, ct}]}.
        A route is the player's position then each art point (the offsets are from the position); on defense an art point of type ct 3 is a zone, with a line to it."""
        players, lines, zones = [], [], []
        for sl in slots:
            players.append({"poso": sl["poso"], "label": sl["label"], "x": sl["x"], "y": sl["y"], "epos": sl["epos"]})
            pts = [(sl["x"], sl["y"])]
            arrow, ct, lt = False, 0, 0
            for q in sl["art"]:
                if q["ax"] == 0 and q["ay"] == 0 and q["ct"] != 3:
                    continue
                pt = (sl["x"] + q["ax"], sl["y"] + q["ay"])
                if q["ct"] == 3 and side == "defense":
                    zones.append({"poso": sl["poso"], "x": pt[0], "y": pt[1], "ct": q["ct"]})
                pts.append(pt)
                arrow = arrow or bool(q["at"])
                ct, lt = q["ct"], q["lt"]
            if len(pts) > 1:
                lines.append({"poso": sl["poso"], "points": pts, "arrow": arrow, "ct": ct, "lt": lt})
        return {"players": players, "lines": lines, "zones": zones}

    # ---- assignments
    def usage(self):
        """{PSAL: {"uses": slots using it, "plays": set of plays, "epos": Counter of the positions using it, "artl": Counter of the art it is drawn with,
        "plrr": Counter of the role codes}} over the stock plays."""
        if self._usage is None:
            u = {}
            for plyl, slots in self.slot_rows.items():
                s = self.sets.get(self.plays.get(plyl, {}).get("setl"))
                if s is None:
                    continue
                epos = {x["poso"]: x["epos"] for x in s["slots"]}
                for poso, row in slots.items():
                    e = u.setdefault(row["psal"], {"uses": 0, "plays": set(), "epos": collections.Counter(), "artl": collections.Counter(), "plrr": collections.Counter()})
                    e["uses"] += 1
                    e["plays"].add(plyl)
                    e["epos"][epos.get(poso, -1)] += 1
                    e["artl"][row["artl"]] += 1
                    e["plrr"][row["plrr"]] += 1
            self._usage = u
        return self._usage

    def library(self, side=None):
        """Every step list of the game as an entry {psal, side, steps, text, uses, plays, epos, artl, plrr, option, cap_only (no stock play uses it)}, ordered by id."""
        u = self.usage()
        out = []
        for psal, steps in self.steps.items():
            if side and self.step_side[psal] != side:
                continue
            e = u.get(psal)
            out.append({"psal": psal, "side": self.step_side[psal], "steps": steps, "text": step_text(steps), "uses": e["uses"] if e else 0, "plays": len(e["plays"]) if e else 0,
                        "epos": e["epos"] if e else collections.Counter(), "artl": e["artl"] if e else collections.Counter(), "plrr": e["plrr"] if e else collections.Counter(),
                        "option": any(c in OPTION_CODES for c, *_ in steps), "cap_only": e is None})
        return sorted(out, key=lambda r: r["psal"])

    def entry_art(self, entry):
        """The art that goes with a library entry: the one used most with it (None for an entry no stock play uses)."""
        return entry["artl"].most_common(1)[0][0] if entry["artl"] else None

    def entry_role(self, entry):
        return entry["plrr"].most_common(1)[0][0] if entry["plrr"] else 2


# ---------- building a custom play (the rows the in-game Create-A-Play writes to the profile save)
def next_ids(profile):
    """The first free ids in a profile's custom-play tables: {"SETL", "PLYL", "SETP", "SGF_"} from {table: rows}."""
    def top(table, col):
        return max([int(r[col]) for r in profile.get(table, [])] or [0]) + 1
    return {"SETL": top("SETL", "SETL"), "PLYL": top("PBPL", "PLYL"), "SETP": top("SETP", "SETP"), "SGF_": top("SGFF", "SGF_")}


def build_custom_play(lib, base_plyl, name, overrides, profile, plyt=None):
    """The rows of a new custom play made from the stock play base_plyl: {table: [row dicts with every column of that table as strings]} for the
    profile save (PBPL, SETL, SETP, SETG, SGFF, PLYS, and PLPD / PLRD / PLCM when the base play has them), and a summary.
    overrides: {poso: (PSAL, ARTL, PLRR)} replaces a slot's assignment with any step list of the game (PSAL, ARTL and PLRR taken from library entries).
    The alignment is the stock set's, in the diagram's units (a custom set keeps the diagram coordinates in both the formation and the art columns); each of
    the set's alignment groups (the normal one and the pre-snap motion variants) is copied with its SETG rows. Ids come after the profile's own."""
    d = lib.detail(base_plyl)
    base, bset = d["play"], d["set"]
    if len(name) > 24 or not name.strip():
        raise ValueError("A play name is 1 to 24 characters.")
    ids = next_ids(profile)
    new_setl, new_plyl = ids["SETL"], ids["PLYL"]
    if new_setl > 511 or new_plyl > 16383:
        raise ValueError("The profile has no free set or play ids left.")
    rows = collections.defaultdict(list)
    ptype = plyt if plyt is not None else base["plyt"]
    rows["PBPL"].append({"SETL": new_setl, "PLYL": new_plyl, "SITT": 2, "PLYT": ptype, "PLF_": base["plf"], "name": name, "risk": 0, "motn": base["motn"], "vpos": base["vpos"]})
    rows["SETL"].append({"SETL": new_setl, "FORM": CREATED_FORMATION, "MOTN": bset["motn"], "SETT": bset["sett"], "SITT": 0, "SLF_": 0, "name": "Created", "poso": 0})
    setp_ids = {}
    for i, sl in enumerate(bset["slots"]):
        setp_ids[sl["setp"]] = ids["SETP"] + i
        rows["SETP"].append({"SETL": new_setl, "SETP": ids["SETP"] + i, "SGT_": 0, "arti": 5 if sl["epos"] == 7 else 4, "opnm": 0, "tabo": sl["tabo"], "poso": sl["poso"], "odep": 0,
                             "flas": 0, "DPos": sl["dpos"], "EPos": sl["epos"], "fmtx": sl["x"], "artx": sl["x"], "fmty": sl["y"], "arty": sl["y"]})
    groups = [g for g in lib.tables["SGFF"] if int(g["SETL"]) == bset["setl"]]
    group_map = {}
    for i, g in enumerate(sorted(groups, key=lambda g: -int(g["dflt"]))):
        group_map[int(g["SGF_"])] = ids["SGF_"] + i
        rows["SGFF"].append({"SETL": new_setl, "SGF_": ids["SGF_"] + i, "name": g["name"], "dflt": g["dflt"]})
    for g in lib.tables["SETG"]:
        if int(g["SETP"]) in setp_ids and int(g["SGF_"]) in group_map:
            rows["SETG"].append({"SETP": setp_ids[int(g["SETP"])], "SGF_": group_map[int(g["SGF_"])], "SF__": g["SF__"], "x___": g["x___"], "y___": g["y___"], "fx__": g["fx__"],
                                 "fy__": g["fy__"], "anm_": g["anm_"], "dir_": g["dir_"], "fanm": g["fanm"], "fdir": g["fdir"]})
    for sl in d["slots"]:
        psal, artl, plrr = overrides.get(sl["poso"], (sl["psal"], sl["artl"], sl["plrr"]))
        if psal not in lib.steps:
            raise ValueError(f"Step list {psal} is not one of the game's.")
        rows["PLYS"].append({"PSAL": psal, "ARTL": artl, "PLYL": new_plyl, "PLRR": plrr, "poso": sl["poso"]})
    for table, src in (("PLPD", lib.passing.get(base_plyl)), ("PLCM", lib.combos.get(base_plyl))):
        if src is not None:
            rows[table].append({**{k: v for k, v in src.items() if k != "PLYL"}, "PLYL": new_plyl})
    for r in lib.running.get(base_plyl, []):
        rows["PLRD"].append({"PLYL": new_plyl, "hole": r["hole"]})
    summary = {"setl": new_setl, "plyl": new_plyl, "name": name, "plyt": ptype, "from": base["name"], "slots_changed": sorted(overrides), "rows": {k: len(v) for k, v in rows.items()}}
    return dict(rows), summary


def career_link_rows(career, bokl, new_setl, new_plyl, plyt):
    """The rows that put a custom play into custom playbook bokl in a career save: PGPL, PGSS, PGSL, and PGFM for the "Created Plays" formation if that
    playbook has none yet. {table: [rows]}."""
    rows = {"PGPL": [{"BOKL": bokl, "SETL": new_setl, "PLYL": new_plyl, "PLTP": plyt}], "PGSS": [{"BOKL": bokl, "SETL": new_setl}],
            "PGSL": [{"BOKL": bokl, "SETL": new_setl, "PBFM": CREATED_FORMATION}]}
    if not any(int(r["BOKL"]) == bokl and int(r["PBFM"]) == CREATED_FORMATION for r in career.get("PGFM", [])):
        rows["PGFM"] = [{"BOKL": bokl, "PBFM": CREATED_FORMATION, "SRFM": CREATED_FORMATION}]
    return rows
