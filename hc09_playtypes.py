"""
The kinds of offensive play the game has (dropback pass, play action, handoff, toss, option ...), read from the plays' own step lists, and a way to turn one
play into another kind so that every player's assignment fits (a prototype of the "make this play action" button of a play editor).

Standard library only (no Tk). Built on hc09_plays.PlayLibrary. How it works (see docs/hc09_play_creator.md for the numbers):

- A play's kind shows in the quarterback's steps: 3 7 (drop back, read and throw) is a dropback pass, 38 40 7 (turn, play-action fake, read and throw) is play
  action, 38 39 5 (turn, hand off, carry out the fake) a handoff run, 11 5 (pitch) a toss, 12 42 1 the triple option, 26 42 1 the speed option, and so on. The
  quarterback's list is the same in at least 84% of the stock plays of a kind and in all of them for several kinds.
- The other players follow the kind too: the linemen all pass block (14) in a dropback pass, run block then pass block (15 14) in play action, run block (15) in a run;
  a back mesh-fakes (26 13 14) in play action and takes the handoff (26 13 1) in a run. Receivers' routes are free (any route is fine in a pass) and in a run they block.
- convert() changes only what does not fit the target kind: it takes the quarterback's, the linemen's and the backs' assignments from a stock play of the target kind
  that uses the same set (so the art and the alignment match and the combination is one the game ships), else from the most common ones of that kind, keeps receivers'
  routes where the kind allows routes, and gives the PLYT / PLPD / PLRD / PLCM rows that go with the kind.
"""
import collections

from hc09_plays import steps_in_words

# key, name, kind (what the quarterback ends with: 7 is a pass, anything else a run), one-line description
FAMILIES = (
    ("dropback", "Dropback pass", "pass", "the quarterback drops back and throws; the linemen pass block"),
    ("play_action", "Play-action pass", "pass", "the quarterback turns and fakes the handoff, then throws; the linemen run block first, then pass block"),
    ("option_pass", "Option pass", "pass", "an option read that ends in a throw"),
    ("handoff", "Handoff run", "run", "the quarterback hands off; the back takes the handoff and runs the hole; the linemen run block"),
    ("toss", "Toss / pitch run", "run", "the quarterback pitches to the back"),
    ("speed_option", "Speed (read) option", "run", "the quarterback reads the end and keeps or pitches"),
    ("triple_option", "Triple option", "run", "the quarterback rides the fullback, then keeps or pitches"),
    ("qb_run", "QB run (keeper, sneak, choice)", "run", "the quarterback runs"),
    ("fake_run", "Fake run (fake handoff)", "run", "the quarterback fakes the handoff and the play is a run by someone else"),
)
FAMILY_NAME = {k: n for k, n, *_ in FAMILIES}
FAMILY_KIND = {k: kind for k, _, kind, _ in FAMILIES}
FAMILY_TEXT = {k: t for k, _, _, t in FAMILIES}
ROLE_OF_EPOS = {0: "QB", 1: "HB", 2: "FB", 3: "WR", 4: "TE", 5: "OL", 6: "OL", 7: "OL", 8: "OL", 9: "OL"}


def role_of(epos, dpos):
    """The role a slot is grouped under: the quarterback, the first and later halfbacks and fullbacks (a second back usually leads or blocks), receivers, tight ends, linemen."""
    role = ROLE_OF_EPOS.get(epos)
    if role in ("HB", "FB"):
        return role + ("1" if dpos == 1 else "2")
    return role
CLASS_WORDS = {"route": "a route", "carry": "carrying the ball", "pass block": "a pass block", "run block": "a run block", "move": "a lead or release path", "option": "an option step",
               "none": "nothing"}
SHARE_MIN = 0.10          # typical: a kind of behaviour is typical of a kind when at least this share of the stock slots of that role in it have it
FIRST_MIN = 0.08          # typical: for the backs, the lead step (the first that is not a wait or a motion step) is one at least this share of that role in the kind starts with
OL_MIN = 0.12             # typical: for the linemen, the whole step list is one that at least this share of the kind's linemen have (run block, then pass block in play action)
SEEN_MIN = 1              # allowed: the game ships at least this many slots of that role with that behaviour in the kind (a hard rule: never seen means it does not work)
TYPICAL_COUNT = 3         # typical also needs this many slots, so that a kind with few plays does not call one odd slot typical


