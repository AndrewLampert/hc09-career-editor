"""
Route tests: a short series of game tests that show whether the game reads edits to a route's step numbers and what those numbers mean (how far a leg runs, which way it
heads, which way a cut turns). The answers decide whether a "route lab" that writes new routes is possible (see docs/hc09_play_creator.md and docs/hc09_test_guide.md).

Standard library only (no Tk). The editor's Route test window uses this: it changes a few numbers of ONE route in qkl_boot.ast (the route "Post" that "WR Post", "FL Post",
"Cross Up" and others use), one change at a time, makes the usual backup first, and can put the route back. Every change is checked against what the file holds now.
"""
import collections

TABLE = "PSLO"                    # the step table of the MASTER copy of the play database (qkl_boot.ast entry 40)
GAME_TABLE = "PSAL"               # the same step lists in the IN-GAME copies (qkl_fe2ig.ast entries 1673-1679): the game's play set-up code reads a table of this name
# where a test writes its change: both copies, or only one of them (to find out which one the game reads)
WHERE = (("both", "Both copies (recommended)"), ("game", "In-game copy only"), ("master", "Master copy only"))
WHERE_LABEL = dict(WHERE)
PSAL = 1202                       # the Post route: stem, break, run (used by 58 slots in 42 playbooks)
# the route's rows in the stock game: (step, code, val1, val2, val3). 8 is a leg, 9 a cut, 10 the end, 255 the end of the list.
STOCK = ((0, 8, 68, 32, 254), (1, 9, 2, 1, 0), (2, 8, 200, 42, 254), (3, 10, 0, 0, 0), (4, 255, 0, 0, 0))
ROW_NAMES = {0: "the first leg (the stem)", 1: "the cut (the break)", 2: "the second leg"}
COLUMN_NAMES = {"val1": "first number", "val2": "second number", "val3": "third number"}

