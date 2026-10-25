"""
Game reference: what the game's own tables say about injuries, draft pick values, contract talks and what an injured body part does to a player.

Standard library only (no Tk). The editor's "Game reference" window uses this. The tables are read out of the user's own qkl_boot.ast into a cache folder (extract_commands says
which bridge calls do it), and everything here is read-only: nothing is written to a save or to the game.

What the tables are (details and the figures: docs/hc09_game_internals.md, docs/hc09_gamedata_findings.md). All of this is the game's DATA; whether and how the game uses it in
a match is not confirmed, so the window says "the game's table holds" and does not promise results:
  LINC  injury chance LEVEL (0-4, not a percent) from position, body part, injury rating, body-part health, fatigue and impact severity (each cut into bins by Eirt, Ebph, EFAT, Eisv)
  DVCD  value of the draft pick by overall pick number (pick 1 = 30,000); DVCP the same for "player value", one column per team-building philosophy; DVFD / DVFP next year's picks by round
  LPCN  chance (percent) that a player accepts, walks away or sets an ultimatum, from head coach approval, player overall, counter offers so far and the gap to his wanted package
        (bins EHCB, POGB, NCOB, PCPG); two more keys (a negotiation type and a player trait) are not named, so they are shown as a range
  PHAE  which ratings an injured body part lowers, by position group (PLPS: position -> group); how MUCH it lowers them is not in this table
"""
import csv
import os

GAME_TABLES = ("LINC", "Eirt", "Ebph", "EFAT", "Eisv", "DVCD", "DVCP", "DVFD", "DVFP", "LPCN", "NCOB", "PCPG", "POGB", "EHCB")   # the big shipped database (streameddata); table names are case sensitive
STATIC_TABLES = ("PHAE", "PLPS")                                                                                          # the small one (STATICDATA)
# Where the two databases usually sit in qkl_boot.ast. Only a hint: the bridge falls back to scanning the whole archive when a table is not there.
TOP_INDEX_HINT = {"game": 46, "static": 45}
CACHE_SUBDIR = "reference"

EMPTY_RATING = 47                       # PHAE fills unused rating slots with this; real rating ids are 0-46
PICKS_PER_ROUND = 32
ROUNDS = 7

POSITION_NAMES = ("QB", "HB", "FB", "WR", "TE", "LT", "LG", "C", "RG", "RT", "LE", "RE", "DT", "LOLB", "MLB", "ROLB", "CB", "FS", "SS", "K", "P")      # PPOS 0-20
GROUP_NAMES = ("QB", "HB", "FB", "WR", "TE", "OT", "OG", "C", "DE", "DT", "OLB", "MLB", "CB", "FS", "SS", "K", "P")                                  # PDRP 0-16 (PLPS maps PPOS to it)
# body part ids (LINC, PHAE): which of the two legs / arms is the left one is not known, so the ids are shown
BODY_PART_NAMES = {0: "Leg (id 0)", 1: "Leg (id 1)", 2: "Arm (id 2)", 3: "Arm (id 3)", 4: "Head", 5: "Torso"}
# rating ids of the game (the ones PHAE and the progression tables use) -> the editor's field and name (same names as the Stat Editor)
RATING_FIELDS = {0: "PSTR", 1: "PAGI", 2: "PSPD", 3: "PACC", 4: "PAWR", 5: "PCTH", 6: "PCAR", 7: "PTHP", 8: "PTHA", 9: "PKPR", 10: "PKAC", 11: "PTAK", 12: "PPBK", 13: "PRBK", 14: "PJMP",
                 15: "PKRT", 16: "PLTR", 17: "PELU", 18: "PBCV", 19: "PLSA", 20: "PLSM", 21: "PLJM", 22: "PLIB", 23: "PRBS", 24: "PRBF", 25: "PPBS", 26: "PPBF", 27: "PLPm", 28: "PFMS",
                 29: "PBSG", 30: "PLPU", 31: "PLPR", 32: "PLMC", 33: "PLZC", 34: "PIMP", 35: "PINJ", 36: "PSTA", 37: "PTGH", 38: "", 39: "PLSC", 40: "PLCI", 41: "PLRR", 42: "PLHT",
                 43: "PLPE", 44: "PLRL", 45: "PMOR", 46: "PLRN"}
