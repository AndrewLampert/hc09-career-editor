"""
Adding a play to the game's own play database, so that the game treats it as a normal play (flip, hot routes, adjustments; the computer does not call it, see free_play_id): the rows of a new play go into the master
play database (qkl_boot.ast entry 40), its compact copy (entry 42), the playbooks' names for it (entry 46, PPPN) and the user-profile template's links (entry 47, PGPL), and the
playbook links go into the profile (a new career copies its links from the PROFILE, not from the game file) and into the careers that should have the play.

Every table of the game's database is exactly full and the archive's entries follow each other without a gap, so the bridge (add-play) writes bigger copies of the four entries at the
END of qkl_boot.ast and points the table of contents at them (proven in the game: the play shows in the playbook, runs, and can be flipped and have its routes changed). This module only
works out the ROWS from what the Play creator shows; the bridge puts them in, checks them and keeps what is needed to put the files back byte for byte. No Tk.

A play whose players line up somewhere else than in the stock formation (set) needs a formation of its own: every play of a set shares its alignment, so moving a player in the stock set
would move him in all of them (the set "Big" has 86 plays). Such a play gets a NEW set, a copy of the stock one with only the moved players' places changed (its slots, the places in each
alignment group, the groups, the quick-sub packages; NOT the compact copy's slots, which crash the game: see new_set_rows), linked into the same playbooks as the stock set.
"""
import collections
import copy

import hc09_gamefiles as GF
import hc09_plays as P

ENTRIES = (40, 42, 46, 47)
PASS_COLS = tuple(f"{a}{k}" for k in range(1, 6) for a in ("per", "rcv"))
TEXT_COLS = {"name", "PPPM"}
LINK_TABLES = {"PGPL": ("BOKL", "SETL", "PLYL", "PLTP"), "PGSL": ("BOKL", "SETL", "PBFM"), "PGSS": ("BOKL", "SETL")}      # the playbook link tables of a save and their columns
LINK_KEYS = {"PGPL": ("BOKL", "SETL", "PLYL"), "PGSL": ("BOKL", "SETL"), "PGSS": ("BOKL", "SETL")}
SET_TABLES = ("SETL", "SETP", "SETG", "SGFF", "SPKF", "SPKG")          # the tables of entry 40 that hold a set: every play in an added formation carries these rows, merge() writes them once
SHARED_ROWS = {"40": SET_TABLES, "47": ("PGSL", "PGSS")}


def _num(row):
    """A row as the bridge takes it: numbers as numbers, the text columns as text."""
    return {k: (str(v) if k in TEXT_COLS else int(v)) for k, v in row.items()}


STOCK_MAX_PLYL = 7459           # the highest play id of the stock PS3 game (Man Blitz): the fallback when the library has no plays; the archive's own highest id is used (stock_max_play)
MAX_PLYL = 16383                # the play id field is 14 bits wide
TESTED_GAME = {"plays": 3099, "sets": 240, "max_play": 7459, "max_set": 500}          # the stock game the editor was tried on (RPCS3, the PS3 game): game_differs compares an archive with it


def stock_max_play(lib, added=()):
    """The highest play id of the stock game in THIS archive: the highest id of the library that is not an added play (added: the added plays or their ids; the mounted custom plays sit far above
    and are not the game's). The PS3 game's 7459 when the library has no plays."""
    skip = {int(a["plyl"]) if isinstance(a, dict) else int(a) for a in added}
    ids = [int(k) for k in lib.plays if int(k) < P.CUSTOM_OFFSETS["PLYL"] and int(k) not in skip]
    return max(ids) if ids else STOCK_MAX_PLYL


def stock_max_set(lib, added=()):
    """The highest set (formation) id of the stock game in this archive, without the sets of the added plays."""
    skip = {int(a["new_set"]) for a in added if isinstance(a, dict) and a.get("new_set")}
    ids = [int(k) for k in lib.sets if int(k) < P.CUSTOM_OFFSETS["SETL"] and int(k) not in skip]
    return max(ids) if ids else STOCK_MAX_SETL


def game_differs(lib, added=()):
    """How this archive differs from the game the editor was tried on: a list of sentences, empty when the counts and the highest ids are those of the stock PS3 game (3,099 plays, 240 sets, highest
    play 7459, highest set 500). The game reads its plays from a list with a fixed size, so another version of the game (the Xbox 360 one, an update) may not take the added plays the way the
    PS3 game does: the editor asks before it writes."""
    skip_p = {int(a["plyl"]) for a in added if isinstance(a, dict)}
    skip_s = {int(a["new_set"]) for a in added if isinstance(a, dict) and a.get("new_set")}
    plays = [int(k) for k in lib.plays if int(k) < P.CUSTOM_OFFSETS["PLYL"] and int(k) not in skip_p]
    sets = [int(k) for k in lib.sets if int(k) < P.CUSTOM_OFFSETS["SETL"] and int(k) not in skip_s]
    got = {"plays": len(plays), "sets": len(sets), "max_play": max(plays) if plays else 0, "max_set": max(sets) if sets else 0}
    names = {"plays": "plays", "sets": "formations (sets)", "max_play": "highest play id", "max_set": "highest formation id"}
    return [f"{names[k]}: {got[k]:,} here, {TESTED_GAME[k]:,} in the game the editor was tried on" for k in TESTED_GAME if got[k] != TESTED_GAME[k]]