# A test: id, title, the changes {step: {column: new value}}, what it asks, what to watch for. What the numbers are comes from the game's own code and route data. A leg's first number
# is its length in yards, (n >> 3) + (n & 7) / 7 (68 = 8.6, 136 = 17, 200 = 25, 60 = 7.6), its second number a heading in degrees, n x 2.8125 (0 = to the right, 32 = 90 = straight upfield,
# 42 = 118, 16 = 45, 64 = 180 = to the left, 96 = 270 = back toward the quarterback), its third a movement intensity, n / 255 (254 = full, 127 = half; capped at full). A cut's first number is the
# side its animation turns to (1 right, 2 left) and its second picks the turn angle of that ANIMATION (1 and 23 = 45 degrees, 2 and 14 = 90, 3 = 22, 4 = 67, 22 = 135, 5 and most other numbers = a
# full turn back, about 180); the cut does not move the receiver along the route: the leg after it does, by its own heading. A tester's first results (master copy, quick game) confirmed the
# lengths and headings and showed that a cut that does not match the next leg gives a glitchy "two cuts in a row" route; tests B11 to B14 were added for what was left open.
TESTS = (
    {"id": "B0", "phase": 1, "title": "Stock route (control)", "changes": {},
     "asks": "How does the route run before any change? This is what the others are compared with. By the numbers it is a first leg of about 9 yards, a cut to the left of about 45 degrees, then a long second leg (25 yards) heading up and toward the middle. The picture of the play on the play-call screen will show the stock Mid Post in EVERY test (it is drawn from separate data): judge by watching the play run, not by the picture.",
     "watch": "How many yards past the line of scrimmage does the receiver run before he breaks (about 9 by the numbers)? Which way does he break? Which route is it (the stock one is a Post)?"},
    {"id": "B1", "phase": 1, "title": "Longer stem: first leg, first number 68 -> 136", "changes": {0: {"val1": 136}},
     "asks": "Does the game use the edited file at all, and is the leg's first number its length in yards (68 = about 8.6 yards, 136 = 17)? A tester has seen it: the break moved to 17 yards. Repeat it if you can, it is quick.",
     "watch": "Does the receiver now run about twice as far before he breaks (about 17 yards instead of 9)? If nothing is different, tell us right away: that decides everything."},
    {"id": "B2", "phase": 1, "title": "Heading of the second leg: second number 42 -> 16", "changes": {2: {"val2": 16}},
     "asks": "The second leg's heading goes from 118 degrees (up and toward the middle) to 45 degrees (up and toward the sideline), but the cut still plants for a 45-degree cut to the left. A tester saw a GLITCHY route: the normal post plant, then a fast turn to the outside like a Corner. Does yours do the same?",
     "watch": "Where does the receiver end up heading? Does he plant one way and then run the other (a glitch is a good result: say what the two halves look like)?"},
    {"id": "B3", "phase": 1, "title": "Heading of the second leg: second number 42 -> 64", "changes": {2: {"val2": 64}},
     "asks": "The heading becomes 180 degrees: straight across to the middle. A tester saw an In/Dig (flat across), a little less sharp than the game's own In. Does it match?",
     "watch": "Does the receiver run flat across the field toward the middle after the break instead of up and in? Which route does it look like?"},
    {"id": "B4", "phase": 1, "title": "Side of the cut: first number 2 -> 1", "changes": {1: {"val1": 1}},
     "asks": "The cut's animation turns to the other side (right instead of left) but the next leg still heads up toward the middle. A tester saw a glitchy 'Corner Post': a break to the outside, then an awkward post cut. Does yours?",
     "watch": "Which way does he plant, and where does he run after it? Describe both halves."},
    {"id": "B5", "phase": 1, "title": "Sharpness of the cut: second number 1 -> 5", "changes": {1: {"val2": 5}},
     "asks": "The code 5 is a full reversal in the game's code (about 180 degrees), so the cut should look like a stop and turn back. A tester saw a 'Curl Post': he runs, stops, then makes the post break. Does yours?",
     "watch": "Does he stop and turn back toward the quarterback before the post break? How big does the turn look?"},
    {"id": "B6", "phase": 2, "title": "Shorter second leg: first number 200 -> 60", "changes": {2: {"val1": 60}},
     "asks": "Is the second leg's first number also a length in yards (200 = 25 yards, 60 = about 7.6)? A tester could not tell: the QB threw before the receiver got far past his break. DO NOT THROW: hold the ball (a team with a strong line, like the Cowboys, gives you the time) and watch the receiver run the whole route; use the replay.",
     "watch": "Where does the receiver stop after the break: about 7-8 yards past it instead of about 25?"},
    {"id": "B7", "phase": 2, "title": "Heading of the first leg: second number 32 -> 16", "changes": {0: {"val2": 16}},
     "asks": "Does the heading work the same way on the stem (32 = straight upfield, 16 = 45 degrees)? A tester has seen it: an angle-type diagonal start, about 5 yards upfield at the break.",
     "watch": "Does the receiver start off at about 45 degrees instead of straight upfield? Which way?"},
    {"id": "B8", "phase": 2, "title": "Third number of the second leg: 254 -> 127", "changes": {2: {"val3": 127}},
     "asks": "Is the third number how hard the receiver runs the leg (254 = full, 127 = half)? A tester saw no change, but the QB threw before the second leg was run. DO NOT THROW: hold the ball and watch the receiver run the whole route; use the replay.",
     "watch": "Does he run the second leg at about half effort (slower, covering less ground in the same time)? Nothing is also a fine answer."},
    {"id": "B9", "phase": 2, "title": "Sharpness of the cut: second number 1 -> 2", "changes": {1: {"val2": 2}},
     "asks": "The cut animation becomes a 90-degree turn while the next leg is unchanged. A tester saw a glitchy route: a 90-degree cut to the inside, then a quick post cut. Does yours?",
     "watch": "Is the plant sharper than in the stock route, and does he then run the stock second leg? Describe both halves."},
    {"id": "B10", "phase": 1, "title": "Stock again (control after putting the route back)", "changes": {},
     "asks": "Did putting the route back work? The route should run exactly as in B0.",
     "watch": "Does the route run the same as in B0?"},
    {"id": "B11", "phase": 2, "title": "Speed of the first leg: first leg third number 254 -> 127", "changes": {0: {"val3": 127}},
     "asks": "The stem is where the speed number can be seen best (B8 changes the second leg, which is hardly run before the throw). At half effort the receiver should reach the break later. DO NOT THROW until he has broken; use the replay to compare with B0.",
     "watch": "Does he take clearly longer to reach the break than in B0 (he should cover the same 9 yards more slowly)? About how much longer?"},
    {"id": "B12", "phase": 2, "title": "A clean Corner: cut side 2 -> 1 and second leg heading 42 -> 16", "changes": {1: {"val1": 1}, 2: {"val2": 16}},
     "asks": "B2 and B4 each gave a glitch because the cut and the next leg disagreed. Here both change together: the cut turns right by 45 degrees and the second leg heads 45 degrees toward the sideline. If the cut and the leg only have to agree, this should be a clean Corner route with no double cut.",
     "watch": "Is it a clean Corner (one break to the outside, no second cut)? Or still glitchy? Say which."},
    {"id": "B13", "phase": 2, "title": "A clean In: cut second number 1 -> 2 and second leg heading 42 -> 64", "changes": {1: {"val2": 2}, 2: {"val2": 64}},
     "asks": "The cut turns left by 90 degrees and the second leg heads 180 degrees (straight across to the middle). Cut and leg agree, so this should be a clean In/Dig with one sharp break.",
     "watch": "Is it a clean In (up, one sharp break, flat across)? Or glitchy?"},
    {"id": "B14", "phase": 2, "title": "A clean Curl: cut second number 1 -> 5, second leg heading 42 -> 96 and length 200 -> 24", "changes": {1: {"val2": 5}, 2: {"val1": 24, "val2": 96}},
     "asks": "The cut is a full reversal (about 180 degrees) and the second leg heads 270 degrees (back toward the quarterback) for 3 yards (24 = 3.0 yards). Cut and leg agree, so this should be a clean Curl/Hitch: up about 9 yards, stop, turn and come back about 3 yards.",
     "watch": "Is it a clean Curl or Hitch (stops, turns, comes back a few yards)? Or glitchy? How far does he come back?"},
)
TEST_BY_ID = {t["id"]: t for t in TESTS}

