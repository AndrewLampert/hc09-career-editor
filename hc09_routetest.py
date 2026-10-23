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

# A test: id, title, the changes {step: {column: new value}}, what it asks, what to watch for. The first number of a leg is guessed to be its length, the second its heading
# (32 straight up the field), a cut's two numbers its side and its sharpness: these tests check that.
TESTS = (
    {"id": "B0", "phase": 1, "title": "Stock route (control)", "changes": {},
     "asks": "How does the route run before any change? This is what the others are compared with.",
     "watch": "How many yards past the line of scrimmage does the receiver run before he breaks? Which way does he break (toward the middle, toward the sideline, straight on, back)? How many yards past the line is he when he is thrown to or stops?"},
    {"id": "B1", "phase": 1, "title": "Longer stem: first leg, first number 68 -> 136", "changes": {0: {"val1": 136}},
     "asks": "Does the game use the edited file at all, and is the leg's first number its length?",
     "watch": "If the receiver now runs about twice as far before he breaks, both are yes. If nothing is different, the game is not reading this file for routes (tell us, this decides everything)."},
    {"id": "B2", "phase": 1, "title": "Heading of the second leg: second number 42 -> 16", "changes": {2: {"val2": 16}},
     "asks": "Is a leg's second number the direction it runs?",
     "watch": "Does the receiver break in a different direction than in the stock route (more toward the middle, toward the sideline, more upfield)? Roughly what angle?"},
    {"id": "B3", "phase": 1, "title": "Heading of the second leg: second number 42 -> 64", "changes": {2: {"val2": 64}},
     "asks": "Which way do larger and smaller numbers turn the leg (compare with B2)?",
     "watch": "Which way does the receiver break now: more toward the middle, toward the sideline, or upfield? Is it opposite to B2?"},
    {"id": "B4", "phase": 1, "title": "Side of the cut: first number 2 -> 1", "changes": {1: {"val1": 1}},
     "asks": "Is the cut's first number the side it turns to?",
     "watch": "Does the receiver turn to the other side (toward the sideline instead of the middle, or the other way round)?"},
    {"id": "B5", "phase": 1, "title": "Sharpness of the cut: second number 1 -> 5", "changes": {1: {"val2": 5}},
     "asks": "What does the cut's second number change?",
     "watch": "Does the break get sharper or rounder, or change its angle, or does the receiver stop first? Describe what you see."},
    {"id": "B6", "phase": 2, "title": "Shorter second leg: first number 200 -> 60", "changes": {2: {"val1": 60}},
     "asks": "Is the second leg's first number also a length?",
     "watch": "Does the receiver stop sooner after the break (how many yards after it)?"},
    {"id": "B7", "phase": 2, "title": "Heading of the first leg: second number 32 -> 16", "changes": {0: {"val2": 16}},
     "asks": "Does the second number work the same way on the stem?",
     "watch": "Does the receiver now start off at an angle instead of straight upfield? Which way?"},
    {"id": "B8", "phase": 2, "title": "Third number of the second leg: 254 -> 127", "changes": {2: {"val3": 127}},
     "asks": "What does the third number (254 on every leg) mean?",
     "watch": "Does anything change (speed, how far he runs, when he stops)? Nothing is a fine answer."},
    {"id": "B9", "phase": 2, "title": "Sharpness of the cut: second number 1 -> 2", "changes": {1: {"val2": 2}},
     "asks": "Compare with B5: how do the cut's second-number values differ?",
     "watch": "Is the break different from the stock route and from B5? How?"},
    {"id": "B10", "phase": 1, "title": "Stock again (control after putting the route back)", "changes": {},
     "asks": "Did putting the route back work? The route should run exactly as in B0.",
     "watch": "Does the route run the same as in B0?"},
)
TEST_BY_ID = {t["id"]: t for t in TESTS}

RESULT_FIELDS = (
    ("changed", "Did the route change from the stock route?", ("", "no change at all", "yes, it changed (describe below)", "the game crashed or froze", "I could not call the play")),
    ("stem", "Yards past the line before the break (a number, 0 if you cannot tell)", None),
    ("direction", "Which way did he break?", ("", "toward the middle", "toward the sideline", "straight upfield", "back toward the quarterback", "no break", "other (describe below)")),
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


def watch_line(play, plyl, set_name, formation, who, book_names):
    """"WR Post (PLYL 1159) - Normal, I Form - WR1, wide on the right, ... - 7 playbooks: Reid All Passing, Zorn West Coast, and 5 more": a play that uses the route, with its id (PLYL), set and
    formation (several sets are called "Normal"), the receiver (receiver_text) and the playbooks that have it. who: [receiver_text]."""
    names = list(book_names)
    shown = ", ".join(names[:2]) + (f", and {len(names) - 2} more" if len(names) > 2 else "")
    return f"{play} (PLYL {plyl}) - {set_name}, {formation} - {' and '.join(who)} - {len(names)} playbook{'s' if len(names) != 1 else ''}" + (f": {shown}" if names else "")


def choose_play(entries, book_names, holders, my_team="", my_book=None):
    """The one play and team a tester should use. entries: [{"plyl", "name", "set", "form", "who", "books": [playbook ids], "read": the route runner's place in the quarterback's reads
    (0 when the play is not a pass or he is not a read), "option": an option play} with the plays in the most playbooks first; book_names: {playbook id: name}; holders: {playbook id: [teams
    that play it]}; my_team / my_book: the team chosen in the editor and the playbook it plays. An ordinary pass that throws to the route runner is the easiest to watch (a run play only uses him
    as a decoy, an option play is hard to follow): the tester's own team when its playbook has such a play, else the best such play and a team that plays one of its playbooks, then worse plays the
    same way. Returns {"entry", "team", "playbook", "others": [(team, playbook)]} or None."""
    if not entries:
        return None
    name_of = lambda b: book_names.get(b, f"playbook {b}")

    def build(e, book, team):
        others = []
        for b in sorted(e["books"], key=name_of):
            for t in holders.get(b, ()):
                if t != team and all(t != o[0] for o in others) and len(others) < 3:
                    others.append((t, name_of(b)))
        return {"entry": e, "team": team, "playbook": name_of(book) if book is not None else "", "others": others}

    tiers = [[e for e in entries if e.get("read") and not e.get("option")], [e for e in entries if e.get("read")], entries]
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
    text = f"{start} Call {e['name']} (PLYL {e['plyl']}): the {e['form']} formation, the {e['set']} set. Watch {' and '.join(e['who'])}. Use this same play for every test."
    if pick["others"]:
        text += " If you cannot use that team: " + "; ".join(f"the {t} ({b})" for t, b in pick["others"]) + " have it too."
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
    """Every play that uses the route, for the chat: PLYL, name, set, formation, receiver, all its playbooks, and the name it has in Create-A-Play when it is in it."""
    lines = [f"Plays that use the route (step list {PSAL}): {len(entries)} plays (PLYL = the play's id in the game files; the last part says which are in Create-A-Play)", ""]
    for e in entries:
        names = [book_names.get(b, f"playbook {b}") for b in sorted(e["books"], key=lambda b: book_names.get(b, ""))]
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
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