def free_play_id(lib, taken=()):
    """The play id for a new play: the next id above the game's highest stock play (7459) and every id in use (7460 first). It must be ABOVE the stock maximum: found in the game (RPCS3,
    2026-10-29) that the game builds an in-memory list of plays from the compact copy (qkl_boot.ast entry 42) and reads only its FIRST 3,099 rows, the stock count. A play with an id below
    the stock maximum sorts in front of the last stock plays and pushes them out of that list; the game then asks for one of them (a side's current play, Man Blitz 7459) on the day before the
    first game, finds nothing and crashes (two added plays in one formation crashed, two in different formations did not, only because of which play was pushed out). With ids above 7459 the first
    3,099 rows are exactly the stock plays. The added plays are then not in that list, so the computer cannot call them (build writes no CPU rows)."""
    taken = [int(t) for t in taken]                      # the ids of the plays added so far (they are not the stock game's)
    top = max([stock_max_play(lib, taken)] + taken)
    if top + 1 > MAX_PLYL:
        raise ValueError("The game has no free play id left.")
    return top + 1


def check_play_id(plyl, stock_max=None):
    """Raises ValueError for a play id that is not above the stock maximum (see free_play_id); stock_max: this archive's own (stock_max_play), the PS3 game's by default."""
    limit = STOCK_MAX_PLYL if stock_max is None else int(stock_max)
    if int(plyl) <= limit:
        raise ValueError(f"A play added to the game files needs an id above {limit}, the game's highest play: a lower id pushes a stock play out of the game's play list and the game crashes "
                         "on the day before the first game.")


def check_ids(plays, stock_max=None):
    """Raises ValueError when an added play has an id that is not above the stock maximum: a play added by an older version of the editor (ids 7455 to 7458) crashes the game. A play knows the
    stock maximum it was built against ("stock_max"); one that does not (an older version's) is checked against stock_max, or the PS3 game's."""
    default = STOCK_MAX_PLYL if stock_max is None else int(stock_max)
    low = sorted(int(p["plyl"]) for p in plays if int(p["plyl"]) <= int(p.get("stock_max", default)))
    if low:
        raise ValueError(f"The plays {', '.join(str(i) for i in low)} were added by an older version of the editor with ids that crash the game on the day before the first game. Press Put the game files back "
                         "and add the plays again (they get ids above 7459).")


MAX_SETL = 511                  # the set id field is 9 bits wide
STOCK_MAX_SETL = 500            # the game's highest set


def _block_above(used, count):
    """`count` consecutive ids, ascending, above every id in `used`."""
    start = (max(used) if used else 0) + 1
    return list(range(start, start + count))


