"""
What the defenders of the game's own plays do, in plain words, and how to give a defender another of the game's own assignments (standard library only, no Tk).

A defender's assignment is the step list his PLYS row points at (table PSLD, id PSAL); what the diagram draws for him is another row (table ARTD, id ARTL). The two are separate columns, so any
defender can be given any step list and any art row the game already has: nothing is invented and no row is added (the tables are full). Two facts of the data decide how:

  * A step list says WHAT the defender does (zone id, man on receiver n, rush, blitz ...). The zone it names is a fixed area of the field, whoever stands where.
  * The art is RELATIVE to the defender's spot: the zone is drawn at his spot plus the art's offset (hc09_plays.PlayLibrary.drawing). The same zone therefore has a different art row for
    each place a defender can stand, so the art row is chosen by where the defender is (best_art), from the rows the game already uses for that kind of zone.

The names ("deep half, left", "deep outer third, right", "hook, middle" ...) are read from the data (where the zone is drawn), not from the game's own screens, which are not known to name
them. Man coverage "receiver n" is the game's receiver number n of the offense. Not tried in the game: what the game does with a step list lent to another defender is the open question.
"""
import collections
import math

import hc09_plays as P

# (the step code, the kind it makes the list): the first one a list has is the list's main assignment
CORE_CODES = ((23, "deep"), (21, "hook"), (22, "curl_flat"), (20, "flat"), (19, "man"), (34, "spy"), (26, "blitz"), (41, "rush"))
WAIT_CODE = 24                         # "wait and read": the first step of many lists
ZONE_KINDS = ("deep", "hook", "curl_flat", "flat")
ZONE_ART_TYPES = (3, 4, 5)             # the art point types (ct) that are a zone's shape: 5 deep half, 4 deep third, 3 quarter / hook / flat / curl-flat

NAMES = {
    "deep": {0: "Deep half, left", 1: "Deep half, right", 2: "Deep outer third, left", 3: "Deep middle third", 4: "Deep outer third, right",
             5: "Deep quarter 1 (far left)", 6: "Deep quarter 2 (left-middle)", 7: "Deep quarter 3 (right-middle)", 8: "Deep quarter 4 (far right)"},
    "hook": {5: "Hook zone, far left", 4: "Hook zone, left", 3: "Hook zone, middle", 2: "Hook zone, right", 1: "Hook zone, far right"},
    "flat": {9: "Flat, left", 10: "Flat, right"},
    "curl_flat": {11: "Curl-flat, left", 12: "Curl-flat, right"},
}
# where each deep zone covers across the field (x of the diagram, 0 = left side line, 90 = the middle, 180 = right side line), from where the stock art draws it; used by the gap / overlap check
DEEP_SPAN = {0: (0, 90), 1: (90, 180), 2: (0, 60), 3: (60, 120), 4: (120, 180), 5: (0, 45), 6: (45, 90), 7: (90, 135), 8: (135, 180)}
EPOS_CLASS = {10: "line", 11: "line", 12: "line", 13: "linebacker", 14: "linebacker", 15: "linebacker", 16: "cornerback", 17: "safety", 18: "safety"}
HEADING_UNIT = 2.8125                  # degrees: the unit of a hook zone's heading (value 2), 0 = right, 32 = upfield, 64 = left
ART_TOLERANCE = 6.0                    # diagram units: a zone drawn farther than this from where it belongs is reported as an approximation


class Assignment(collections.namedtuple("Assignment", "kind ident words wait params steps")):
    """kind: deep, hook, curl_flat, flat, man, spy, blitz, rush or other. ident: the zone id, the receiver number, or None (for other: the whole step list). words: what it does in plain words.
    wait: the list starts with a wait and read. params: the step's other values (value 2 and 3: a hook's heading, a man's technique), copied from the game, never guessed."""
    __slots__ = ()

    @property
    def key(self):
        return (self.kind, self.ident)


