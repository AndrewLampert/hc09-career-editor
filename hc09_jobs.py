"""
What a player can be asked to do, in the words a coach uses (Slant, Post, Out, Pass block, Deep zone - left ...), for a simple play editor: the game's own assignments grouped by
what they are, each with the assignment (step list, art and role code) that does it for a player standing where this one stands.

Standard library only (no Tk). Built on hc09_plays.PlayLibrary, hc09_playtypes.PlayTypes (what fits which kind of play) and hc09_routes (names of routes). The catalogue is
read from the game's own plays: every stock slot's assignment is named and counted, and a choice's assignment is the one the game's plays most use for that kind of player
on that side of the field (a route's art is drawn from the player's own spot, so a left-side player needs the left-side version of a slant).
"""
import collections

from hc09_plays import steps_in_words
from hc09_playtypes import FAMILIES, FAMILY_NAME, FAMILY_TEXT, ROLE_OF_EPOS, behavior, signature, qb_family
from hc09_routes import CENTER_X, ROUTE_ORDER, classify, depth_word

OFFENSE_CATEGORIES = ("Routes", "Blocks", "Carry the ball", "Option and pitch", "Quarterback", "Other")
DEFENSE_CATEGORIES = ("Pass rush", "Blitz", "Man coverage", "Zones", "Spy", "Other")
SIDE_MARGIN = 8           # a player this close to the middle of the field is "in the middle"


def side_of(x):
    return "L" if x < CENTER_X - SIDE_MARGIN else ("R" if x > CENTER_X + SIDE_MARGIN else "C")


def group_of(table, epos):
    """The kind of player a choice list is for: QB, HB, FB, WR, TE, OL on offense; DL, LB, DB on defense (None for a slot that is neither)."""
    if table == "offense":
        return ROLE_OF_EPOS.get(epos)
    return "DL" if epos in (10, 11, 12) else ("LB" if epos in (13, 14, 15) else ("DB" if epos in (16, 17, 18) else None))