# a role the kind has no stock plays for (a second fullback in a toss, say) is judged like the closest role it has
ROLE_FALLBACK = {"FB2": ("FB1", "HB2", "HB1"), "HB2": ("FB2", "FB1", "HB1"), "FB1": ("HB2", "HB1"), "HB1": ("FB1", "HB2"), "TE": ("WR",), "WR": ("TE",)}


def signature(steps):
    return tuple(c for c, *_ in steps if c != 255)


def qb_family(sig):
    """The kind of play a quarterback's step signature says, or None."""
    if not sig:
        return None
    if 42 in sig:
        if sig[-1] == 7:
            return "option_pass"
        if sig[-1] == 1:
            return "triple_option" if sig[0] == 12 else "speed_option"
        return None
    if sig[:2] == (38, 40):
        return "play_action" if sig[-1] == 7 else "fake_run"
    if sig == (12, 3, 7):
        return "play_action"
    if sig[-1] == 7 and sig[0] == 3:
        return "dropback"
    if 39 in sig:
        return "handoff"
    if sig[0] == 11:
        return "toss"
    if sig[-1] == 1:
        return "qb_run"
    return None


def lead(sig):
    """The first step that is not a wait or a pre-snap motion step: what a player really starts with (the mesh, the release, the route)."""
    for c in sig:
        if c not in (25, 45, 46):
            return c
    return None


def behavior(sig):
    """What a step signature does in broad terms: route, carry, pass block, run block, option, or move (a lead or release path)."""
    s = tuple(c for c in sig if c not in (45, 46, 25))          # motion and waiting do not change what the play asks of the player
    if not s:
        return "none"
    if 42 in s or 43 in s:
        return "option"
    if s[-1] == 10:
        return "route"
    if s[-1] == 1:
        return "carry"
    if s[-1] == 14:
        return "pass block"
    if s[-1] == 15:
        return "run block"
    return "move"