def free_set_ids(lib, slots=11, groups=1, packages=0, taken=None, added=()):
    """The ids of a new set in the game's own tables: {"SETL": n, "SETP": [one per slot], "SGF_": [one per alignment group], "SPF_": [one per quick-sub package]}. The set id is the next one above
    every id in use (501 first: the way tried most in the game), the set id field is 9 bits wide, so 501 to 511 are 11 sets; when those are all in use the lowest id the game leaves FREE below its
    highest set (500) is taken: the game's own numbering has about 260 gaps (sets that were removed), and a formation at one of them works (RPCS3, 2026-10-31: a formation at id 84 reached game day,
    the moved receiver stood at the sideline and the play ran; the earlier 'new rows must come after every stock row' came from tests that also had the play-id bug of free_play_id). An id a save holds
    (the profile's custom formations use gaps too) is never taken. The slot, group and package ids are consecutive ascending blocks above all ids in use, in the order of the rows, as the game's own
    sets number them (the id of a slot is the first one plus its number: 239 of 240 sets). `taken` = {"SETL": ids, "SETP": ..., "SGF_": ..., "SPF_": ...} that must not be used either (earlier added
    sets, ids a save holds); added: the added plays (their sets are not the stock game's: the highest stock set of this archive decides where the ids above it start)."""
    taken = taken or {}
    quick = getattr(lib, "quick_subs", None) or {}
    off = P.CUSTOM_OFFSETS
    used = {"SETL": {int(k) for k in lib.sets if int(k) < off["SETL"]}, "SETP": {int(r["SETP"]) for r in lib.tables["SETP"] if int(r["SETP"]) < off["SETP"]},
            "SGF_": {int(r["SGF_"]) for r in lib.tables["SGFF"] if int(r["SGF_"]) < off["SGF_"]}, "SPF_": {int(r["SPF_"]) for r in quick.get("SPKF", [])}}
    for k in used:
        used[k] |= {int(x) for x in taken.get(k, ())}
    setl = _block_above(used["SETL"], 1)[0]                 # the next id above every one in use: the new rows come last (the order that was tried in the game)
    if setl > MAX_SETL:
        # a save's stale link may name a high id (511) while lower ones are free: use the lowest free id of the supported range before refusing
        top = stock_max_set(lib, added)
        free = [i for i in range(top + 1, MAX_SETL + 1) if i not in used["SETL"]]
        if not free:
            free = [i for i in range(1, top + 1) if i not in used["SETL"]]          # the ids above the stock maximum are in use: the gaps of the game's own numbering
        if not free:
            raise ValueError("The game has no free formation id left (the ids above its own sets and the gaps below them are all in use). Take a play with its own formation out first.")
        setl = free[0]
    return {"SETL": setl, "SETP": _block_above(used["SETP"], slots), "SGF_": _block_above(used["SGF_"], groups), "SPF_": _block_above(used["SPF_"], packages) if packages else []}


def books_of(lib, base):
    """The playbooks (BOKL) that hold the play."""
    return sorted(lib.books_of_play.get(base, ()))


def moved_players(lib, base, alignment):
    """The slots of an alignment that are not where the stock set has them."""
    stock = lib.alignment(lib.detail(base)["set"]["setl"])
    return sorted(poso for poso, (x, y) in (alignment or {}).items() if poso in stock and (abs(float(x) - stock[poso]["x"]) > 0.001 or abs(float(y) - stock[poso]["y"]) > 0.001))


def moved_places(lib, base, alignment):
    """Where the moved players stand, as the play keeps it to know which formation it is in: {"slot": [x, y]} for the slots that are not where the stock set has them."""
    return {str(poso): [round(float(alignment[poso][0]), 3), round(float(alignment[poso][1]), 3)] for poso in moved_players(lib, base, alignment)}


def find_shared(lib, base, alignment, added):
    """The added play whose formation already has the players where this play wants them (a copy of the same stock set with the same moved players in the same places), or None. A formation is a
    lineup, and many plays can use one (the stock set Big holds 87), so a second play with the same lineup goes into it instead of taking one of the 11 places for formations of our own."""
    places = moved_places(lib, base, alignment)
    if not places:
        return None
    stock_setl = int(lib.detail(base)["set"]["setl"])
    for p in added:
        have = p.get("moved")
        if not p.get("new_set") or p.get("stock_setl") != stock_setl or not have or set(have) != set(places):
            continue
        if all(abs(have[k][0] - places[k][0]) <= 0.0011 and abs(have[k][1] - places[k][1]) <= 0.0011 for k in places):
            return p
    return None


def convert_places(lib, custom_setl):
    """Where every player of a custom set stands, as a converted play keeps it to know which formation it is in: {"slot": [x, y]} for all eleven slots."""
    al = lib.alignment(custom_setl)
    return {str(p): [round(float(al[p]["x"]), 3), round(float(al[p]["y"]), 3)] for p in sorted(al)}


def find_shared_convert(lib, base, like, added):
    """The converted play (among `added`) whose formation is a copy of the same stock set `like` with the players in the same places as the custom play `base`'s set, or None: custom plays
    with the same lineup go into one formation (the game has room for about 230 formations of its own: 11 above its own ids, then the ids it leaves free below them; and a play of the user's often shares its lineup with others: 18 plays had 9 lineups)."""
    mine = convert_places(lib, lib.detail(base)["set"]["setl"])
    for p in added:
        have = p.get("moved")
        if not p.get("new_set") or p.get("like") != like or not have or set(have) != set(mine):
            continue
        if all(abs(have[k][0] - mine[k][0]) <= 0.0011 and abs(have[k][1] - mine[k][1]) <= 0.0011 for k in mine):
            return p
    return None


def check_name(name):
    return GF.clean_name(name)


def compact_row(setl, plyl, plyt, plpd=None, plrd=None):
    """A play's row in the compact copy of the database (qkl_boot.ast entry 42): the pass reads (PLPD) and the run hole (PLRD) sit in the play's own row, zeros where the play has none. Checked
    against all 3,099 stock plays: it reproduces every one."""
    row = {"SETL": setl, "PLYL": plyl, "PLYT": plyt, "hole": int(plrd["hole"]) if plrd else 0}
    for c in PASS_COLS:
        row[c] = int(plpd[c]) if plpd else 0
    return row