def classify(steps):
    """The assignment a stock step list stands for: [(code, value 1, 2, 3), ...] (255 = end) -> Assignment."""
    codes = [tuple(s) for s in steps if s[0] != 255]
    wait = any(c[0] == WAIT_CODE for c in codes)
    for code, kind in CORE_CODES:
        step = next((c for c in codes if c[0] == code), None)
        if step is None:
            continue
        ident = step[1] if kind in ("deep", "hook", "curl_flat", "flat", "man") else None
        if kind in NAMES:
            base = NAMES[kind].get(ident, f"{kind.replace('_', '-').capitalize()} zone {ident}")
        elif kind == "man":
            base = f"Man on receiver {ident}"
        elif kind == "spy":
            base = "Spy the quarterback"
        elif kind == "blitz":
            base = "Blitz"
        else:
            base = "Rush the passer"
        return Assignment(kind, ident, base + (", after a wait and read" if wait else ""), wait, (step[2], step[3]), tuple(codes))
    return Assignment("other", tuple(codes), P.steps_in_words(codes, "defense") if codes else "nothing", wait, (0, 0), tuple(codes))


def group_words(key):
    """The plain words of an assignment group (kind, ident), without the wait."""
    kind, ident = key
    if kind in NAMES:
        return NAMES[kind].get(ident, f"{kind} {ident}")
    return {"man": f"Man on receiver {ident}", "spy": "Spy the quarterback", "blitz": "Blitz", "rush": "Rush the passer"}.get(kind, "Something else")


def _zone_point(art_row):
    """(ct, ax, ay) of the point of an art row that draws a zone (the last point of a zone type), or None."""
    pts = [q for q in P.decode_art(art_row) if q["ct"] in ZONE_ART_TYPES]
    return (pts[-1]["ct"], pts[-1]["ax"], pts[-1]["ay"]) if pts else None


class Pick(collections.namedtuple("Pick", "psal artl error group")):
    """The step list and art row chosen for a defender; error: how far (diagram units) the drawn zone is from where the zone belongs (None when the kind has no zone)."""
    __slots__ = ()