# The routes a tester can name, with what each looks like. "Go" is the one with no break at all (straight upfield); a Hitch or Curl is also straight at first but then turns round and comes back toward the
# quarterback. Out and In turn sharply (about 90 degrees) to the sideline / the middle, Corner and Post turn at a shallower angle (about 45 degrees) to the sideline / the middle.
ROUTE_CHOICES = (
    "",
    "Go: straight upfield, no break at all",
    "Hitch or Curl: runs up, stops and turns back toward the quarterback",
    "Comeback: runs deep, then comes back toward the sideline",
    "Out: runs up, then turns sharply (about 90 degrees) toward the sideline",
    "In or Dig: runs up, then turns sharply (about 90 degrees) toward the middle",
    "Slant: a short stem, then a diagonal toward the middle",
    "Post: runs up, then angles toward the middle (the stock route)",
    "Corner: runs up, then angles toward the sideline",
    "Flat: goes straight to the sideline, close to the line",
    "He stopped or stood still",
    "A mix of two routes, or a glitchy turn (describe below)",
    "Something else (describe below)",
)
LEGACY_FIELDS = {"direction": "Which way did he break (earlier form)"}      # answers saved by an earlier version of the form still show up in the report

# Teams whose offense is best to watch a route with: a strong offensive line that holds the rush until the receiver has broken (a weak line gives sacks and hurried throws instead of a route to look at).
# The tester found the Cowboys much better than the Bears, whose line "can barely hold the rush before the receiver breaks". Nicknames as the Playbooks tab shows them, best first.
GOOD_TEAMS = ("Cowboys",)

RESULT_FIELDS = (
    ("changed", "Did the route change from the stock route?", ("", "no change at all", "yes, it changed (describe below)", "yes, but glitchy: it does two different things (describe below)", "the game crashed or froze", "I could not call the play")),
    ("stem", "Yards past the line before the break (a number, 0 if you cannot tell)", None),
    ("route", "Which route did the receiver run? (the closest name)", ROUTE_CHOICES),
    ("after", "Yards he ran after the break (a number)", None),
    ("notes", "What you saw, in your own words (angle, speed, anything odd)", None),
)