def _lineup(lib, setl):
    """What a set puts on the field: the sorted (EPos, DPos) of its slots (a custom set can only share a formation type with a stock set that has the same players)."""
    return tuple(sorted((s["epos"], s["dpos"]) for s in lib.sets[setl]["slots"]))


def stock_match(lib, custom_setl):
    """The game's own set that a custom set is closest to: the stock sets with the same players, the one whose places are nearest (sum of the yard differences). (stock set, distance) or None
    when no stock set has the same players. The custom set's formation type (FORM), situation type (SITT) and kind (SETT) are not the game's (a profile files its plays under the
    formation 8190 "Created Plays"), so a play converted to the game's database takes them from this set."""
    mine = lib.alignment(custom_setl)
    want = _lineup(lib, custom_setl)
    best = None
    for setl in sorted(lib.sets):
        if setl >= P.CUSTOM_OFFSETS["SETL"] or not lib.sets[setl].get("slots") or _lineup(lib, setl) != want:
            continue
        al = lib.alignment(setl)
        dist = sum(abs(mine[p]["x"] - al[p]["x"]) + abs(mine[p]["y"] - al[p]["y"]) for p in mine if p in al)
        if best is None or dist < best[1]:
            best = (setl, dist)
    return best


SPECIAL_GROUPS = {"special teams", "special", "kickoff", "safety punt", "kick return", "safety kick return", "run plays", "goal line", "hail mary"}
GROUP_ALIASES = {"gun": "shotgun", "i": "i form", "wishbone": "wishbone"}


class FormationGroups:
    """The formation groups of the playbooks (the menus the play-call screen sorts a playbook's formations under: Singleback, Gun, I Form, Wishbone...): which group of a playbook a new formation goes
    into. Built from the game's own PGSL (playbook, set, group), PBFM (the groups: id, name, kind FTYP) and PGFM (the groups each playbook has) rows. A group id is the playbook's own."""

    def __init__(self, pgsl_rows, pbfm_rows, pgfm_rows):
        self.name = {int(r["PBFM"]): str(r["name"]).strip() for r in pbfm_rows}
        self.kind = {int(r["PBFM"]): int(r["FTYP"]) for r in pbfm_rows}
        self.order = {int(r["PBFM"]): int(r["ord_"]) for r in pbfm_rows}
        self.book_groups = collections.defaultdict(list)
        for r in pgfm_rows:
            self.book_groups[int(r["BOKL"])].append(int(r["PBFM"]))
        self.of_set = {(int(r["BOKL"]), int(r["SETL"])): int(r["PBFM"]) for r in pgsl_rows}
        self.family = collections.defaultdict(collections.Counter)             # set -> the group names the playbooks give it, most used first
        self.sets_in = collections.Counter()
        for r in pgsl_rows:
            if int(r["PBFM"]) in self.name:
                self.family[int(r["SETL"])][self._norm(self.name[int(r["PBFM"])])] += 1
            self.sets_in[int(r["PBFM"])] += 1

    @staticmethod
    def _norm(name):
        n = name.lower()
        return GROUP_ALIASES.get(n, n)

    def pick(self, book, like):
        """The group of `book` for a new formation that is like the stock set `like`: the group the book already gives that set; else the book's group with the same name as the one most playbooks
        give it (Gun is Shotgun, I is I Form); else the playbook's offense group with the most formations that is not a special group. None for a playbook that has no offense group."""
        book, like = int(book), int(like)
        if (book, like) in self.of_set:
            return self.of_set[(book, like)]
        groups = [g for g in self.book_groups.get(book, ()) if self.kind.get(g) == 1]
        for fam, _n in self.family[like].most_common():
            if fam in SPECIAL_GROUPS:
                continue                       # Hail Mary / Goal Line / Special Teams are used by every kind of formation; they are not what the formation is
            for g in groups:
                if self._norm(self.name[g]) == fam:
                    return g
        plain = [g for g in groups if self.name[g].lower() not in SPECIAL_GROUPS] or groups
        return max(plain, key=lambda g: (self.sets_in[g], -self.order.get(g, 0)), default=None)


def set_ids_needed(lib, base, like=None):
    """How many ids a copy of the base play's set needs: (slots, alignment groups, quick-sub packages). like: the stock set a converted custom play copies instead (see convert_changes)."""
    setl = int(like) if like is not None else lib.detail(base)["set"]["setl"]
    quick = getattr(lib, "quick_subs", None) or {}
    return (len([r for r in lib.tables["SETP"] if int(r["SETL"]) == setl]), len([g for g in lib.tables["SGFF"] if int(g["SETL"]) == setl]),
            len([r for r in quick.get("SPKF", []) if int(r["SETL"]) == setl]))