class Catalog:
    """The defensive assignments the game's own plays use, from a PlayLibrary: every step list classified, every stock defensive slot (a defender of a play) with where he stands, the zones' places."""

    def __init__(self, lib):
        self.lib = lib
        steps, arts = lib.steps["defense"], lib.art_rows["defense"]
        self.assignment = {psal: classify(lst) for psal, lst in steps.items()}
        self.zone_of_art = {artl: _zone_point(row) for artl, row in arts.items()}
        self.slots = []                                      # every defender of a stock defensive play
        self.uses = collections.Counter()                    # psal -> times a stock defender has it
        self.class_uses = collections.defaultdict(collections.Counter)      # position class -> group key -> times
        for p in lib.plays.values():
            s = lib.sets.get(p["setl"])
            if s is None or s["side"] != "defense":
                continue
            for sl in s["slots"]:
                row = lib.slot_rows.get(p["plyl"], {}).get(sl["poso"])
                if row is None or row["psal"] not in steps:
                    continue
                a = self.assignment[row["psal"]]
                self.slots.append({"plyl": p["plyl"], "poso": sl["poso"], "epos": sl["epos"], "dpos": sl["dpos"], "x": sl["x"], "y": sl["y"], "psal": row["psal"], "artl": row["artl"], "key": a.key})
                self.uses[row["psal"]] += 1
                self.class_uses[EPOS_CLASS.get(sl["epos"], "other")][a.key] += 1
        self.members = collections.defaultdict(dict)         # group key -> {psal: assignment}
        for psal, a in self.assignment.items():
            self.members[a.key][psal] = a
        # where each zone group belongs (the mean of the places the stock art draws it for the defenders that have it) and its art type
        pts = collections.defaultdict(list)
        for sl in self.slots:
            z = self.zone_of_art.get(sl["artl"])
            if z is not None and sl["key"][0] in ZONE_KINDS:
                pts[sl["key"]].append((sl["x"] + z[1], sl["y"] + z[2], z[0]))
        self.centre, self.art_type = {}, {}
        for key, lst in pts.items():
            self.centre[key] = (sum(p[0] for p in lst) / len(lst), sum(p[1] for p in lst) / len(lst))
            self.art_type[key] = collections.Counter(p[2] for p in lst).most_common(1)[0][0]
        self.art_groups = collections.defaultdict(collections.Counter)      # artl -> group key -> times used with it
        for sl in self.slots:
            self.art_groups[sl["artl"]][sl["key"]] += 1

    # ---- what a defender can be given
    def options(self, epos):
        """[(group key, words, times the game gives it to a defender of that position class)] the stock game gives to a defender of this kind (line, linebacker, cornerback, safety), most
        used first. 'Something else' lists are not offered: they are special lists the picker does not know."""
        used = self.class_uses.get(EPOS_CLASS.get(epos, "other"), {})
        out = [(key, group_words(key), n) for key, n in used.items() if key[0] != "other"]
        out.sort(key=lambda t: (-t[2], t[1]))
        return out

    def group_of_slot(self, plyl, poso):
        row = self.lib.slot_rows[plyl][poso]
        return self.assignment[row["psal"]]

    # ---- choosing the rows
    def best_art(self, key, spot, current_artl=None):
        """The art row for a defender standing at `spot` (x, y) with the zone of group `key`: among the art rows that draw this kind of zone, the one that lands the zone nearest to where it belongs
        (spot + the art's offset), rows the game already uses with this group first. Returns (artl, error); (None, None) when the group has no zone."""
        centre, ct = self.centre.get(key), self.art_type.get(key)
        if centre is None:
            return None, None
        best = None
        for artl, z in self.zone_of_art.items():
            if z is None or z[0] != ct:
                continue
            err = math.hypot(spot[0] + z[1] - centre[0], spot[1] + z[2] - centre[1])
            rank = (round(err), 0 if self.art_groups[artl].get(key) else 1, 0 if artl == current_artl else 1, artl)
            if best is None or rank < best[0]:
                best = (rank, artl, err)
        return (best[1], best[2]) if best else (None, None)

    def art_for_other(self, key, spot, current_artl=None):
        """The art row for a defender with an assignment that has no zone (man, rush, blitz, spy): the art row the stock game uses with this group for the defender who stands nearest to `spot`."""
        best = None
        for sl in self.slots:
            if sl["key"] != key:
                continue
            d = math.hypot(sl["x"] - spot[0], sl["y"] - spot[1])
            rank = (round(d), 0 if sl["artl"] == current_artl else 1, sl["artl"])
            if best is None or rank < best[0]:
                best = (rank, sl["artl"])
        return best[1] if best else None

    def pick(self, key, spot, current_psal=None, current_artl=None):
        """The step list and art row to give a defender at `spot` for group `key`: a Pick, or raises ValueError when the game has no such list."""
        members = self.members.get(key)
        if not members:
            raise ValueError(f"The game has no step list for \"{group_words(key)}\".")
        cur = self.assignment.get(current_psal)
        centre = self.centre.get(key)

        def rank(item):
            psal, a = item
            r = [0 if (cur is not None and a.wait == cur.wait) else 1]
            if key[0] == "hook" and centre is not None:             # a hook's heading points from the defender at the zone
                want = (math.degrees(math.atan2(-(centre[1] - spot[1]), centre[0] - spot[0])) % 360) / HEADING_UNIT
                r.append(abs((want - a.params[0] + 64) % 128 - 64))
            elif cur is not None and cur.kind == key[0]:
                r.append(0 if a.params == cur.params else 1)
            r.append(-self.uses[psal])
            r.append(psal)
            return tuple(r)
        psal = min(members.items(), key=rank)[0]
        if key[0] in ZONE_KINDS:
            artl, err = self.best_art(key, spot, current_artl)
        else:
            artl, err = self.art_for_other(key, spot, current_artl), None
        if artl is None:
            artl = current_artl
        return Pick(psal, artl, err, key)