def receiver_text(label, x, y, rank=0, n=1):
    """Where the receiver on the route lines up, in words: "WR1, wide on the right, about 15 yards right of the middle and 2 yards behind the line (closest to the sideline)".
    x: yards across the field (plus is the right, 0 the middle), y: yards from the line of scrimmage (minus is behind it), rank: how many players of his kind stand further out on his side,
    n: how many stand on that side."""
    behind = abs(y)
    back = f"{behind:.0f} yard{'s' if round(behind) != 1 else ''} behind the line"
    if abs(x) < 2.5:
        return f"{label}, in the middle of the field, {back}"
    side = "right" if x > 0 else "left"
    place = {0: "closest to the sideline", 1: "second in from the sideline", 2: "third in from the sideline"}.get(rank, f"number {rank + 1} in from the sideline")
    return f"{label}, wide on the {side}, about {abs(x):.0f} yards {side} of the middle and {back}" + (f" ({place})" if n > 1 else "")


def book_label(book, called, play):
    """A playbook with the name it gives the play when that is not the master name: 'Bears Power Run (calls it "22 Z Post")'."""
    return f'{book} (calls it "{called}")' if called and called != play else book


def watch_line(play, plyl, set_name, formation, who, book_names, called=None):
    """"WR Post (PLYL 1159) - Normal, I Form - WR1, wide on the right, ... - 7 playbooks: Reid All Passing (calls it "22 Scat Z Post"), Zorn West Coast, and 5 more": a play that uses the route, with its id (PLYL),
    set and formation (several sets are called "Normal"), the receiver (receiver_text) and the playbooks that have it. who: [receiver_text]. play is the master name; called: the name each of those playbooks
    gives the play, in the same order (the game's play-call screen shows these, and none of them need be the master name)."""
    names = list(book_names)
    called = list(called) if called else [None] * len(names)
    shown = ", ".join(book_label(n, c, play) for n, c in list(zip(names, called))[:2]) + (f", and {len(names) - 2} more" if len(names) > 2 else "")
    return f"{play} (PLYL {plyl}) - {set_name}, {formation} - {' and '.join(who)} - {len(names)} playbook{'s' if len(names) != 1 else ''}" + (f": {shown}" if names else "")


def choose_play(entries, book_names, holders, my_team="", my_book=None, strong=GOOD_TEAMS):
    """The one play and team a tester should use. entries: [{"plyl", "name", "set", "form", "who", "books": [playbook ids], "read": the route runner's place in the quarterback's reads
    (0 when the play is not a pass or he is not a read), "option": an option play} with the plays in the most playbooks first; book_names: {playbook id: name}; holders: {playbook id: [teams
    that play it]}; my_team / my_book: the team chosen in the editor and the playbook it plays. An ordinary pass that throws to the route runner is the easiest to watch (a run play only uses him
    as a decoy, an option play is hard to follow): the tester's own team when its playbook has such a play, else the best such play and a team that plays one of its playbooks, then worse plays the
    same way, except that a team of `strong` (a good offensive line, see GOOD_TEAMS) that plays such a play comes first. An entry may carry "called": {playbook id: the name that playbook gives the play}.
    Returns {"entry", "team", "playbook", "called" (the name in the chosen playbook), "others": [(team, playbook)], "other_names": [the name in each of those playbooks]} or None."""
    if not entries:
        return None
    name_of = lambda b: book_names.get(b, f"playbook {b}")

    def name_in(e, b):
        return e.get("called", {}).get(b) or e["name"]

    def build(e, book, team):
        others, other_names = [], []
        for b in sorted(e["books"], key=name_of):
            for t in holders.get(b, ()):
                if t != team and all(t != o[0] for o in others) and len(others) < 3:
                    others.append((t, name_of(b)))
                    other_names.append(name_in(e, b))
        return {"entry": e, "team": team, "playbook": name_of(book) if book is not None else "", "called": name_in(e, book) if book is not None else e["name"], "others": others, "other_names": other_names}

    tiers = [[e for e in entries if e.get("read") and not e.get("option")], [e for e in entries if e.get("read")], entries]
    for team in strong:
        for e in tiers[0]:
            for b in sorted(e["books"], key=name_of):
                if team in holders.get(b, ()):
                    return build(e, b, team)
    if my_book is not None:
        for tier in tiers[:1]:
            for e in tier:
                if my_book in e["books"]:
                    return build(e, my_book, my_team)
    for tier in tiers:
        for e in tier:
            for b in sorted(e["books"], key=name_of):
                if holders.get(b):
                    return build(e, b, holders[b][0])
    e = next((tier[0] for tier in tiers if tier), entries[0])           # no team has one: the best play anyway, with the first base playbook that has it
    return build(e, sorted(e["books"], key=name_of)[0] if e["books"] else None, "")