RATING_NAMES = {0: "Strength", 1: "Agility", 2: "Speed", 3: "Acceleration", 4: "Awareness", 5: "Catching", 6: "Carrying", 7: "Throw Power", 8: "Throw Accuracy", 9: "Kick Power",
                10: "Kick Accuracy", 11: "Tackling", 12: "Pass Block", 13: "Run Block", 14: "Jump", 15: "Kick Return", 16: "Trucking", 17: "Elusiveness", 18: "Vision", 19: "Stiff Arm",
                20: "Spin Move", 21: "Juke Move", 22: "Impact Blocking", 23: "Run Block Strength", 24: "Run Block Finesse", 25: "Pass Block Strength", 26: "Pass Block Finesse",
                27: "Power Move", 28: "Finesse Move", 29: "Block Shed", 30: "Pursuit", 31: "Play Recognition", 32: "Man Coverage", 33: "Zone Coverage", 34: "Importance", 35: "Injury",
                36: "Stamina", 37: "Toughness", 38: "Running Style", 39: "Spectacular Catch", 40: "Catch In Traffic", 41: "Route Running", 42: "Hit Power", 43: "Press", 44: "Release",
                45: "Morale", 46: "Learning"}
PHILOSOPHY_NAMES = {0: "Build through the draft", 1: "Build through free agency"}      # BTTP; the strings in the shipped enum are run together, these are its two values in words


def extract_commands(boot_ast, out_dir):
    """The bridge calls (argument lists for run_bridge) that put the tables into out_dir. Two calls: the export finds ONE entry that holds all the tables asked for, and the
    two databases are different entries. --require-rows skips an empty copy of a table."""
    return [["shipped-table-export", "--ast", boot_ast, "--tables", ",".join(GAME_TABLES), "--top-index", str(TOP_INDEX_HINT["game"]), "--require-rows", "--out-dir", out_dir],
            ["shipped-table-export", "--ast", boot_ast, "--tables", ",".join(STATIC_TABLES), "--top-index", str(TOP_INDEX_HINT["static"]), "--require-rows", "--out-dir", out_dir]]


def table_path(cache_dir, table):
    return os.path.join(cache_dir, table.lower() + ".csv")


def missing_tables(cache_dir):
    """The tables that are not in the cache folder yet (or are empty)."""
    out = []
    for t in GAME_TABLES + STATIC_TABLES:
        p = table_path(cache_dir, t)
        if not (os.path.isfile(p) and os.path.getsize(p) > 0):
            out.append(t)
    return out


def _int(text, default=None):
    try:
        return int(float(str(text).strip()))
    except (TypeError, ValueError):
        return default