def spot_of(slot):
    return (slot["x"], slot["y"])


# ---- reading a whole play
def play_assignments(cat, plyl):
    """[(poso, label, Assignment)] for each defender of a defensive play."""
    d = cat.lib.detail(plyl)
    return [(s["poso"], s["label"], cat.assignment[s["psal"]]) for s in d["slots"] if s["psal"] in cat.assignment]


def deep_ids(assignments):
    return sorted(a.ident for a in assignments if a.kind == "deep")


def shell_name(deep, man=0):
    """What the deep zones of a defense look like, in the words coaches use ('looks like': the editor does not know the game's own name for it). deep: the deep zone ids; man: how many defenders are in man."""
    deep = sorted(set(deep))
    if not deep:
        return "No deep zones" + (" (man coverage)" if man else "")
    if deep == [0, 1]:
        return "Two deep halves (Cover 2 shell)"
    if deep == [2, 3, 4]:
        return "Three deep thirds (Cover 3 shell)"
    if deep == [5, 6, 7, 8]:
        return "Four deep quarters (Cover 4 shell)"
    if deep == [3]:
        return "One deep middle third" + (" with man underneath (Cover 1 shell)" if man else "")
    if deep == [1, 5, 6]:
        return "Quarters to the left, a half to the right (Cover 6 shell)"
    if deep == [0, 7, 8]:
        return "A half to the left, quarters to the right (Cover 6 shell)"
    return "Deep zones " + ", ".join(NAMES["deep"][i] for i in deep)


def check(assignments):
    """Warnings for a set of assignments [(poso, label, Assignment)]: deep areas that overlap, deep areas nobody covers while others are covered, a receiver covered by two defenders. Each is a
    sentence. Nothing here stops a play; the game's own plays do some of these."""
    out = []
    deep = [(label, a.ident) for _p, label, a in assignments if a.kind == "deep"]
    spans = [(label, i, DEEP_SPAN[i]) for label, i in deep if i in DEEP_SPAN]
    for n, (l1, i1, s1) in enumerate(spans):
        for l2, i2, s2 in spans[n + 1:]:
            overlap = min(s1[1], s2[1]) - max(s1[0], s2[0])
            if overlap > 20:
                out.append(f"{l1} ({NAMES['deep'][i1].lower()}) and {l2} ({NAMES['deep'][i2].lower()}) cover much of the same deep area.")
    if spans:
        gaps, edge = [], 0
        for lo, hi in sorted(s for _l, _i, s in spans):
            if lo - edge > 25:
                gaps.append((edge, lo))
            edge = max(edge, hi)
        if 180 - edge > 25:
            gaps.append((edge, 180))
        for lo, hi in gaps:
            side = "the left" if hi <= 60 else ("the right" if lo >= 120 else "the middle")
            out.append(f"Nobody covers the deep area on {side} of the field (x {lo} to {hi}).")
    seen = collections.defaultdict(list)
    for _p, label, a in assignments:
        if a.kind == "man":
            seen[a.ident].append(label)
    for r, labels in sorted(seen.items()):
        if len(labels) > 1:
            out.append(f"Receiver {r} is covered by {' and '.join(labels)}.")
    return out


# ---- presets: they only fill in the deep defenders' assignments; the others keep what the play gives them
PRESETS = (
    ("cover2", "Cover 2: safeties deep halves, corners in the flats"),
    ("cover3", "Cover 3: corners and a safety in deep thirds"),
    ("cover4", "Cover 4: four deep quarters"),
    ("cover6_left", "Cover 6: quarters to the left, a half to the right"),
    ("cover6_right", "Cover 6: a half to the left, quarters to the right"),
)