def play_text(pick):
    """Step 2 of a test in words: which team to be, which play to call, which receiver to watch."""
    e = pick["entry"]
    if pick["team"]:
        start = f"Start a quick game (Play Now) as the {pick['team']} (their base playbook: {pick['playbook']}) and play offense."
    elif pick["playbook"]:
        start = f"Start a quick game (Play Now) with a team whose base playbook is {pick['playbook']} and play offense."
    else:
        start = "Start a quick game (Play Now) and play offense."
    called = pick.get("called") or e["name"]
    what = f'"{called}" (PLYL {e["plyl"]}; the master list calls it {e["name"]})' if called != e["name"] else f"{e['name']} (PLYL {e['plyl']})"
    text = f"{start} Call {what}: the {e['form']} formation, the {e['set']} set. Watch {' and '.join(e['who'])}. Use this same play for every test."
    if pick["others"]:
        names = pick.get("other_names") or [None] * len(pick["others"])
        text += " If you cannot use that team: " + "; ".join(f"the {t} ({book_label(b, n, e['name'])})" for (t, b), n in zip(pick["others"], names)) + " have it too."
    text += " Playbooks name the same play differently, so go by the PLYL and the formation, not by the name."
    if pick["team"] not in GOOD_TEAMS:
        text += f" Pick a team with a strong offensive line if you can ({', '.join('the ' + t for t in GOOD_TEAMS)} work well): with a weak line the pass rush arrives before the receiver breaks and there is no route to watch."
    return text


def choose_cap_play(entries, book_names):
    """The play to use in the game's Create-A-Play: one that is in it (entry["cap"] is the name it shows there) and in at least one of the game's own named playbooks (never a custom one,
    and not the unnamed catch-all playbook). The same kind of choice as choose_play: an ordinary pass that throws to the route runner, then other passes, then anything; within a kind the play
    where he stands closest to the sideline (the easiest to follow), then where he is read first, and plays with a clean name (no "(1)" tail) first. Returns {"entry", "playbooks": [names of the game's playbooks that have it]} or None when no play qualifies."""
    pool = [e for e in entries if e.get("cap") and any(b in book_names for b in e["books"])]
    if not pool:
        return None
    tiers = [[e for e in pool if e.get("read") and not e.get("option")], [e for e in pool if e.get("read")], pool]
    tier = next(t for t in tiers if t)
    e = min(tier, key=lambda e: (e.get("rank", 0), e.get("read") or 9, e["cap"].rstrip().endswith(")"), e["plyl"]))
    return {"entry": e, "playbooks": sorted(book_names[b] for b in e["books"] if b in book_names)}


def cap_text(pick):
    """Step 2 of a test in words, for Create-A-Play: the existing play to open (formation, set, the name Create-A-Play shows), where the receiver lines up. The menu wording is not confirmed."""
    e = pick["entry"]
    pbs = pick["playbooks"]
    also = f" It is also in the game playbooks {'; '.join(pbs[:3])}{' and more' if len(pbs) > 3 else ''}." if pbs else ""
    return (f"In Create-A-Play, open the existing play {e['cap'].strip()} (PLYL {e['plyl']}): the {e['form']} formation, the {e['set']} set. Run it from there and watch {' and '.join(e['who'])}. "
            f"Use this same play for every test.{also} (The menu may be worded differently in your game: if you cannot run a play from Create-A-Play, tell us how you tested.)")


