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
own. The offense (PSLO) and defense (PSLD) tables number their step lists separately but overlap: 138 ids (2182 to 2343) are in both with identical lists and no
stock play uses them (the profile's custom plays use 22 of them, with art that varies per use); everything is therefore keyed by side. In the career, the play is
linked into a custom playbook by PGPL, PGSS, PGSL and PGFM rows. build_custom_play() and career_link_rows() make those rows.
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
# A profile's custom plays have ids of their own that can equal the game's (set 66, play 28 ...); mounted next to the game's plays they are moved up by these, which are above anything
# the game or a profile can have (sets go up to 511 in a profile, plays up to 16,383).
CUSTOM_OFFSETS = {"SETL": 10000, "PLYL": 100000, "SETP": 1000000, "SGF_": 1000000}
CUSTOM_TABLES = ("PBPL", "SETL", "SETP", "SETG", "SGFF", "PLYS", "PLPD", "PLRD", "PLCM")
CREATED_FORMATION = 8190          # "Created Plays": the formation the game files its custom plays under
# The game's own formation names (its FORM table, which lives in qkl_fe2ig.ast). Used for the ids the editor cannot read names for, for example when it did not find that archive.
FORMATION_NAMES = {1: "Shotgun", 2: "4-3", 3: "I Form", 4: "Strong I", 5: "Split Backs", 10: "Goal Line Offense", 11: "Singleback", 13: "Weak I", 14: "Near", 15: "Far", 16: "3-4",
                   17: "Nickel", 18: "Dime", 19: "Goal Line Defense", 36: "Quarter", 63: "Jumbo T", 67: "Full House", 95: "Flexbone", 103: "Pistol", 105: "Wishbone", 115: "Maryland I"}
OPTION_CODES = (36, 37, 42, 43)   # step codes found (almost) only in option plays: 42 and 43 in 100% of their uses, 36 and 37 in 96%
# What a step code does, read from the data (no documentation of it was found): which positions use it, whether the play is a pass or a run, what the play is
# called (a code found in every "trap" and "sweep" and nowhere else is a pull) and what comes before and after it. The code numbers overlap between the offense
# and the defense tables, but a code means the same in both where both use it (the 138 lists in both tables are identical), so a code missing from one table
# is read from the other. A "?" at the end marks a reading that fits the data but is not certain; a code that is not here shows as "step N".
# value: a phrase, or {"QB": phrase for the quarterback, "": phrase for anyone else}
STEP_TERMS = {
    "offense": {
        1: "carry the ball", 2: "then pursue (?)", 3: {"QB": "drop back", "": "release path (?)"}, 5: "carry out the fake (?)", 7: "read and throw",
        11: "pitch (?)", 12: "option start (?)", 13: "run through the hole (?)", 14: "pass block", 15: "run block", 18: "lead path (?)", 25: "wait",
        16: "kick (?)", 29: "punt (?)", 26: "go to the mesh point (?)", 32: "take the pitch (?)", 33: "pull (?)", 36: "option route read (?)", 37: "option route break (?)",
        38: "take the snap and turn (?)", 39: "hand off (?)", 40: "play-action fake (?)", 42: "option read", 43: "option pitch route (?)",
        45: "pre-snap motion", 46: "go at the snap (?)",
    },
    "defense": {
        2: "then pursue (?)", 3: "line slant / stunt (?)", 19: "man coverage", 20: "flat zone", 21: "hook zone", 22: "curl zone", 23: "deep zone",
        24: "wait and read (?)", 25: "wait", 26: "blitz path (?)", 34: "spy the quarterback", 41: "pass rush",
    },
}
ROUTE_TERMS = {8: "route leg", 9: "cut", 10: "look for the ball", 35: "curve in the route (?)"}
ROUTE_CODES = (8, 9, 10, 35)      # a run of these steps reads as one route (35 sits between route legs and in the backs' flare, swing and drag routes)


def signed(value, bits):
    value = int(value)
    return value - (1 << bits) if value >= (1 << (bits - 1)) else value


def cut_at_control(text):
    """A string out of the game's database as it should read: the pool the strings sit in runs on past the text, so everything from the first control character on is dropped."""
    for i, ch in enumerate(text or ""):
        if ord(ch) < 32:
            return text[:i].strip()
    return (text or "").strip()


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


def step_term(table, code, epos=None):
    """The words for a step code on a table ("offense" or "defense"), for a player at EPos epos (0 is the quarterback; None if not known), or None if the code is
    not understood."""
    term = STEP_TERMS[table].get(code)
    if term is None:
        term = STEP_TERMS["defense" if table == "offense" else "offense"].get(code)
    if isinstance(term, dict):
        return term["QB"] if epos == 0 else (term[""] if epos is not None else f"{term['QB']} / {term['']}")
    return term


def steps_in_words(steps, table="offense", epos=None):
    """A step list in plain words, "route: 2 legs, 1 cut, then look for the ball > run block"; codes that are not understood show as "step N"."""
    steps = [s for s in steps if s[0] != 255]
    out, i = [], 0
    while i < len(steps):
        if steps[i][0] in ROUTE_CODES:
            j = i
            while j < len(steps) and steps[j][0] in ROUTE_CODES:
                j += 1
            codes = [c for c, *_ in steps[i:j]]
            legs, cuts, curves = codes.count(8), codes.count(9), codes.count(35)
            parts = ([f"{legs} leg{'s' if legs != 1 else ''}"] if legs else []) + ([f"{cuts} cut{'s' if cuts != 1 else ''}"] if cuts else []) + \
                    ([f"{curves} curve{'s' if curves != 1 else ''} (?)"] if curves else [])
            text = ("route: " + ", ".join(parts)) if legs or curves else "route end"
            out.append(text + (", then look for the ball" if 10 in codes else ""))
            i = j
        else:
            out.append(step_term(table, steps[i][0], epos) or f"step {steps[i][0]}")
            i += 1
    runs = []                         # the same phrase twice in a row reads "x2"
    for text in out:
        if runs and runs[-1][0] == text:
            runs[-1][1] += 1
        else:
            runs.append([text, 1])
    return " > ".join(t + (f" x{n}" if n > 1 else "") for t, n in runs) or "nothing"


def step_meanings(steps, table="offense", epos=None):
    """["14 = pass block", ...] for the understood codes of a step list, each once, route steps included."""
    out = []
    for code in dict.fromkeys(c for c, *_ in steps if c != 255):
        word = ROUTE_TERMS.get(code) if code in ROUTE_CODES else step_term(table, code, epos)
        if word:
            out.append(f"{code} = {word}")
    return out


def step_text(steps):
    return " ".join(("end" if code == 255 else f"{code}({v1},{v2},{v3})" if (v1 or v2 or v3) else f"{code}") for code, v1, v2, v3 in steps if code != 255) or "-"


class PlayLibrary:
    """Plays, sets, assignments and art of the game, from the tables of the master play database (qkl_boot.ast entry 40)."""

    def __init__(self, tables):
        t = {k: tables.get(k, []) for k in ("PBPL", "SETL", "SETP", "SETG", "SGFF", "PLYS", "PSLO", "PSLD", "ARTO", "ARTD", "PLPD", "PLRD", "PLCM", "PBAI", "FORM")}
        self.tables = t
        self.sets = {}
        self.plays = {}
        self.slot_rows = collections.defaultdict(dict)
        self.passing = {}
        self.running = collections.defaultdict(list)
        self.combos = {}
        self.custom = {}                                     # {mounted PLYL: {"plyl", "setl" (as in the profile), "name"}} of the profile's custom plays, see mount_custom
        self._custom_rows = {}
        self._index_sets(t["SETL"], t["SETP"])
        self.form_names = {int(r["FORM"]): r["name"] for r in t["FORM"]}
        self.form_names.setdefault(CREATED_FORMATION, "Created Plays")
        for fid, fname in FORMATION_NAMES.items():
            self.form_names.setdefault(fid, fname)
        self._index_plays(t["PBPL"], t["PLYS"], t["PLPD"], t["PLRD"], t["PLCM"])
        self.steps = {"offense": {}, "defense": {}}          # side -> {PSAL: [(code, val1, val2, val3), ...]}: the two tables share id numbers
        for side, rows in (("offense", t["PSLO"]), ("defense", t["PSLD"])):
            by = collections.defaultdict(list)
            for r in rows:
                by[int(r["PSAL"])].append((int(r["step"]), int(r["code"]), int(r["val1"]), int(r["val2"]), int(r["val3"])))
            for psal, lst in by.items():
                self.steps[side][psal] = [x[1:] for x in sorted(lst)]
        self.art_rows = {"offense": {}, "defense": {}}       # side -> {ARTL: row}
        for side, rows in (("offense", t["ARTO"]), ("defense", t["ARTD"])):
            for r in rows:
                self.art_rows[side][int(r["ARTL"])] = r
        self.shared_ids = {psal for psal, lst in self.steps["offense"].items() if self.steps["defense"].get(psal) == lst}
        for s in self.sets.values():
            s["table"] = self._table_of(s)
        self.books_of_play = collections.defaultdict(set)
        for r in t["PBAI"]:
            self.books_of_play[int(r["PBPL"])].add(int(r["BOKL"]))
        self.book_play_names = {}                            # {BOKL: {PLYL: the name that playbook shows for the play}}, see set_book_play_names
        self._usage = None

    def _index_sets(self, setl_rows, setp_rows):
        """Add sets (SETL rows) and their slots (SETP rows) to self.sets; returns the new set ids."""
        new = []
        for r in setl_rows:
            self.sets[int(r["SETL"])] = {"setl": int(r["SETL"]), "name": r["name"], "form": int(r["FORM"]), "motn": int(r["MOTN"]), "sett": int(r["SETT"]),
                                         "sitt": int(r["SITT"]), "slots": []}
            new.append(int(r["SETL"]))
        new_set = set(new)
        for r in sorted(setp_rows, key=lambda r: (int(r["SETL"]), int(r["poso"]))):
            s = self.sets.get(int(r["SETL"]))
            if s is not None and int(r["SETL"]) in new_set:
                s["slots"].append({"setp": int(r["SETP"]), "poso": int(r["poso"]), "epos": int(r["EPos"]), "dpos": int(r["DPos"]), "x": int(r["artx"]), "y": int(r["arty"]),
                                   "fmtx": int(r["fmtx"]), "fmty": int(r["fmty"]), "sgt": int(r["SGT_"]), "arti": int(r["arti"]), "tabo": int(r["tabo"])})
        for setl in new:
            s = self.sets[setl]
            epos = [x["epos"] for x in s["slots"]]
            s["side"] = "offense" if 0 in epos else ("defense" if epos and all(10 <= e <= 18 for e in epos) else "other")
        return new

    def _index_plays(self, pbpl, plys, plpd, plrd, plcm):
        """Add plays (PBPL rows) with their slot rows (PLYS), pass reads (PLPD), run holes (PLRD) and combination rows (PLCM)."""
        for r in pbpl:
            self.plays[int(r["PLYL"])] = {"plyl": int(r["PLYL"]), "setl": int(r["SETL"]), "name": r["name"], "plyt": int(r["PLYT"]), "plf": int(r["PLF_"]), "risk": int(r["risk"]),
                                          "motn": int(r["motn"]), "vpos": int(r["vpos"]), "sitt": int(r["SITT"])}
        for r in plys:
            self.slot_rows[int(r["PLYL"])][int(r["poso"])] = {"psal": int(r["PSAL"]), "artl": int(r["ARTL"]), "plrr": int(r["PLRR"])}
        for r in plpd:
            self.passing[int(r["PLYL"])] = r
        for r in plrd:
            self.running[int(r["PLYL"])].append(r)
        for r in plcm:
            self.combos[int(r["PLYL"])] = r

    # ---- the profile's custom plays, mounted next to the game's own so that the Play creator can open and change them
    def mount_custom(self, profile):
        """Mount the custom plays of a profile save: profile is {table: [row dicts]} with PBPL, SETL, SETP, SETG, SGFF, PLYS, PLPD, PLRD and PLCM. A profile's ids can equal the
        game's own, so every id of the mounted rows is moved up by CUSTOM_OFFSETS (the originals are kept in self.custom: {mounted PLYL: {"plyl", "setl", "name"}}); an earlier mount
        is taken out first. Their step lists and art are the game's own (a custom play only names them). Returns the mounted play ids, in the profile's order."""
        self.unmount_custom()
        self.yard_map()                                       # fitted on the game's own sets only, before the custom ones are in
        off = CUSTOM_OFFSETS

        def move(rows, **cols):
            return [{**r, **{c: str(int(r[c]) + off[k]) for c, k in cols.items()}} for r in rows]
        rows = {
            "SETL": move(profile.get("SETL", []), SETL="SETL"), "SETP": move(profile.get("SETP", []), SETL="SETL", SETP="SETP"), "SGFF": move(profile.get("SGFF", []), SETL="SETL", SGF_="SGF_"),
            "SETG": move(profile.get("SETG", []), SETP="SETP", SGF_="SGF_"), "PBPL": move(profile.get("PBPL", []), SETL="SETL", PLYL="PLYL"), "PLYS": move(profile.get("PLYS", []), PLYL="PLYL"),
            "PLPD": move(profile.get("PLPD", []), PLYL="PLYL"), "PLRD": move(profile.get("PLRD", []), PLYL="PLYL"), "PLCM": move(profile.get("PLCM", []), PLYL="PLYL")}
        # only plays whose set is in the profile (a play of the game's own sets is not a custom play)
        have = {int(r["SETL"]) for r in rows["SETL"]}
        rows["PBPL"] = [r for r in rows["PBPL"] if int(r["SETL"]) in have]
        kept = {int(r["PLYL"]) for r in rows["PBPL"]}
        for t in ("PLYS", "PLPD", "PLRD", "PLCM"):
            rows[t] = [r for r in rows[t] if int(r["PLYL"]) in kept]
        for t, rs in rows.items():
            self.tables[t].extend(rs)
        self._custom_rows = rows
        new_sets = self._index_sets(rows["SETL"], rows["SETP"])
        self._index_plays(rows["PBPL"], rows["PLYS"], rows["PLPD"], rows["PLRD"], rows["PLCM"])
        for setl in new_sets:
            self.sets[setl]["table"] = self._table_of(self.sets[setl])
        for r in rows["PBPL"]:
            plyl = int(r["PLYL"])
            self.custom[plyl] = {"plyl": plyl - off["PLYL"], "setl": int(r["SETL"]) - off["SETL"], "name": r["name"]}
        self.__dict__.pop("_align_cache", None)
        self.__dict__.pop("_setg_by_group", None)
        return [int(r["PLYL"]) for r in rows["PBPL"]]

    def unmount_custom(self):
        """Take the mounted custom plays out again."""
        if not self._custom_rows and not self.custom:
            return
        for plyl in list(self.custom):
            self.plays.pop(plyl, None)
            self.slot_rows.pop(plyl, None)
            self.passing.pop(plyl, None)
            self.running.pop(plyl, None)
            self.combos.pop(plyl, None)
        for setl in [k for k in self.sets if k >= CUSTOM_OFFSETS["SETL"]]:
            del self.sets[setl]
        for t, rows in self._custom_rows.items():
            gone = {id(r) for r in rows}
            self.tables[t][:] = [r for r in self.tables[t] if id(r) not in gone]
        self._custom_rows, self.custom = {}, {}
        self._usage = None
        self.__dict__.pop("_align_cache", None)
        self.__dict__.pop("_setg_by_group", None)

    def is_custom(self, plyl):
        return plyl in self.custom

    def set_book_play_names(self, rows):
        """The names the playbooks give their plays (table PPPN of the shipped database: BOKL, PLYL, PPPM). The game's play-call screen shows these, not the master names in
        PBPL (about four in five differ, e.g. "Deep Attack" is "Liz Lft Deep Attack" in one playbook). Rows that do not parse are skipped."""
        out = collections.defaultdict(dict)
        for r in rows:
            try:
                name = cut_at_control(r["PPPM"])
                if name:
                    out[int(r["BOKL"])][int(r["PLYL"])] = name
            except (KeyError, ValueError):
                continue
        self.book_play_names = dict(out)

    def name_in_book(self, plyl, bokl):
        """The name a playbook shows for a play: its own name for it when it has one, else the master name."""
        own = self.book_play_names.get(bokl, {}).get(plyl)
        return own or (self.plays[plyl]["name"] if plyl in self.plays else f"Play {plyl}")

    def names_across_books(self, plyl):
        """[(name, number of playbooks)], the most common first: what the playbooks that hold a play call it."""
        counts = collections.Counter(self.name_in_book(plyl, b) for b in self.books_of_play.get(plyl, ()))
        return counts.most_common()

    def _table_of(self, s):
        """Which assignment tables a set's plays use, "offense" (PSLO, ARTO) or "defense" (PSLD, ARTD): the side for offensive and defensive sets; for the special-teams
        sets (kicking, returning, blocking), whichever table most of their plays' step lists are only in."""
        if s["side"] in ("offense", "defense"):
            return s["side"]
        votes = collections.Counter()
        for plyl, p in self.plays.items():
            if p["setl"] != s["setl"]:
                continue
            for row in self.slot_rows.get(plyl, {}).values():
                in_o, in_d = row["psal"] in self.steps["offense"], row["psal"] in self.steps["defense"]
                if in_o != in_d:
                    votes["offense" if in_o else "defense"] += 1
        return votes.most_common(1)[0][0] if votes else "offense"

    # ---- alignment: where the players line up on the field, in yards (the SETG floats), and how the diagram's picture draws it
    def alignment(self, setl):
        """{poso: {"x", "y", "fx", "fy", "setp", "partner"}} for a set's normal alignment group, in yards: x across the field (plus is the right side), y from the line of scrimmage
        (minus is behind it); fx / fy is where the slot lines up when the play is flipped, which is where another slot, "partner", lines up mirrored (partner is None when no slot
        matches)."""
        cache = self.__dict__.setdefault("_align_cache", {})
        if setl in cache:
            return cache[setl]
        if "_setg_by_group" not in self.__dict__:
            by = collections.defaultdict(list)
            for r in self.tables["SETG"]:
                by[int(r["SGF_"])].append(r)
            self._setg_by_group = by
        out = {}
        group = next((g for g in self.tables["SGFF"] if int(g["SETL"]) == setl and g["dflt"] == "1"), None)
        s = self.sets.get(setl)
        if group is not None and s is not None:
            poso_of = {sl["setp"]: sl["poso"] for sl in s["slots"]}
            for r in self._setg_by_group.get(int(group["SGF_"]), []):
                poso = poso_of.get(int(r["SETP"]))
                if poso is not None:
                    out[poso] = {"x": float_bits(r["x___"]), "y": float_bits(r["y___"]), "fx": float_bits(r["fx__"]), "fy": float_bits(r["fy__"]), "setp": int(r["SETP"]), "partner": None}
            for i, a in out.items():
                for j, b in out.items():
                    if abs(a["fx"] + b["x"]) < 0.02 and abs(a["fy"] - b["y"]) < 0.02:
                        a["partner"] = j
                        break
        cache[setl] = out
        return out

    def yard_map(self):
        if "_yard_map" not in self.__dict__:
            self._yard_map = YardMap(self)
        return self._yard_map

    # ---- plays
    @staticmethod
    def side_key(side):
        """The table ("offense" or "defense") a side's step lists and art are in; pass a set's "table" for the special-teams sets."""
        return "defense" if side == "defense" else "offense"

    def steps_of(self, side, psal):
        return self.steps[self.side_key(side)].get(psal, [])

    def art_of(self, side, artl):
        """The decoded art points of an ARTL id on a side ([] for an id with no art)."""
        row = self.art_rows[self.side_key(side)].get(artl)
        return decode_art(row) if row is not None else []

    def play_table(self, plyl):
        return self.sets[self.plays[plyl]["setl"]]["table"] if self.plays[plyl]["setl"] in self.sets else "offense"

    def play_side(self, plyl):
        return self.sets[self.plays[plyl]["setl"]]["side"] if self.plays[plyl]["setl"] in self.sets else "other"

    def play_list(self, side=None, custom=False):
        """The plays of a side as rows; the game's own, or with custom=True only the mounted custom plays of a profile (mount_custom)."""
        out = []
        for plyl, p in self.plays.items():
            s = self.sets.get(p["setl"])
            if s is None or (side and s["side"] != side) or (plyl in self.custom) != bool(custom):
                continue
            out.append({"plyl": plyl, "name": p["name"], "set": s["name"], "form": self.form_names.get(s["form"], f"formation {s['form']}"), "plyt": p["plyt"], "motn": p["motn"],
                        "option": self.play_is_option(plyl), "books": len(self.books_of_play.get(plyl, ())), "side": s["side"]})
        return sorted(out, key=lambda r: (r["name"].lower(), r["plyl"]))

    def play_is_option(self, plyl):
        table = self.play_table(plyl)
        return any(c in OPTION_CODES for poso in self.slot_rows.get(plyl, {}).values() for c, *_ in self.steps_of(table, poso["psal"]))

    def detail(self, plyl):
        """A play with its slots: [{poso, epos, dpos, label, x, y, psal, artl, plrr, steps, text, art}] and the play's own columns."""
        p = self.plays[plyl]
        s = self.sets[p["setl"]]
        slots = []
        for sl in s["slots"]:
            row = self.slot_rows.get(plyl, {}).get(sl["poso"])
            if row is None:
                continue
            steps = self.steps_of(s["table"], row["psal"])
            art = self.art_of(s["table"], row["artl"])
            slots.append({**sl, "label": POSITIONS.get(sl["epos"], str(sl["epos"])) + (str(sl["dpos"]) if sl["epos"] in (1, 2, 3, 4) or 10 <= sl["epos"] <= 18 else ""),
                          "psal": row["psal"], "artl": row["artl"], "plrr": row["plrr"], "steps": steps, "text": step_text(steps), "art": art})
        return {"play": p, "set": s, "slots": slots, "side": s["side"], "table": s["table"], "passing": self.passing.get(plyl), "running": self.running.get(plyl, []), "combo": self.combos.get(plyl),
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
        """{(side, PSAL): {"uses": slots using it, "plays": set of plays, "epos": Counter of the positions using it, "artl": Counter of the art it is drawn with,
        "plrr": Counter of the role codes}} over the stock plays."""
        if self._usage is None:
            u = {}
            for plyl, slots in self.slot_rows.items():
                s = self.sets.get(self.plays.get(plyl, {}).get("setl"))
                if s is None or plyl in self.custom:
                    continue
                side = s["table"]
                epos = {x["poso"]: x["epos"] for x in s["slots"]}
                for poso, row in slots.items():
                    e = u.setdefault((side, row["psal"]), {"uses": 0, "plays": set(), "epos": collections.Counter(), "artl": collections.Counter(), "plrr": collections.Counter()})
                    e["uses"] += 1
                    e["plays"].add(plyl)
                    e["epos"][epos.get(poso, -1)] += 1
                    e["artl"][row["artl"]] += 1
                    e["plrr"][row["plrr"]] += 1
            self._usage = u
        return self._usage

    def library(self, side=None):
        """Every step list of a side as an entry {psal, side, steps, text, uses, plays, epos, artl, plrr, option, unused (no stock play of that side uses it),
        shared (the same list is in both the offense and the defense table)}, ordered by id."""
        u = self.usage()
        side = self.side_key(side)
        out = []
        for psal, steps in self.steps[side].items():
            e = u.get((side, psal))
            out.append({"psal": psal, "side": side, "steps": steps, "text": step_text(steps), "uses": e["uses"] if e else 0, "plays": len(e["plays"]) if e else 0,
                        "epos": e["epos"] if e else collections.Counter(), "artl": e["artl"] if e else collections.Counter(), "plrr": e["plrr"] if e else collections.Counter(),
                        "option": any(c in OPTION_CODES for c, *_ in steps), "unused": e is None, "shared": psal in self.shared_ids})
        return sorted(out, key=lambda r: r["psal"])

    def entry_art(self, entry):
        """The art that goes with a library entry: the one used most with it (None for an entry no stock play uses)."""
        return entry["artl"].most_common(1)[0][0] if entry["artl"] else None

    def entry_role(self, entry):
        return entry["plrr"].most_common(1)[0][0] if entry["plrr"] else 2


ALIGN_X = 22.0            # a player may line up this many yards either side of the center (the game's offensive sets use up to 17.5)
ALIGN_Y = (-12.0, -0.4)   # and from 0.4 to 12 yards behind the line of scrimmage (the game's sets use 0.6 to 10.6)


class YardMap:
    """How the diagram's picture draws yards. The picture squeezes the field (wide spots are drawn closer together, so a wide receiver 17.5 yards out is 75 units from the
    middle while a tackle 3.3 yards out is 24), so the two are related by a curve, found here from where the game's own offensive sets stand in both: art(x, y) gives the
    picture's units for yards, yards(artx, arty) the other way round."""

    def __init__(self, lib):
        px, py = collections.defaultdict(list), collections.defaultdict(list)
        for s in lib.sets.values():
            if s["side"] != "offense":
                continue
            al = lib.alignment(s["setl"])
            for sl in s["slots"]:
                a = al.get(sl["poso"])
                if a:
                    px[round(a["x"] * 4) / 4].append(sl["x"])
                    py[round(-a["y"] * 2) / 2].append(sl["y"])
        self.xt = self._table(px)
        self.yt = self._table(py)

    @staticmethod
    def _table(groups):
        pts = sorted((k, sum(v) / len(v)) for k, v in groups.items() if len(v) >= 2)
        out, top = [], -1e9
        for k, v in pts:                  # keep it rising (a single odd set must not fold the curve)
            if v > top:
                out.append((k, v))
                top = v
        return out

    @staticmethod
    def _interp(table, v, inverse=False):
        a = [(t[1], t[0]) for t in table] if inverse else table
        if v <= a[0][0]:
            (x0, y0), (x1, y1) = a[0], a[1]
        elif v >= a[-1][0]:
            (x0, y0), (x1, y1) = a[-2], a[-1]
        else:
            i = next(k for k in range(1, len(a)) if a[k][0] >= v)
            (x0, y0), (x1, y1) = a[i - 1], a[i]
        return y0 + (v - x0) * (y1 - y0) / (x1 - x0) if x1 != x0 else y0

    def art(self, x_yd, y_yd):
        """(artx, arty) in whole diagram units for a place in yards."""
        ax = self._interp(self.xt, x_yd)
        ay = self._interp(self.yt, -y_yd)
        return int(round(min(180, max(0, ax)))), int(round(min(104, max(0, ay))))

    def yards(self, artx, arty):
        """(x, y) in yards, to a quarter yard, for a place in the picture's units."""
        x = self._interp(self.xt, artx, inverse=True)
        y = -self._interp(self.yt, arty, inverse=True)
        return round(x * 4) / 4, round(y * 4) / 4


# ---------- building a custom play (the rows the in-game Create-A-Play writes to the profile save)
def next_ids(profile):
    """The first free ids in a profile's custom-play tables: {"SETL", "PLYL", "SETP", "SGF_"} from {table: rows}."""
    def top(table, col):
        return max([int(r[col]) for r in profile.get(table, [])] or [0]) + 1
    return {"SETL": top("SETL", "SETL"), "PLYL": top("PBPL", "PLYL"), "SETP": top("SETP", "SETP"), "SGF_": top("SGFF", "SGF_")}


def build_custom_play(lib, base_plyl, name, overrides, profile, plyt=None, plan=None, reads=None, alignment=None):
    """The rows of a new custom play made from the stock play base_plyl: {table: [row dicts with every column of that table as strings]} for the
    profile save (PBPL, SETL, SETP, SETG, SGFF, PLYS, and PLPD / PLRD / PLCM when the base play has them), and a summary.
    overrides: {poso: (PSAL, ARTL, PLRR)} replaces a slot's assignment with any step list of the game (PSAL, ARTL and PLRR taken from library entries).
    plan: a hc09_playtypes conversion plan, when the play was turned into another kind of play: its PLYT is used, and the PLPD / PLRD / PLCM rows come from the
    stock play of that kind it names (tables_from) or are the ones it synthesised, instead of the base play's.
    reads: the quarterback's progression for a pass play, [(slot, chance)] for five different skill slots in the order he looks to them (the in-game editor's "progressions"; a
    chance is 0 to 100): it replaces the copied PLPD row. A play that is not a pass has no reads and ignores it.
    alignment: {slot: (x, y)} in yards (x across, plus to the right; y from the line, minus behind it) for the players to line up somewhere else than the stock set has them:
    written to the new set's own SETG rows of the normal alignment group (and to the flipped position of the slot that mirrors him) and, in the diagram's units, to its SETP rows;
    the pre-snap motion alignment groups are copied as they are.
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
    ptype = plyt if plyt is not None else (plan["plyt"] if plan is not None else base["plyt"])
    rows["PBPL"].append({"SETL": new_setl, "PLYL": new_plyl, "SITT": 2, "PLYT": ptype, "PLF_": base["plf"], "name": name, "risk": 0, "motn": base["motn"], "vpos": base["vpos"]})
    rows["SETL"].append({"SETL": new_setl, "FORM": CREATED_FORMATION, "MOTN": bset["motn"], "SETT": bset["sett"], "SITT": 0, "SLF_": 0, "name": "Created", "poso": 0})
    stock_al = lib.alignment(bset["setl"])
    moved = {}
    for poso, (mx, my) in (alignment or {}).items():
        if poso not in stock_al:
            raise ValueError(f"Slot {poso} is not in this set.")
        if not (-ALIGN_X <= float(mx) <= ALIGN_X and ALIGN_Y[0] <= float(my) <= ALIGN_Y[1]):
            raise ValueError(f"A player lines up within {ALIGN_X:g} yards of the middle and between {-ALIGN_Y[1]:g} and {-ALIGN_Y[0]:g} yards behind the line.")
        if (abs(float(mx) - stock_al[poso]["x"]) > 0.001 or abs(float(my) - stock_al[poso]["y"]) > 0.001):
            moved[poso] = (float(mx), float(my))
    ymap = lib.yard_map() if moved else None
    setp_ids = {}
    for i, sl in enumerate(bset["slots"]):
        setp_ids[sl["setp"]] = ids["SETP"] + i
        ax, ay = ymap.art(*moved[sl["poso"]]) if sl["poso"] in moved else (sl["x"], sl["y"])
        rows["SETP"].append({"SETL": new_setl, "SETP": ids["SETP"] + i, "SGT_": 0, "arti": 5 if sl["epos"] == 7 else 4, "opnm": 0, "tabo": sl["tabo"], "poso": sl["poso"], "odep": 0,
                             "flas": 0, "DPos": sl["dpos"], "EPos": sl["epos"], "fmtx": ax, "artx": ax, "fmty": ay, "arty": ay})
    groups = [g for g in lib.tables["SGFF"] if int(g["SETL"]) == bset["setl"]]
    group_map = {}
    for i, g in enumerate(sorted(groups, key=lambda g: -int(g["dflt"]))):
        group_map[int(g["SGF_"])] = ids["SGF_"] + i
        rows["SGFF"].append({"SETL": new_setl, "SGF_": ids["SGF_"] + i, "name": g["name"], "dflt": g["dflt"]})
    default_group = next((int(g["SGF_"]) for g in groups if g["dflt"] == "1"), None)
    poso_of_setp = {sl["setp"]: sl["poso"] for sl in bset["slots"]}
    for g in lib.tables["SETG"]:
        if int(g["SETP"]) in setp_ids and int(g["SGF_"]) in group_map:
            row = {"SETP": setp_ids[int(g["SETP"])], "SGF_": group_map[int(g["SGF_"])], "SF__": g["SF__"], "x___": g["x___"], "y___": g["y___"], "fx__": g["fx__"],
                   "fy__": g["fy__"], "anm_": g["anm_"], "dir_": g["dir_"], "fanm": g["fanm"], "fdir": g["fdir"]}
            if moved and int(g["SGF_"]) == default_group:
                poso = poso_of_setp[int(g["SETP"])]
                if poso in moved:
                    row["x___"], row["y___"] = bits_of_float(moved[poso][0]), bits_of_float(moved[poso][1])
                partner = stock_al.get(poso, {}).get("partner")
                if partner in moved:               # flipped, this slot lines up where the partner is, mirrored
                    row["fx__"], row["fy__"] = bits_of_float(-moved[partner][0]), bits_of_float(moved[partner][1])
            rows["SETG"].append(row)
    for sl in d["slots"]:
        psal, artl, plrr = overrides.get(sl["poso"], (sl["psal"], sl["artl"], sl["plrr"]))
        if psal not in lib.steps[d["table"]]:
            raise ValueError(f"Step list {psal} is not one of the game's {d['table']} step lists.")
        rows["PLYS"].append({"PSAL": psal, "ARTL": artl, "PLYL": new_plyl, "PLRR": plrr, "poso": sl["poso"]})
    src_plyl = base_plyl
    synth = {}
    if plan is not None:
        src_plyl = plan.get("tables_from")
        synth = plan.get("tables") or {}
    if src_plyl is not None:
        for table, src in (("PLPD", lib.passing.get(src_plyl)), ("PLCM", lib.combos.get(src_plyl))):
            if src is not None:
                rows[table].append({**{k: v for k, v in src.items() if k != "PLYL"}, "PLYL": new_plyl})
        for r in lib.running.get(src_plyl, []):
            rows["PLRD"].append({"PLYL": new_plyl, "hole": r["hole"]})
    if synth.get("PLPD"):
        rows["PLPD"].append({**synth["PLPD"], "PLYL": new_plyl})
    for r in synth.get("PLRD") or []:
        rows["PLRD"].append({"PLYL": new_plyl, "hole": r["hole"]})
    if reads is not None and rows.get("PLPD"):
        skill = {sl["poso"] for sl in bset["slots"] if sl["epos"] in (1, 2, 3, 4)}
        if len(reads) != 5 or len({int(p) for p, _ in reads}) != 5 or any(int(p) not in skill for p, _ in reads) or any(not 0 <= int(c) <= 100 for _, c in reads):
            raise ValueError("The pass reads are five different receivers (halfbacks, fullbacks, receivers, tight ends), each with a chance from 0 to 100.")
        row = {"PLYL": new_plyl}
        for k, (poso, chance) in enumerate(reads, 1):
            row[f"rcv{k}"] = int(poso)
            row[f"per{k}"] = int(chance)
        rows["PLPD"] = [row]
    summary = {"setl": new_setl, "plyl": new_plyl, "name": name, "plyt": ptype, "from": base["name"], "slots_changed": sorted(overrides), "slots_moved": sorted(moved),
               "rows": {k: len(v) for k, v in rows.items()}}
    return dict(rows), summary


def update_custom_play(lib, plyl, name, overrides, profile, plyt=None, plan=None, reads=None, alignment=None):
    """Change a custom play of the profile in place: plyl is its MOUNTED id (lib.mount_custom), the other arguments are those of build_custom_play. Returns ({table: the whole table's rows
    with the play's rows changed}, summary) for the profile save: only values change, no row is added or taken out, so the ids, the set and the playbook links stay as they are.
    What changes: the play's name and play type, each slot's step list, art and role (PLYS), the players' places (SETP diagram columns and the yards of SETG), and the pass reads, run
    holes and combination row (PLPD, PLRD, PLCM) when the play is made another kind. Raises ValueError when that needs rows the play does not have or has too many of (a pass made a run
    play, say): make a new play from it then. summary["plyt"] is the play type to write into the playbook links (PGPL.PLTP)."""
    info = lib.custom.get(plyl)
    if info is None:
        raise ValueError("That is not one of the profile's custom plays.")
    orig_plyl, orig_setl = info["plyl"], info["setl"]
    if not any(int(r["PLYL"]) == orig_plyl for r in profile.get("PBPL", [])):
        raise ValueError("The play is not in the profile any more (it was changed since the editor read it). Open the plays again.")
    # the rows the play would have if it were made new from itself, then copied over its own rows by place (slot number, group order)
    scratch = {t: [dict(r) for r in rows] for t, rows in profile.items()}
    new, summ = build_custom_play(lib, plyl, name, overrides, scratch, plyt=plyt, plan=plan, reads=reads, alignment=alignment)
    out = {t: [dict(r) for r in profile.get(t, [])] for t in ("PBPL", "SETP", "SETG", "PLYS", "PLPD", "PLRD", "PLCM")}

    def mine(table, col, value):
        return [r for r in out[table] if int(r[col]) == value]
    pbpl = mine("PBPL", "PLYL", orig_plyl)[0]
    pbpl["name"], pbpl["PLYT"] = new["PBPL"][0]["name"], new["PBPL"][0]["PLYT"]
    for nr in new["PLYS"]:
        row = next((r for r in mine("PLYS", "PLYL", orig_plyl) if int(r["poso"]) == int(nr["poso"])), None)
        if row is None:
            raise ValueError("The play has no slot " + str(nr["poso"]) + " in the profile.")
        row["PSAL"], row["ARTL"], row["PLRR"] = nr["PSAL"], nr["ARTL"], nr["PLRR"]
    old_setp = {int(r["poso"]): r for r in mine("SETP", "SETL", orig_setl)}
    new_setp = {int(r["poso"]): r for r in new["SETP"]}
    for poso, nr in new_setp.items():
        if poso not in old_setp:
            raise ValueError("The set has no slot " + str(poso) + " in the profile.")
        for c in ("artx", "arty", "fmtx", "fmty"):
            old_setp[poso][c] = nr[c]
    # SETG: the new rows are keyed by the new set's slots and groups; the old ones by theirs. Match slots by poso and groups by their order (default group first), as build_custom_play made them
    new_poso = {int(r["SETP"]): int(r["poso"]) for r in new["SETP"]}
    old_poso = {int(r["SETP"]): p_ for p_, r in old_setp.items()}
    old_groups = [g for g in profile.get("SGFF", []) if int(g["SETL"]) == orig_setl]
    old_groups.sort(key=lambda g: -int(g["dflt"]))
    new_groups = [int(g["SGF_"]) for g in new["SGFF"]]
    if len(old_groups) != len(new_groups):
        raise ValueError("The play's alignment groups are not the ones of its set, so it cannot be changed in place.")
    group_of_new = {ng: int(og["SGF_"]) for ng, og in zip(new_groups, old_groups)}
    old_setg = {(old_poso[int(r["SETP"])], int(r["SGF_"])): r for r in out["SETG"] if int(r["SETP"]) in old_poso}
    for nr in new["SETG"]:
        key = (new_poso[int(nr["SETP"])], group_of_new[int(nr["SGF_"])])
        row = old_setg.get(key)
        if row is None:
            raise ValueError("The play's alignment is not complete in the profile, so it cannot be changed in place.")
        for c in ("SF__", "x___", "y___", "fx__", "fy__", "anm_", "dir_", "fanm", "fdir"):
            row[c] = nr[c]
    for table in ("PLPD", "PLRD", "PLCM"):
        have = mine(table, "PLYL", orig_plyl)
        want = new.get(table, [])
        if len(have) != len(want):
            word = {"PLPD": "pass-read", "PLRD": "run-hole", "PLCM": "play-combination"}[table]
            raise ValueError(f"Making the play this kind needs {len(want)} {word} row{'' if len(want) == 1 else 's'} ({table}) and the play has {len(have)}, which cannot be changed in place. "
                             "Use Save as a new play instead.")
        for old_row, nr in zip(have, want):
            for c in old_row:
                if c != "PLYL" and c in nr:
                    old_row[c] = nr[c]
    summary = {"setl": orig_setl, "plyl": orig_plyl, "name": name, "plyt": int(new["PBPL"][0]["PLYT"]), "from": info["name"], "slots_changed": sorted(overrides),
               "slots_moved": summ["slots_moved"], "mounted": plyl}
    return out, summary


def career_link_rows(career, bokl, new_setl, new_plyl, plyt):
    """The rows that put a custom play into custom playbook bokl in a career save: PGPL, PGSS, PGSL, and PGFM for the "Created Plays" formation if that
    playbook has none yet. {table: [rows]}."""
    rows = {"PGPL": [{"BOKL": bokl, "SETL": new_setl, "PLYL": new_plyl, "PLTP": plyt}], "PGSS": [{"BOKL": bokl, "SETL": new_setl}],
            "PGSL": [{"BOKL": bokl, "SETL": new_setl, "PBFM": CREATED_FORMATION}]}
    if not any(int(r["BOKL"]) == bokl and int(r["PBFM"]) == CREATED_FORMATION for r in career.get("PGFM", [])):
        rows["PGFM"] = [{"BOKL": bokl, "PBFM": CREATED_FORMATION, "SRFM": CREATED_FORMATION}]
    return rows