def read_rows(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def read_bins(rows):
    """[(low, high, value)] of a bin table (BNMN, BNMX, ENUV), lowest first. The rows are stored in any order: always look a number up by its range."""
    bins = []
    for r in rows:
        lo, hi, v = _int(r.get("BNMN")), _int(r.get("BNMX")), _int(r.get("ENUV"))
        if None not in (lo, hi, v):
            bins.append((lo, hi, v))
    return sorted(bins)


def bin_of(value, bins):
    """The bin value (ENUV) a number falls in; a number below the lowest range counts as the lowest bin, above the highest as the highest."""
    value = int(value // 1)
    for lo, hi, v in bins:
        if lo <= value <= hi:
            return v
    return bins[0][2] if value < bins[0][0] else bins[-1][2]


def bin_text(bins, enuv, open_top=False):
    """"90-100" for the range of a bin value; "6+" for the highest bin when it has no real upper end (open_top)."""
    for lo, hi, v in bins:
        if v == enuv:
            return f"{lo}+" if open_top and (lo, hi, v) == bins[-1] else f"{lo}-{hi}"
    return str(enuv)


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


class Reference:
    """The tables in memory. Reference.load(cache_dir) is None when a table is missing."""

    def __init__(self, tables):
        t = tables
        self.bins = {name: read_bins(t[name]) for name in ("Eirt", "Ebph", "EFAT", "Eisv", "NCOB", "PCPG", "POGB", "EHCB")}
        # injuries: {(ppos, bdpt, inrb, fatb, bpth, injs): INCH}
        self.linc = {}
        for r in t["LINC"]:
            key = tuple(_int(r.get(k)) for k in ("PPOS", "BDPT", "INRB", "FATB", "BPTH", "INJS"))
            level = _int(r.get("INCH"))
            if None not in key and level is not None:
                self.linc[key] = level
        # draft picks: value of overall pick n (1-224) and, per philosophy, the "player value"; next year's picks by round (1-7)
        self.pick_values = {}
        for r in t["DVCD"]:
            n, v = _int(r.get("DPNM")), _int(r.get("DPVL"))
            if n is not None and v is not None:
                self.pick_values[n + 1] = v
        self.pick_player_values = {}
        for r in t["DVCP"]:
            n, v, p = _int(r.get("DPNM")), _int(r.get("DPVL")), _int(r.get("BTTP"))
            if None not in (n, v, p):
                self.pick_player_values[(n + 1, p)] = v
        self.future_values, self.future_player_values = {}, {}
        for table, out in (("DVFD", self.future_values), ("DVFP", self.future_player_values)):
            for r in t[table]:
                rnd, v, p = _int(r.get("DRND")), _int(r.get("DPVL")), _int(r.get("BTTP"))
                if None not in (rnd, v, p):
                    out[(rnd + 1, p)] = v
        # contract talks: list of dicts, with the key columns as numbers
        self.contract_rows = []
        for r in t["LPCN"]:
            row = {k: _int(r.get(k)) for k in ("HCAB", "POGB", "NCOB", "PCPG", "NGTY", "CSLT", "ACCP", "LVPT", "ULTP", "PKSM", "PKSX")}
            if None not in (row["HCAB"], row["POGB"], row["NCOB"], row["PCPG"], row["NGTY"], row["CSLT"]):
                self.contract_rows.append(row)
        # injured body parts: PLPS gives position -> position group; PHAE the rating ids per (group, body part)
        self.group_of = {}
        for r in t["PLPS"]:
            ppos, pdrp = _int(r.get("PPOS")), _int(r.get("PDRP"))
            if ppos is not None and pdrp is not None:
                self.group_of[ppos] = pdrp
        self.affected = {}
        slots = [f"GEA{c}" for c in "123456789AB"]
        for r in t["PHAE"]:
            pdrp, bdpt = _int(r.get("PDRP")), _int(r.get("BDPT"))
            if pdrp is None or bdpt is None:
                continue
            ids = [_int(r.get(s)) for s in slots]
            self.affected[(pdrp, bdpt)] = [i for i in ids if i is not None and i < EMPTY_RATING]

    @classmethod
    def load(cls, cache_dir):
        if missing_tables(cache_dir):
            return None
        tables = {name: read_rows(table_path(cache_dir, name)) for name in GAME_TABLES + STATIC_TABLES}
        if not all(tables.values()):
            return None
        ref = cls(tables)
        return ref if ref.linc and ref.pick_values and ref.contract_rows and ref.affected else None

    # ---------- injuries ----------
    def injury_bins(self, rating, health, fatigue, severity):
        """The four bin values for the numbers as the player has them: injury rating 0-99, body-part health 0-1000, fatigue 0-100, impact severity 0-10000."""
        return (bin_of(rating, self.bins["Eirt"]), bin_of(fatigue, self.bins["EFAT"]), bin_of(health, self.bins["Ebph"]), bin_of(severity, self.bins["Eisv"]))

    def injury_level(self, ppos, bdpt, rating, health, fatigue, severity):
        """The chance level (0-4) the table holds for one exact case, or None if the table has no row for it."""
        inrb, fatb, bpth, injs = self.injury_bins(rating, health, fatigue, severity)
        return self.linc.get((ppos, bdpt, inrb, fatb, bpth, injs))

    def injury_average(self, ppos=None, bdpt=None, inrb=None, fatb=None, bpth=None, injs=None):
        """Mean level over every row that matches the ones given (None = any), and the number of rows."""
        want = (ppos, bdpt, inrb, fatb, bpth, injs)
        levels = [lv for key, lv in self.linc.items() if all(w is None or w == k for w, k in zip(want, key))]
        return mean(levels), len(levels)

    def injury_grid(self, ppos=None, bdpt=None, fatb=None, injs=None):
        """{(injury rating bin, body-part health bin): mean level} for one position (None = all), averaged over what is not fixed."""
        return {(i, b): self.injury_average(ppos, bdpt, i, fatb, b, injs)[0]
                for i in sorted({v for _, _, v in self.bins["Eirt"]}) for b in sorted({v for _, _, v in self.bins["Ebph"]})}

    # ---------- draft picks ----------
    @staticmethod
    def pick_round(overall):
        """(round, pick in the round) of overall pick 1-224."""
        return (overall - 1) // PICKS_PER_ROUND + 1, (overall - 1) % PICKS_PER_ROUND + 1

    def pick_value(self, overall):
        return self.pick_values.get(overall)

    def future_value(self, rnd, philosophy=0):
        """Next year's pick of a round (1-7): the value the table holds for the team-building philosophy (0 draft, 1 free agency)."""
        return self.future_values.get((rnd, philosophy))

    def parse_picks(self, text):
        """"1, 33, n2" -> ([("now", 1), ("now", 33), ("next", 2)], [tokens that were not understood]). A plain number is an overall pick of this draft (1-224); n2 or next2 is
        next year's pick of round 2 (rounds 1-7)."""
        picks, bad = [], []
        for tok in text.replace(";", ",").replace("\n", ",").replace(" ", ",").split(","):
            tok = tok.strip().lower()
            if not tok:
                continue
            if tok.startswith("next"):
                tok = "n" + tok[4:]
            if tok.startswith("n") and tok[1:].isdigit() and 1 <= int(tok[1:]) <= ROUNDS:
                picks.append(("next", int(tok[1:])))
            elif tok.isdigit() and 1 <= int(tok) <= PICKS_PER_ROUND * ROUNDS:
                picks.append(("now", int(tok)))
            else:
                bad.append(tok)
        return picks, bad

    def picks_total(self, picks, philosophy=0):
        """(sum of the table's values, [(label, value)]) for parsed picks. A sum on the game's chart, not a prediction of what a team would accept."""
        total, lines = 0, []
        for kind, n in picks:
            if kind == "now":
                v, label = self.pick_value(n), f"pick {n} (round {self.pick_round(n)[0]}, #{self.pick_round(n)[1]})"
            else:
                v, label = self.future_value(n, philosophy), f"next year's round {n}"
            total += v or 0
            lines.append((label, v))
        return total, lines

    def closest_pick(self, value):
        """The overall pick whose value is nearest to a number."""
        return min(self.pick_values, key=lambda n: (abs(self.pick_values[n] - value), n))

    # ---------- contract talks ----------
    def contract_bins(self, approval, overall, counters, gap):
        return (bin_of(approval, self.bins["EHCB"]), bin_of(overall, self.bins["POGB"]), bin_of(counters, self.bins["NCOB"]), bin_of(gap, self.bins["PCPG"]))

    def contract_odds(self, approval, overall, counters, gap, ngty=None, cslt=None):
        """Accept / walk away / ultimatum chances (percent) in the table for a case, as {name: (lowest, mean, highest)} over the two keys that are not named (negotiation type
        NGTY and player trait CSLT) unless one is given. Plus "rows": how many table rows that covers."""
        hcab, pogb, ncob, pcpg = self.contract_bins(approval, overall, counters, gap)
        rows = [r for r in self.contract_rows if (r["HCAB"], r["POGB"], r["NCOB"], r["PCPG"]) == (hcab, pogb, ncob, pcpg)
                and (ngty is None or r["NGTY"] == ngty) and (cslt is None or r["CSLT"] == cslt)]
        out = {"rows": len(rows)}
        for name, col in (("accept", "ACCP"), ("leave", "LVPT"), ("ultimatum", "ULTP")):
            vals = [r[col] for r in rows if r[col] is not None]
            out[name] = (min(vals), mean(vals), max(vals)) if vals else None
        return out

    def contract_grid(self, approval, overall, column="ACCP"):
        """{(counter-offers bin, gap bin): mean of one column} for a head coach approval and player overall."""
        hcab, pogb = bin_of(approval, self.bins["EHCB"]), bin_of(overall, self.bins["POGB"])
        cells = {}
        for r in self.contract_rows:
            if r["HCAB"] == hcab and r["POGB"] == pogb and r[column] is not None:
                cells.setdefault((r["NCOB"], r["PCPG"]), []).append(r[column])
        return {k: mean(v) for k, v in cells.items()}

    # ---------- injured body parts ----------
    def group_for(self, ppos):
        return self.group_of.get(ppos)

    def ratings_lowered(self, pdrp, bdpt):
        """Rating ids the table says an injured body part lowers, for a position group."""
        return list(self.affected.get((pdrp, bdpt), []))

    def ratings_by_part(self, pdrp):
        """{rating id: [body part ids that lower it]} for a position group, in rating id order."""
        out = {}
        for bdpt in sorted(BODY_PART_NAMES):
            for rid in self.ratings_lowered(pdrp, bdpt):
                out.setdefault(rid, []).append(bdpt)
        return dict(sorted(out.items()))