def preset(name, slots, current=None):
    """The assignments a preset gives, {slot (poso): group key}, for the defenders of a play ([{poso, epos, x, ...}] as hc09_plays.PlayLibrary.detail gives them), or None with the reason (a ValueError
    text) when the formation does not have the defenders it needs. Defenders are placed by where they stand: cornerbacks and safeties from the left of the diagram (small x) to the right.
    current: {slot: group key} of what the defenders do now; a preset keeps a defender in the role he already has when it can (the safety who already has the deep middle third keeps it in Cover 3),
    so the other safety is not left with the same zone."""
    cbs = sorted((s for s in slots if s["epos"] == 16), key=lambda s: s["x"])
    sfs = sorted((s for s in slots if s["epos"] in (17, 18)), key=lambda s: s["x"])
    deep = sorted(cbs + sfs, key=lambda s: s["x"])

    def need(ok, text):
        if not ok:
            raise ValueError(text)
    if name == "cover2":
        need(len(sfs) >= 2 and len(cbs) >= 2, "Cover 2 needs two safeties and two cornerbacks; this formation has " + f"{len(sfs)} and {len(cbs)}.")
        return {sfs[0]["poso"]: ("deep", 0), sfs[-1]["poso"]: ("deep", 1), cbs[0]["poso"]: ("flat", 9), cbs[-1]["poso"]: ("flat", 10)}
    if name == "cover3":
        need(len(cbs) >= 2 and len(sfs) >= 1, "Cover 3 needs two cornerbacks and a safety; this formation has " + f"{len(cbs)} and {len(sfs)}.")
        holder = next((s for s in sfs if (current or {}).get(s["poso"]) == ("deep", 3)), None)
        mid = holder or min(sfs, key=lambda s: abs(s["x"] - 90))
        return {cbs[0]["poso"]: ("deep", 2), mid["poso"]: ("deep", 3), cbs[-1]["poso"]: ("deep", 4)}
    if name in ("cover4", "cover6_left", "cover6_right"):
        need(len(deep) >= 4, f"{name.replace('cover', 'Cover ').replace('_', ' ')} needs four cornerbacks and safeties; this formation has {len(deep)}.")
        four = sorted(_outer_four(cbs, sfs), key=lambda s: s["x"])
        a, b, c, d = four
        if name == "cover4":
            ids = (5, 6, 7, 8)
            return {a["poso"]: ("deep", ids[0]), b["poso"]: ("deep", ids[1]), c["poso"]: ("deep", ids[2]), d["poso"]: ("deep", ids[3])}
        if name == "cover6_left":              # quarters on the left side, one half on the right (the two on the right share it: the outer one drops out of the deep zones to the flat)
            return {a["poso"]: ("deep", 5), b["poso"]: ("deep", 6), c["poso"]: ("deep", 1), d["poso"]: ("flat", 10)}
        return {a["poso"]: ("flat", 9), b["poso"]: ("deep", 0), c["poso"]: ("deep", 7), d["poso"]: ("deep", 8)}
    raise ValueError("Unknown preset " + name)


def _outer_four(cbs, sfs):
    """The four deep defenders of a base defense: the two outermost cornerbacks and the two safeties (or, with fewer safeties, the next cornerbacks in)."""
    four = list(cbs[:1]) + list(cbs[-1:]) if len(cbs) >= 2 else list(cbs)
    rest = [s for s in cbs if s not in four]
    pool = list(sfs) + sorted(rest, key=lambda s: abs(s["x"] - 90))
    four += pool[:4 - len(four)]
    return four


def zone_extent(key, centre):
    """(x0, y0, x1, y1) of the rectangle a zone covers, for the preview: a deep zone spans the field x range it covers (DEEP_SPAN); hooks and flats are small areas around their centre. The editor's own
    estimate of the area (the data gives the zone's centre, not its size)."""
    cx, cy = centre
    kind, ident = key
    if kind == "deep" and ident in DEEP_SPAN:
        lo, hi = DEEP_SPAN[ident]
        return (lo, cy - 8, hi, cy + 8)
    half = {"hook": (14, 8), "flat": (14, 7), "curl_flat": (16, 9)}.get(kind, (10, 8))
    return (cx - half[0], cy - half[1], cx + half[0], cy + half[1])