def convert_changes(lib, custom_setl, like):
    """A custom set converted into a copy of the stock look-alike set `like`: ({slot: {artx, arty}}, {slot: {x___, y___, fx__, fy__}}, the id of the stock set's normal alignment group): only the
    custom set's PLACES go onto the stock set's rows. The custom set's other slot columns are placeholders (SGT_ 0, arti 4, opnm 0, odep 0, flas 0 in every slot), the stock set's are the game's;
    a play converted with the placeholders lined up wrong or ran another play in the game (RPCS3, 2026-10-29)."""
    c_setp = {int(r["poso"]): r for r in lib.tables["SETP"] if int(r["SETL"]) == int(custom_setl)}
    c_ids = {int(r["SETP"]): p for p, r in c_setp.items()}
    c_dflt = next(int(g["SGF_"]) for g in lib.tables["SGFF"] if int(g["SETL"]) == int(custom_setl) and g["dflt"] == "1")
    c_setg = {c_ids[int(r["SETP"])]: r for r in lib.tables["SETG"] if int(r["SETP"]) in c_ids and int(r["SGF_"]) == c_dflt}
    l_setp = {int(r["poso"]): r for r in lib.tables["SETP"] if int(r["SETL"]) == int(like)}
    l_ids = {int(r["SETP"]): p for p, r in l_setp.items()}
    l_dflt = next(int(g["SGF_"]) for g in lib.tables["SGFF"] if int(g["SETL"]) == int(like) and g["dflt"] == "1")
    l_setg = {l_ids[int(r["SETP"])]: r for r in lib.tables["SETG"] if int(r["SETP"]) in l_ids and int(r["SGF_"]) == l_dflt}
    setp_diff, setg_diff = {}, {}
    for poso, row in l_setp.items():
        c = c_setp.get(poso)
        if c is not None:
            diff = {k: int(c[k]) for k in ("artx", "arty") if int(c[k]) != int(row[k])}
            if diff:
                setp_diff[poso] = diff
    # The places a flipped play stands at (SETG fx__, fy__) are NOT the custom set's: its rows hold 0.0 / 0.0 in every slot (a created play cannot be flipped), and a converted play that was
    # flipped in the game froze it (RPCS3, 2026-10-29: every player sent to the same spot). The rule of the game's own formations (true for 2,552 of their 2,640 slots, the rest are special teams
    # sets): a slot stands, flipped, where its flip partner stands mirrored (fx = -x of the partner, fy = y of the partner); a slot without a partner stays where it is.
    final = {}
    for poso, gl in l_setg.items():
        src = c_setg.get(poso) or gl
        final[poso] = (int(src["x___"]) & 0xFFFFFFFF, int(src["y___"]) & 0xFFFFFFFF)
    partner = {p: v.get("partner") for p, v in lib.alignment(int(like)).items()}
    mirror = lambda bits: bits if (bits & 0x7FFFFFFF) == 0 else bits ^ 0x80000000          # the sign bit of the float (a zero stays +0.0 as in the game's rows)
    for poso, gl in l_setg.items():
        q = partner.get(poso)
        x, y = final[poso]
        fx, fy = (x, y) if q is None or q not in final else (mirror(final[q][0]), final[q][1])
        diff = {k: v for k, v in (("x___", x), ("y___", y), ("fx__", fx), ("fy__", fy)) if v != int(gl[k]) & 0xFFFFFFFF}
        if diff:
            setg_diff[poso] = diff
    return setp_diff, setg_diff, l_dflt


def stock_plf(lib, plyt, like):
    """The play family (PBPL.PLF_) of a converted play: the commonest one among the stock plays of the same kind (PLYT), preferring those of the stock set `like`, then those of its formation
    (FORM), then all of them. A custom play keeps the family of the play it was made from, so a pass kind carried a run's family (PLYT 4 with 288, PLYT 13 with 33): pairs that no stock play has."""
    stock = [p for k, p in lib.plays.items() if int(k) < P.CUSTOM_OFFSETS["PLYL"] and p["plyt"] == plyt]
    form = lib.sets[int(like)]["form"]
    for pick in (lambda p: p["setl"] == int(like), lambda p: lib.sets.get(p["setl"], {}).get("form") == form, lambda p: True):
        counts = collections.Counter(p["plf"] for p in stock if pick(p))
        if counts:
            return max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    raise ValueError("No stock play has that kind.")