def full_list(entries, book_names):
    """Every play that uses the route, for the chat: PLYL, master name, set, formation, receiver, all its playbooks (with the name each gives the play when it is not the master one), and the name it
    has in Create-A-Play when it is in it."""
    lines = [f"Plays that use the route (step list {PSAL}): {len(entries)} plays (PLYL = the play's id in the game files; the last part says which are in Create-A-Play)", ""]
    for e in entries:
        books = sorted(e["books"], key=lambda b: book_names.get(b, ""))
        names = [book_label(book_names.get(b, f"playbook {b}"), e.get("called", {}).get(b), e["name"]) for b in books]
        lines.append(f"PLYL {e['plyl']} | {e['name']} | set {e['set']} | {e['form']} | {' and '.join(e['who'])} | {len(names)} playbook(s): {'; '.join(names)}" + (f" | in Create-A-Play as {e['cap'].strip()}" if e.get("cap") else ""))
    return "\n".join(lines) + "\n"


def side_of(x):
    return "left" if x < 82 else ("right" if x > 98 else "middle")


def stock_rows():
    return [dict(step=s, code=c, val1=a, val2=b, val3=d) for s, c, a, b, d in STOCK]


def rows_of(table_rows):
    """The route's rows from a PSLO export (list of dicts with strings), as [(step, code, val1, val2, val3)] by step."""
    out = [(int(r["step"]), int(r["code"]), int(r["val1"]), int(r["val2"]), int(r["val3"])) for r in table_rows if int(r["PSAL"]) == PSAL]
    return sorted(out)


def is_stock(rows):
    return tuple(rows) == STOCK


def wanted_rows(test_id):
    """The rows the route should have for a test: the stock rows with that test's changes."""
    changes = TEST_BY_ID[test_id]["changes"]
    out = []
    for s, c, a, b, d in STOCK:
        vals = {"val1": a, "val2": b, "val3": d}
        vals.update(changes.get(s, {}))
        out.append((s, c, vals["val1"], vals["val2"], vals["val3"]))
    return out


def edits_for(test_id, current, table=TABLE):
    """Bridge edits that turn the route's current rows into the wanted ones (only the numbers that differ), each checked against what is there now; [] if there is nothing to do.
    current: [(step, code, val1, val2, val3)] as read from the file; table: the step table of that copy (PSLO in the master, PSAL in an in-game copy)."""
    now = {s: (c, a, b, d) for s, c, a, b, d in current}
    if sorted(now) != [s for s, *_ in STOCK] or any(now[s][0] != c for s, c, *_ in STOCK):
        raise ValueError("This route does not look like the game this test was made for (the steps are different), so nothing is changed.")
    edits = []
    for s, c, a, b, d in wanted_rows(test_id):
        old = dict(zip(("val1", "val2", "val3"), now[s][1:]))
        new = {"val1": a, "val2": b, "val3": d}
        diff = {k: v for k, v in new.items() if old[k] != v}
        if diff:
            edits.append({"table": table, "match": {"PSAL": PSAL, "step": s}, "expect": {k: old[k] for k in diff}, "set": diff})
    return edits


# ---- the copies of the route in the game files
# A copy is {"kind": "master" | "game", "file": "qkl_boot.ast", "index": 40, "table": "PSLO" | "PSAL", "rows": [(step, code, v1, v2, v3)], ...} (the rest, ast/start/size, is for the writer).
def copy_name(c):
    return ("the master copy" if c["kind"] == "master" else "the in-game copy") + f" ({c['file']} entry {c['index']})"


def copies_text(copies):
    """For the report: which game files hold the route."""
    return " + ".join(f"{c['file']} entry {c['index']} ({'master' if c['kind'] == 'master' else 'in-game'})" for c in copies)


def selected(copies, where):
    return [c for c in copies if where == "both" or c["kind"] == where]