class PlayTypes:
    """The kinds of play of a PlayLibrary's offensive plays: detection, comparison, validation and conversion."""

    def __init__(self, lib):
        self.lib = lib
        self.steps = lib.steps["offense"]
        self.family = {}                                              # plyl -> kind
        self.members = collections.defaultdict(list)                  # kind -> [plyl]
        self.by_set = collections.defaultdict(lambda: collections.defaultdict(list))   # setl -> kind -> [plyl]
        self.sig_count = collections.defaultdict(collections.Counter)  # (kind, role) -> Counter of signatures
        self.class_count = collections.defaultdict(collections.Counter)  # (kind, role) -> Counter of behaviours
        self.first_count = collections.defaultdict(collections.Counter)  # (kind, role) -> Counter of first steps
        self.entry_count = collections.defaultdict(collections.Counter)  # (kind, role key) -> Counter of (psal, artl, plrr)
        self.plyt_count = collections.defaultdict(collections.Counter)
        self.hole_count = collections.defaultdict(collections.Counter)
        self.per_values = collections.defaultdict(lambda: collections.defaultdict(list))
        self._index()

    # ---- index
    def entry_sig(self, entry):
        return signature(self.steps.get(entry[0], []))

    def role_key(self, epos, dpos=1):
        """The key entries are collected under: each position for the quarterback and the linemen (their art differs), the role for the rest."""
        return epos if epos == 0 or 5 <= epos <= 9 else role_of(epos, dpos)

    def _index(self):
        lib = self.lib
        for plyl, play in lib.plays.items():
            s = lib.sets.get(play["setl"])
            if not s or s["side"] != "offense":
                continue
            slots = lib.slot_rows.get(plyl, {})
            qb = next((x for x in s["slots"] if x["epos"] == 0), None)
            if qb is None or qb["poso"] not in slots:
                continue
            fam = qb_family(signature(self.steps.get(slots[qb["poso"]]["psal"], [])))
            if fam is None:
                continue
            self.family[plyl] = fam
            self.members[fam].append(plyl)
            self.by_set[s["setl"]][fam].append(plyl)
            self.plyt_count[fam][play["plyt"]] += 1
            for sl in s["slots"]:
                row = slots.get(sl["poso"])
                if row is None:
                    continue
                role = role_of(sl["epos"], sl["dpos"])
                if role is None:
                    continue
                entry = (row["psal"], row["artl"], row["plrr"])
                sig = self.entry_sig(entry)
                self.sig_count[(fam, role)][sig] += 1
                self.class_count[(fam, role)][behavior(sig)] += 1
                self.first_count[(fam, role)][lead(sig)] += 1
                self.entry_count[(fam, self.role_key(sl["epos"], sl["dpos"]))][entry] += 1
            for r in lib.running.get(plyl, []):
                self.hole_count[fam][int(r["hole"])] += 1
            pr = lib.passing.get(plyl)
            if pr is not None:
                for k in range(1, 6):
                    self.per_values[fam][k].append((int(pr[f"rcv{k}"]), int(pr[f"per{k}"])))

    # ---- what a kind asks of each role
    def effective_role(self, fam, role):
        """The role itself if the kind has stock slots for it, else the closest role it has."""
        if sum(self.class_count[(fam, role)].values()):
            return role
        for other in ROLE_FALLBACK.get(role, ()):
            if sum(self.class_count[(fam, other)].values()):
                return other
        return role

    def share(self, fam, role, sig):
        c = self.sig_count[(fam, role)]
        total = sum(c.values())
        return c[sig] / total if total else 0.0

    def class_ok(self, fam, role, cls, typical=False):
        """Is this behaviour part of the kind for the role: typical (SHARE_MIN of the stock slots) or just allowed (the game ships it, SEEN_MIN times)?"""
        c = self.class_count[(fam, self.effective_role(fam, role))]
        total = sum(c.values())
        if not total:
            return False
        return (c[cls] / total >= SHARE_MIN and c[cls] >= TYPICAL_COUNT) if typical else c[cls] >= SEEN_MIN

    def top_signature(self, fam, role):
        c = self.sig_count[(fam, role)]
        return c.most_common(1)[0][0] if c else ()

    def best_entry(self, fam, epos, dpos=1):
        """The most common (psal, artl, plrr) of a kind for a position: for receivers, the most common among the entries whose signature is the kind's most common one."""
        role = self.effective_role(fam, role_of(epos, dpos))
        key = self.role_key(epos, dpos) if role == role_of(epos, dpos) else role
        c = self.entry_count[(fam, key)]
        if not c:
            return None
        top = self.top_signature(fam, role)
        for entry, _ in c.most_common():
            if self.entry_sig(entry) == top:
                return entry
        return c.most_common(1)[0][0]

    def plyt_values(self, fam):
        return [t for t, _ in self.plyt_count[fam].most_common()]

    # ---- detection and validation
    def family_of_play(self, plyl):
        return self.family.get(plyl)

    def _qb(self, setl):
        return next((x for x in self.lib.sets[setl]["slots"] if x["epos"] == 0), None)

    def family_of_assignments(self, setl, assign):
        """The kind a set's assignments make: from the quarterback's (assign is {poso: (psal, artl, plrr)})."""
        qb = self._qb(setl)
        if qb is None or qb["poso"] not in assign:
            return None
        return qb_family(self.entry_sig(assign[qb["poso"]]))

    def slot_fine(self, fam, epos, dpos, entry, lenient=False):
        """Does one player's assignment fit a kind? The quarterback must have a signature that reads as that kind. Others must do something the game ships in the kind;
        unless lenient they must also do something typical of it (SHARE_MIN) and, for the backs, start the way the kind's backs do (the mesh, the handoff, the pitch).
        validate() asks leniently (does it work?), convert() strictly (does it look like that kind of play?) except for the slots the user chose."""
        role = role_of(epos, dpos)
        sig = self.entry_sig(entry)
        if role is None:
            return True
        if role == "QB":
            return qb_family(sig) == fam
        cls = behavior(sig)
        if not self.class_ok(fam, role, cls, typical=not lenient):
            return False
        if lenient:
            return True
        if role == "OL":
            return self.share(fam, role, sig) >= OL_MIN
        if cls == "route" or role not in ("HB1", "HB2", "FB1", "FB2"):
            return True
        c = self.first_count[(fam, self.effective_role(fam, role))]
        total = sum(c.values())
        return bool(total) and c[lead(sig)] / total >= FIRST_MIN

    def validate(self, setl, assign, fam):
        """[(poso, label, text)] for each player whose assignment does not fit the kind (empty if the play works as that kind)."""
        out = []
        for sl in self.lib.sets[setl]["slots"]:
            entry = assign.get(sl["poso"])
            if entry is None or self.slot_fine(fam, sl["epos"], sl["dpos"], entry, lenient=True):
                continue
            label = self._label(sl)
            sig = self.entry_sig(entry)
            what = steps_in_words(self.steps.get(entry[0], []), "offense", sl["epos"])
            if sl["epos"] == 0:
                text = f"{label}: \"{what}\" is not how a {FAMILY_NAME[fam].lower()} starts"
            else:
                role = role_of(sl["epos"], sl["dpos"])
                cls = behavior(sig)
                if not self.class_ok(fam, role, cls):
                    text = f"{label}: {CLASS_WORDS[cls]} (\"{what}\") is not part of a {FAMILY_NAME[fam].lower()}"
                else:
                    text = f"{label}: \"{what}\" does not start the way the game's {role[:2]} do in a {FAMILY_NAME[fam].lower()}"
            out.append((sl["poso"], label, text))
        return out

    def _label(self, sl):
        from hc09_plays import POSITIONS
        base = POSITIONS.get(sl["epos"], str(sl["epos"]))
        return base + (str(sl["dpos"]) if sl["epos"] in (1, 2, 3, 4) else "")

    # ---- conversion
    def _tables_synth(self, fam, base_plyl, assign, setl):
        """PLPD / PLRD rows for a kind when no stock play of it uses the set: the read order from the receivers' routes with the kind's usual percentages, the hole the
        base play had (or the kind's most common)."""
        lib = self.lib
        kind = FAMILY_KIND[fam]
        if kind == "pass":
            slots = lib.sets[setl]["slots"]
            order = {3: 0, 4: 1, 1: 2, 2: 3}
            runners = [sl for sl in slots if behavior(self.entry_sig(assign[sl["poso"]])) == "route"]
            runners.sort(key=lambda sl: (order.get(sl["epos"], 9), sl["dpos"]))
            chosen = [sl["poso"] for sl in runners][:5]
            others = [sl["poso"] for sl in slots if sl["poso"] not in chosen and sl["epos"] in (1, 2, 3, 4)]
            chosen += others[:5 - len(chosen)]
            while len(chosen) < 5:
                chosen.append(chosen[-1] if chosen else 1)
            pers = []
            for k in range(1, 6):
                vals = sorted(p for _, p in self.per_values[fam][k]) or [0]
                pers.append(vals[len(vals) // 2])
            row = {}
            for k in range(5):
                row[f"rcv{k + 1}"] = chosen[k]
                row[f"per{k + 1}"] = pers[k]
            return {"PLPD": row}
        hole = None
        base_rows = lib.running.get(base_plyl, [])
        if base_rows:
            hole = int(base_rows[0]["hole"])
        elif self.hole_count[fam]:
            hole = self.hole_count[fam].most_common(1)[0][0]
        return {"PLRD": [{"hole": hole if hole is not None else 0}]}

    def pick_sibling(self, setl, fam, cur, plyt, exclude=None):
        """The stock play of the kind in the same set that is closest to the current assignments (the most players the same, then the same PLYT)."""
        best, best_key = None, None
        for q in self.by_set[setl][fam]:
            if q == exclude:
                continue
            rows = self.lib.slot_rows.get(q, {})
            same = sum(1 for poso, row in rows.items() if cur.get(poso) == (row["psal"], row["artl"], row["plrr"]))
            key = (same, self.lib.plays[q]["plyt"] == plyt, -q)
            if best_key is None or key > best_key:
                best, best_key = q, key
        return best

    def convert(self, plyl, target, current=None, keep=()):
        """Plan turning a play into another kind. current is {poso: (psal, artl, plrr)} (the play's own if None, or with the user's edits); keep is the set of slots the
        user chose by hand, which stay unless they cannot work in the kind. Returns {"family", "overrides": {poso: entry} (only the slots that change), "changes":
        [{"poso", "label", "old", "new", "why"}], "plyt", "tables_from" (a stock play whose PLPD / PLRD / PLCM to copy, or None), "tables" (synthesised rows when there is
        none), "source" (words), "issues" (what still does not fit, empty normally)}."""
        lib = self.lib
        play = lib.plays[plyl]
        s = lib.sets[play["setl"]]
        base = {poso: (row["psal"], row["artl"], row["plrr"]) for poso, row in lib.slot_rows.get(plyl, {}).items()}
        cur = dict(current) if current is not None else dict(base)
        already = self.family.get(plyl) == target       # the play (as the game has it) already is that kind: only what cannot work is fixed
        sib = self.pick_sibling(s["setl"], target, cur, play["plyt"], exclude=plyl)
        sib_entries = {poso: (row["psal"], row["artl"], row["plrr"]) for poso, row in lib.slot_rows.get(sib, {}).items()} if sib is not None else {}
        out = dict(cur)
        changes = []
        for sl in s["slots"]:
            poso = sl["poso"]
            if poso not in cur:
                continue
            entry = cur[poso]
            if self.slot_fine(target, sl["epos"], sl["dpos"], entry, lenient=already or poso in keep):
                continue
            new = sib_entries.get(poso) or self.best_entry(target, sl["epos"], sl["dpos"])
            if new is None or new == entry:
                continue
            out[poso] = new
            changes.append({"poso": poso, "label": self._label(sl), "old": steps_in_words(self.steps.get(entry[0], []), "offense", sl["epos"]),
                            "new": steps_in_words(self.steps.get(new[0], []), "offense", sl["epos"]), "why": "from " + (f"\"{lib.plays[sib]['name']}\"" if sib is not None else "the kind's usual assignments")})
        plyt = play["plyt"] if play["plyt"] in self.plyt_count[target] else (lib.plays[sib]["plyt"] if sib is not None else (self.plyt_values(target) or [play["plyt"]])[0])
        tables = {}
        if sib is None:
            tables = self._tables_synth(target, plyl, out, s["setl"])
        issues = self.validate(s["setl"], out, target)
        return {"family": target, "overrides": {poso: e for poso, e in out.items() if e != base.get(poso)}, "changes": changes, "plyt": plyt, "tables_from": sib,
                "tables": tables, "source": (f"the play \"{lib.plays[sib]['name']}\" of the same set" if sib is not None else "the usual assignments of that kind of play"),
                "issues": issues}

    # ---- the comparison
    def comparison(self, kinds=None):
        """Rows for a table of the kinds: {"key", "name", "kind", "plays", "plyt": [(value, plays)], "qb": [(signature words, share)], "roles": {role: [(words, share)]},
        "tables": which of PLPD / PLRD / PLCM the stock plays have}. Top three step lists per role."""
        lib = self.lib
        rows = []
        for key, name, kind, text in FAMILIES:
            if kinds and key not in kinds:
                continue
            n = len(self.members[key])
            roles = {}
            for role in ("QB", "HB1", "HB2", "FB1", "TE", "WR", "OL"):
                c = self.sig_count[(key, role)]
                tot = sum(c.values())
                epos = {"QB": 0, "HB1": 1, "HB2": 1, "FB1": 2, "TE": 4, "WR": 3, "OL": 5}[role]
                roles[role] = [(steps_in_words([(code, 0, 0, 0) for code in sig], "offense", epos), round(100 * v / tot)) for sig, v in c.most_common(3)] if tot else []
            tabs = {t: sum(1 for q in self.members[key] if present(q)) for t, present in (("PLPD", lambda q: q in lib.passing), ("PLRD", lambda q: q in lib.running), ("PLCM", lambda q: q in lib.combos))}
            rows.append({"key": key, "name": name, "kind": kind, "text": text, "plays": n, "plyt": self.plyt_count[key].most_common(), "roles": roles, "tables": tabs})
        return rows