def new_set_rows(lib, base, new, alignment, ids, set_name, like=None):
    """The rows of a copy of the base play's set with the moved players' places changed: ({"40": {SETL, SETP, SETG, SGFF, SPKF, SPKG}, "42": {}}, the new set's id). The copy is the stock set's
    own rows with only these values changed: the diagram places (SETP artx, arty) and the yards of the normal alignment group (SETG x___, y___, fx__, fy__, the flipped partner's too) of the players
    that moved. Nothing goes into the compact copy (entry 42): its slot table cannot take another set (found in the game: even one extra set of slot rows there crashes it)."""
    d = lib.detail(base)
    st = d["set"]
    setl = int(st["setl"])
    set_name = GF.clean_name(set_name)
    if like is not None:                                      # a custom play: a copy of the stock look-alike set with the custom set's places
        setp_diff, setg_diff, dflt = convert_changes(lib, setl, like)
        setl = int(like)
    else:
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


def build(lib, base, name, books, plyl, overrides=None, plan=None, reads=None, alignment=None, set_name=None, set_ids=None, book_pbfm=None, new_set=False, share=None, like=None, stock_max=None, cpu=False):
    """What the bridge needs for a new play id `plyl`, made from the stock play `base` as the Play creator shows it (overrides, plan, reads, alignment as in hc09_gamefiles.changes_for), put into
    the playbooks `books`: {"plyl", "name", "base", "setl", "new_set", "plyt", "books", "rows": {"40": {table: [row]}, "42": ..., "46": ..., "47": ...}}. When players are moved (or new_set is
    asked for) the play gets a set of its own: set_name (its name), set_ids (free_set_ids) and book_pbfm ({playbook: the formation id the playbook gives the stock set}, the PBFM of its PGSL row)
    are needed. share: an added play (find_shared) whose formation has the same players in the same places; the play goes into that formation instead of a new one (no ids or name needed: the play
    carries a copy of the formation's rows, which merge() writes once, so the formation stays while any play of it is in the game files). A custom play of the user's profile (lib.mount_custom) can be the base too (\"convert\"): it always gets a set of its own, made like the stock set `like` (default: stock_match), and goes into any playbooks that
    have a formation for it (book_pbfm). stock_max: the highest play id of the stock game in this archive (stock_max_play, the plays added before left out; the library's own when not given): the play's
    id must be above it, and the play remembers it for merge(). cpu: also give the play CPU rows (PBAI, the table the computer picks its plays from: a copy of the rows of the play it was made from in the
    chosen playbooks, so the computer may call it like the original). EXPERIMENTAL, not tried in the game: no CPU rows were written since the registry crash was found (see free_play_id), because a play the computer picks that
    is not in the game's play list could crash it. Only for a stock play (a play of the Play creator has no CPU rows to copy). Raises ValueError for what cannot be added."""
    name = GF.clean_name(name)
    d = lib.detail(base)
    if d["side"] != "offense":
        raise ValueError("Only offensive plays can be added for now.")
    if plyl in lib.plays:
        raise ValueError(f"The game already has a play {plyl}.")
    convert = lib.is_custom(base)
    stock_max = stock_max_play(lib) if stock_max is None else int(stock_max)
    check_play_id(plyl, stock_max)
    own_set = bool(moved_players(lib, base, alignment)) or new_set or convert
    have = set(books_of(lib, base))
    books = sorted({int(b) for b in books})
    if not books:
        raise ValueError("Choose at least one playbook.")
    if not convert and any(b not in have for b in books):
        raise ValueError("The play can only go into playbooks that already have the play it was made from (they hold its formation).")
    st = d["set"]
    if convert and like is None:
        match = stock_match(lib, st["setl"])
        if match is None:
            raise ValueError("No set of the game has the same players as this play's formation, so it has no formation type to take.")
        like = match[0]
    _d, new = GF._new_rows(lib, base, overrides or {}, plan, reads, alignment)
    nb = new["PBPL"][0]
    plyt = int(nb["PLYT"])
    stock_setl = int(st["setl"])
    setl = stock_setl
    extra40, extra42, extra47 = {}, {}, {}
    if own_set:
        if share is None and (not set_name or not set_ids or book_pbfm is None):
            raise ValueError("A play whose players are somewhere else than in the stock formation needs a formation of its own: a name for it and free ids are needed.")
        if book_pbfm is None or any(b not in book_pbfm for b in books):
            raise ValueError("The formation of the play was not found in every playbook chosen.")
        if share is not None:
            if (find_shared_convert(lib, base, like, [share]) if convert else find_shared(lib, base, alignment, [share])) is None:
                raise ValueError("That formation has the players somewhere else than this play.")
            setl = int(share["new_set"])
            extra40 = {t: copy.deepcopy(share["rows"]["40"][t]) for t in SET_TABLES if t in share["rows"]["40"]}
        else:
            sets, setl = new_set_rows(lib, base, new, alignment, set_ids, set_name, like=like if convert else None)
            extra40, extra42 = sets["40"], sets["42"]
        extra47 = {"PGSL": [{"BOKL": b, "SETL": setl, "PBFM": book_pbfm[b]} for b in books]}
        if extra40.get("SPKF"):
            extra47["PGSS"] = [{"BOKL": b, "SETL": setl} for b in books]            # a set with no quick-sub packages has no PGSS row (32 of the game's 240 sets are like that)
    base_play = lib.plays[base]
    sitt = int(next(r["SITT"] for r in lib.tables["SETL"] if int(r["SETL"]) == int(like))) if convert else int(base_play["sitt"])
    pbpl = {"SETL": setl, "PLYL": plyl, "SITT": sitt, "PLYT": plyt, "PLF_": stock_plf(lib, plyt, like) if convert else int(nb["PLF_"]), "name": name, "risk": int(nb["risk"]), "motn": int(nb["motn"]), "vpos": int(nb["vpos"])}
    plys = [{"PSAL": int(r["PSAL"]), "ARTL": int(r["ARTL"]), "PLYL": plyl, "PLRR": int(r["PLRR"]), "poso": int(r["poso"])} for r in new["PLYS"]]
    r40 = {"PBPL": [pbpl], "PLYS": plys}
    for table in ("PLPD", "PLRD", "PLCM"):
        if new.get(table):
            r40[table] = [{**{k: v for k, v in row.items() if k != "PLYL"}, "PLYL": plyl} for row in new[table]]
    # No CPU rows (PBAI) unless asked for (cpu): the game's play list (the first 3,099 rows of the compact copy) cannot hold an added play, and a CPU pick of a play that is not in it might crash the game.
    # The computer picks only from the plays of its playbook (in the game's data every (playbook, play) pair of PBAI is also a link of PGPL), so these rows are what it takes to let it call the play.
    if cpu:
        if convert:
            raise ValueError("The computer cannot be given a play made in the Play creator: it has no CPU rows to copy.")
        pbai = [{"BOKL": int(r["BOKL"]), "PBPL": plyl, "SETL": setl, "AIGR": int(r["AIGR"]), "PLYT": plyt, "PLF_": pbpl["PLF_"], "vpos": pbpl["vpos"], "prct": int(r["prct"])}
                for r in lib.tables["PBAI"] if int(r["PBPL"]) == base and int(r["BOKL"]) in books]
        if not pbai:
            raise ValueError("The play has no CPU rows (PBAI) in those playbooks, so the computer cannot be given it there.")
        r40["PBAI"] = pbai
    row42 = compact_row(setl, plyl, plyt, (r40.get("PLPD") or [None])[0], (r40.get("PLRD") or [None])[0])
    r42 = {"PBPL": [row42], "PLYS": [{"PLYL": plyl, "PLRR": r["PLRR"], "poso": r["poso"]} for r in plys]}
    r47 = {"PGPL": [{"BOKL": b, "SETL": setl, "PLYL": plyl, "PLTP": plyt} for b in books]}
    r40.update(extra40)
    r42.update(extra42)
    r47.update(extra47)
    rows = {"40": r40, "42": r42, "46": {"PPPN": [{"BOKL": b, "PLYL": plyl, "PPPM": name} for b in books]}, "47": r47}
    rows = {e: {t: [_num(r) for r in rs] for t, rs in tables.items()} for e, tables in rows.items()}
    warnings = (["The computer may call this play (experimental: CPU rows were added and this has not been tried in the game yet): if the game crashes on the day before a game, take the play out and add it again without them."] if cpu else
                ["The computer will not call this play (it has no CPU rows); you can call it yourself."])
    return {"plyl": plyl, "name": name, "base": base, "setl": setl, "new_set": setl if own_set else None, "stock_setl": stock_setl, "stock_max": stock_max, "moved": convert_places(lib, lib.detail(base)["set"]["setl"]) if convert else (moved_places(lib, base, alignment) if own_set else {}),
            "plyt": plyt, "books": books, "rows": rows, "like": like if convert else None, "warnings": warnings, "cpu": bool(cpu)}