class JobCatalog:
    """The named assignments of the game's offensive and defensive plays."""

    def __init__(self, lib, types=None):
        self.lib = lib
        self.types = types
        # (table, group, side) -> {(label, category): Counter of entries}
        self.items = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        self.info = {}                 # (label, category) -> {"name", "depth_word"}
        self._index()

    # ---- naming
    def label(self, table, epos, x, y, entry):
        """(label, category, extra) of an assignment for a player at (x, y): extra is {"name", "depth_word"} for routes."""
        psal, artl, plrr = entry
        steps = self.lib.steps_of(table, psal)
        sig = signature(steps)
        words = steps_in_words(steps, table, epos)
        art = self.lib.art_of(table, artl)
        if table == "offense":
            if epos == 0:
                fam = qb_family(sig)
                return (f"{FAMILY_NAME[fam]}: {words}" if fam else words), "Quarterback", {}
            beh = behavior(sig)
            if beh == "route":
                c = classify(art, x)
                if c and c["name"] != "Other":
                    motion = ", after motion" if 45 in sig else ""
                    depth = "" if c["name"] in ("Go", "Fade", "Wheel") else f", {c['depth_word']}"       # these are deep by definition; the art's squeezed scale would say otherwise
                    return f"{c['name']}{depth}{motion}", "Routes", {"name": c["name"], "depth_word": c["depth_word"]}
                return "Other route: " + words, "Routes", {}
            if beh in ("pass block", "run block"):
                return words[:1].upper() + words[1:], "Blocks", {}
            if beh == "carry":
                return "Carry the ball: " + words, "Carry the ball", {}
            if beh == "option":
                return words[:1].upper() + words[1:], "Option and pitch", {}
            return words[:1].upper() + words[1:], "Other", {}
        # defense: the words, with where the zone is or which way the rush goes when the art shows it
        pts = [q for q in art if (q["ax"], q["ay"]) != (0, 0)]
        zone = [q for q in pts if q["ct"] == 3]
        cats = {41: "Pass rush", 26: "Blitz", 19: "Man coverage", 34: "Spy", 20: "Zones", 21: "Zones", 22: "Zones", 23: "Zones"}
        codes = [c for c in sig if c in cats]
        first = next((c for c in sig if c in (41, 26, 19, 34, 20, 21, 22, 23)), None)
        category = cats.get(first, "Other")
        if 26 in sig and 41 in sig:
            category = "Blitz"
        text = words[:1].upper() + words[1:]
        if zone and first in (20, 21, 22, 23):
            zx, zy = x + zone[-1]["ax"], y + zone[-1]["ay"]
            where = "left" if zx < 55 else ("right" if zx > 125 else "middle")
            how = "deep" if zy < 30 else ("medium" if zy < 52 else "short")
            text = f"{text}: {how}, {where}"
        elif pts and category in ("Pass rush", "Blitz"):
            dx = pts[-1]["ax"]
            text = f"{text}: " + ("to the left" if dx < -10 else ("to the right" if dx > 10 else "straight ahead"))
        return text, category, {}

    # ---- index
    def _index(self):
        lib = self.lib
        for plyl, play in lib.plays.items():
            s = lib.sets.get(play["setl"])
            if not s or s["side"] not in ("offense", "defense"):
                continue
            table = s["table"]
            for sl in s["slots"]:
                row = lib.slot_rows.get(plyl, {}).get(sl["poso"])
                group = group_of(table, sl["epos"])
                if row is None or group is None:
                    continue
                entry = (row["psal"], row["artl"], row["plrr"])
                if not lib.steps_of(table, entry[0]):
                    continue
                label, cat, extra = self.label(table, sl["epos"], sl["x"], sl["y"], entry)
                self.items[(table, group, side_of(sl["x"]))][(label, cat)][entry] += 1
                if extra:
                    self.info[(label, cat)] = extra

    # ---- what a player can be asked to do
    def choices(self, table, epos, dpos, x, kind=None, only_fitting=True):
        """The assignments a player at x can be given, as [{"category", "label", "entry": (psal, artl, plrr), "uses", "words"}]. On offense, with only_fitting and a kind of play
        (a hc09_playtypes key), only those typical of that position in that kind of play (a receiver's route in a handoff run is shipped but atypical, so it is hidden until asked for); the quarterback's list is one per kind of play."""
        group = group_of(table, epos)
        out = []
        if group is None:
            return out
        if table == "offense" and epos == 0:
            return self._quarterback_choices()
        side = side_of(x)
        merged = collections.defaultdict(collections.Counter)
        for s in (["C", "L", "R"] if side == "C" else [side]):                 # a route's art is drawn from the player's own spot: same side of the field
            for key, entries in self.items.get((table, group, s), {}).items():
                merged[key].update(entries)
        for s in ("L", "C", "R"):                                              # blocks, carries and the like do not depend on the side
            if s == side:
                continue
            for key, entries in self.items.get((table, group, s), {}).items():
                if key not in merged and key[1] not in ("Routes", "Zones", "Pass rush", "Blitz"):
                    merged[key].update(entries)
        for (label, cat), entries in merged.items():
            entry = self._pick(entries, table, epos)
            if table == "offense" and only_fitting and kind and self.types is not None and not self.types.slot_fine(kind, epos, dpos, entry):
                continue
            out.append({"category": cat, "label": label, "entry": entry, "uses": sum(entries.values()), "words": steps_in_words(self.lib.steps_of(table, entry[0]), table, epos)})
        order = {c: i for i, c in enumerate(OFFENSE_CATEGORIES if table == "offense" else DEFENSE_CATEGORIES)}
        depth_rank = {"short": 0, "medium": 1, "deep": 2}

        def sort_key(r):
            if r["category"] == "Routes" and r["label"].split(",")[0] in ROUTE_ORDER:
                parts = [x.strip() for x in r["label"].split(",")]
                return (order.get(r["category"], 99), ROUTE_ORDER.index(parts[0]), depth_rank.get(parts[1] if len(parts) > 1 else "", -1), len(parts), -r["uses"])
            return (order.get(r["category"], 99), 99, 0, 0, -r["uses"], r["label"])
        out.sort(key=sort_key)
        return out

    def _pick(self, entries, table, epos):
        """The entry of a choice that the game's plays use most (ties by the lower ids)."""
        return max(entries.items(), key=lambda kv: (kv[1], -kv[0][0], -kv[0][1]))[0]

    def _quarterback_choices(self):
        out = []
        if self.types is None:
            return out
        for key, name, kind, text in FAMILIES:
            entry = self.types.best_entry(key, 0)
            if entry is None:
                continue
            out.append({"category": "Quarterback", "label": f"{name}: {steps_in_words(self.lib.steps_of('offense', entry[0]), 'offense', 0)}", "entry": entry,
                        "uses": len(self.types.members[key]), "words": text})
        return out

    def label_of(self, table, epos, x, y, entry):
        """The label this catalogue gives an assignment for a player (to find the current choice in a list)."""
        return self.label(table, epos, x, y, entry)[:2]