def plan_edits(test_id, copies, where="both"):
    """[(copy, edits)] for the copies that need a write. The copies chosen by `where` get the numbers of the test, every other copy is put back to the game's own, so after a test the
    route is the same in the chosen copies and stock everywhere else (a test never leaves a half-changed route behind)."""
    if not selected(copies, where):
        raise ValueError("The route was not found in " + ("the in-game copy of the play database (qkl_fe2ig.ast): choose \"Both copies\" or \"Master copy only\"." if where == "game" else "the master copy of the play database."))
    chosen = selected(copies, where)
    out = []
    for c in copies:
        e = edits_for(test_id if c in chosen else "B0", c["rows"], c["table"])
        if e:
            out.append((c, e))
    return out


def label_of(rows):
    """"stock" for the game's own rows, the id of the test whose numbers these are, or None."""
    if is_stock(rows):
        return "stock"
    for t in TESTS:
        if tuple(wanted_rows(t["id"])) == tuple(rows):
            return t["id"]
    return None


def describe_state(copies):
    """(level, text) for the status line: level is "ok" (the game's own), "changed" (one test, in every copy it was written to) or "odd" (numbers that belong to no test, or a mix)."""
    states = [(c, label_of(c["rows"])) for c in copies]
    many = len(copies) > 1
    if all(s == "stock" for _, s in states):
        return "ok", "The route in your game files is the game's own (nothing changed)." if many else "The route in your game file is the game's own (nothing changed)."
    odd = [c for c, s in states if s is None]
    if odd:
        return "odd", f"The route in {' and in '.join(copy_name(c) for c in odd)} has numbers that do not belong to any test. Press Put the route back to the game's own."
    changed = [(c, s) for c, s in states if s != "stock"]
    ids = {s for _, s in changed}
    if len(ids) > 1:
        return "odd", "The copies of the route are changed for different tests. Press Put the route back to the game's own."
    t = ids.pop()
    where = " and ".join(copy_name(c) for c, _ in changed)
    rest = [c for c, s in states if s == "stock"]
    return "changed", f"The route is changed for test {t}: {TEST_BY_ID[t]['title']} - in {where}." + (f" Not changed: {' and '.join(copy_name(c) for c in rest)}." if rest else "")


def describe_changes(test_id):
    """Plain words for what a test changes."""
    ch = TEST_BY_ID[test_id]["changes"]
    if not ch:
        return "Nothing: the route is the game's own."
    out = []
    for s, cols in sorted(ch.items()):
        for col, v in cols.items():
            stock = {"val1": STOCK[s][2], "val2": STOCK[s][3], "val3": STOCK[s][4]}[col]
            out.append(f"{ROW_NAMES[s]}: {COLUMN_NAMES[col]} {stock} becomes {v}")
    return "; ".join(out) + "."


def report(state, route_plays=None, game=""):
    """The tester's results as text to paste into Discord: one block per test with what was recorded. state: {"results": {test_id: {field: value}}, "applied": [ids],
    "applied_where": {test_id: "both" | "game" | "master"} (where the test's numbers were written)}."""
    lines = ["**HC09 route test results**", f"Route: step list {PSAL} (the Post route; PSLO in the master copy, PSAL in the in-game copy; stock rows {', '.join('%d(%d,%d,%d)' % (c, a, b, d) for _, c, a, b, d in STOCK[:4])})"]
    if game:
        lines.append(game)
    if route_plays:
        lines.append("Plays that use it: " + ", ".join(route_plays))
    lines.append("")
    results = state.get("results", {})
    for t in TESTS:
        r = results.get(t["id"])
        lines.append(f"**{t['id']} - {t['title']}**")
        if not r:
            lines.append("not done")
            lines.append("")
            continue
        w = state.get("applied_where", {}).get(t["id"])
        if w in WHERE_LABEL:
            lines.append(f"- Written to: {WHERE_LABEL[w].lower().replace(' (recommended)', '')}")
        for key, label, _ in RESULT_FIELDS:
            v = (r.get(key) or "").strip()
            if v:
                lines.append(f"- {label.split('(')[0].strip()}: {v}")
        for key, label in LEGACY_FIELDS.items():
            if (r.get(key) or "").strip():
                lines.append(f"- {label}: {r[key].strip()}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