def convert_mine(lib, bases, books, groups, taken_plays=(), added=(), taken=None):
    """Convert the user's custom plays (lib.mount_custom) into plays of the game's own database: each gets a new play id and a formation (a copy of the stock set it is closest to, with the
    custom set's places), in the playbooks `books`, each formation in the playbook's formation group that suits it (FormationGroups.pick). Plays with the same lineup share one formation (the game has
    room for about 230). added: the plays added to the game files before (their ids and formations stay, and a new play can go into one of their formations); taken: set, slot, group and package ids that
    saves still name (the window's _taken_set_ids). Returns (plays, skipped): the built plays, and [(base, why)] for the ones that cannot be converted."""
    plays, skipped = [], []
    taken_plays = list(taken_plays) + [p["plyl"] for p in added]
    extra = {k: list(v) for k, v in (taken or {}).items()}
    stock_max = stock_max_play(lib, added)
    for base in bases:
        name = lib.plays[base]["name"]
        try:
            d = lib.detail(base)
            if d["side"] != "offense":
                raise ValueError("Only offensive plays can be converted for now.")
            before = next((p for p in added if p.get("from_custom") == lib.custom[base]["plyl"]), None)
            if before is not None:
                raise ValueError(f"It is already converted (play {before['plyl']}): take that copy out first, then convert the edited play again, or the game files would hold both versions.")
            match = stock_match(lib, d["set"]["setl"])
            if match is None:
                raise ValueError("No set of the game has the same players as the play's formation.")
            like = match[0]
            ok = [b for b in books if groups.pick(b, like) is not None]
            if not ok:
                raise ValueError("None of the playbooks has an offense formation group to put it in.")
            missing = [r for r in lib.slot_rows[base].values() if r["psal"] not in {int(x["PSAL"]) for x in lib.tables["PSLO"]} or r["artl"] not in {int(x["ARTL"]) for x in lib.tables["ARTO"]}]
            if missing:
                raise ValueError("It uses a route or diagram art the game's own database does not have.")
            shared = find_shared_convert(lib, base, like, list(added) + plays)
            ids = None
            if shared is None:
                used = taken_ids(list(added) + plays, custom_ids(lib))
                for k, v in extra.items():
                    used[k] = list(used.get(k, [])) + v
                ids = free_set_ids(lib, *set_ids_needed(lib, base, like=like), taken=used, added=list(added) + plays)
            plyl = free_play_id(lib, taken_plays + [p["plyl"] for p in plays])
            play = build(lib, base, name, ok, plyl, set_name=name, set_ids=ids, book_pbfm={b: groups.pick(b, like) for b in ok}, like=like, share=shared, stock_max=stock_max)
            play["from_custom"] = lib.custom[base]["plyl"]
            plays.append(play)
        except ValueError as e:
            skipped.append((base, str(e)))
    return plays, skipped


def merge(plays):
    """The spec for the bridge: the rows of all the plays that are to be in the game files (a play with the same id as an earlier one replaces it)."""
    by_id = {}
    for p in plays:
        by_id[p["plyl"]] = p
    plays = [by_id[k] for k in sorted(by_id)]
    check_ids(plays)                                        # every play against the stock maximum it was built with
    rows = {}
    for p in plays:
        for entry, tables in p["rows"].items():
            for table, rs in tables.items():
                have = rows.setdefault(entry, {}).setdefault(table, [])
                for r in rs:
                    if table in SHARED_ROWS.get(entry, ()) and r in have:
                        continue                            # plays in one added formation each carry its rows; the game files get them once
                    have.append(copy.deepcopy(r))
    return {"rows": rows, "plays": plays}


def custom_ids(lib):
    """The ids the user's custom plays use in the profile (before the mount moved them up): they must not become ids of the game's own database, because the game reads ITS OWN set of the
    same number instead of the custom one (found in the game: a custom set 74 was played as the punt return team)."""
    off = P.CUSTOM_OFFSETS
    rows = getattr(lib, "_custom_rows", {}) or {}
    return {"SETL": [int(r["SETL"]) - off["SETL"] for r in rows.get("SETL", [])], "SETP": [int(r["SETP"]) - off["SETP"] for r in rows.get("SETP", [])],
            "SGF_": [int(r["SGF_"]) - off["SGF_"] for r in rows.get("SGFF", [])], "SPF_": []}


def taken_ids(plays, extra=None):
    """The set ids the added plays already use: {"SETL": ..., "SETP": ..., "SGF_": ..., "SPF_": ...} (for free_set_ids)."""
    out = {k: list(v) for k, v in (extra or {"SETL": [], "SETP": [], "SGF_": [], "SPF_": []}).items()}
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


def unused_set_pairs(removed, kept):
    """The (playbook, set) pairs of the formations of the removed plays that no kept play uses any more: a formation shared by several plays keeps its PGSL / PGSS links in a playbook while a play of
    it is still in that playbook."""
    pairs = lambda plays: {(int(r["BOKL"]), int(r["SETL"])) for p in plays for r in p["rows"]["47"].get("PGSL", [])}
    return pairs(removed) - pairs(kept)


def remove_set_pairs(rows, pairs):
    """The save's PGSL or PGSS rows without these (playbook, set) pairs. Returns (rows, number removed)."""
    out = [dict(r) for r in rows if (int(r["BOKL"]), int(r["SETL"])) not in pairs]
    return out, len(rows) - len(out)
