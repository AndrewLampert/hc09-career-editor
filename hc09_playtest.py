"""
Test plays: the seven custom plays of Part A of the test guide, worked out in one go so the editor can make and install them with a single button.

Standard library only (no Tk). All seven start from the same stock play (Slants, set Big, formation Singleback) and each changes one thing, so that what the game does with
each kind of change can be told apart:

    T1  nothing (the control: does the game accept a custom play at all?)
    T2  the kind of play: play-action pass
    T3  the kind of play: handoff run
    T4  the kind of play: triple option, in a set that has no triple option (the assignments come from other formations)
    T5  one receiver's route: WR1 runs an out, medium
    T6  the quarterback's reads: WR1 first, TE1 second
    T7  one player's place: WR1 stands 7 yards from the middle of the field

build_tests(lib, types, catalog) returns one spec per test (what to give hc09_plays.build_custom_play); report() writes the tester's answers as text for the chat.
"""

BASE_PLAY = "Slants"
BASE_SET = "Big"
MOVED_TO = 7.0                      # T7: WR1 is moved to this many yards from the middle (on the side he stands on)
READ_CHANCES = (100, 20, 10, 5, 1)  # what the plays made in the game usually have, first read to last

YES = ("", "yes", "partly", "no", "could not tell")
COMMON = (
    ("listed", "Is the play listed under Created Plays, with its name?", ("", "yes", "no", "yes, but its diagram looks different from the original")),
    ("called", "Could you call it without the game crashing or freezing?", ("", "yes", "the game crashed or froze", "I could not call it")),
)
NOTES = ("notes", "Anything odd, in your own words (players standing still, a wrong formation, missing players ...)", None)


def _checks(*extra):
    return COMMON + tuple(extra) + (NOTES,)


def find_base(lib):
    """The stock play every test starts from: Slants in the set Big (the one with the Singleback formation when there are several)."""
    found = [p for p in lib.plays.values() if p["name"] == BASE_PLAY and lib.sets[p["setl"]]["name"] == BASE_SET and lib.play_side(p["plyl"]) == "offense"]
    if not found:
        raise RuntimeError(f"The play {BASE_PLAY} (set {BASE_SET}) was not found in the game files, so the test plays cannot be made.")
    found.sort(key=lambda p: (lib.form_names.get(lib.sets[p["setl"]]["form"], "") != "Singleback", p["plyl"]))
    return found[0]["plyl"]


def kind_plan(lib, types, plyl, family):
    """(overrides, plan) of turning a play into another kind of play, the way the Play creator does it (Change the kind of play, then Make custom play): the players whose
    assignment does not fit change, and the plan names where the kind's tables are taken from."""
    detail = lib.detail(plyl)
    setl = detail["set"]["setl"]
    stock = {sl["poso"]: (sl["psal"], sl["artl"], sl["plrr"]) for sl in detail["slots"]}
    first = types.convert(plyl, family, current=stock, keep=set())
    overrides = dict(first["overrides"])
    now = types.family_of_assignments(setl, {**stock, **overrides})
    if now != family:
        raise RuntimeError(f"The converted play does not come out as a {family} but as {now}.")
    base = types.family_of_play(plyl)
    plan = types.convert(plyl, now, current={**stock, **overrides}, keep=set(overrides)) if now != base else None
    return overrides, plan, first


def _slot(detail, label):
    return next((s for s in detail["slots"] if s["label"] == label), None)


def _yards(x):
    return f"{abs(x):.1f} yards {'right' if x > 0 else 'left'} of the center"


def build_tests(lib, types, catalog):
    """The seven tests as a list of dicts: id, name (the custom play's name), title, changed (what was changed, in words), look (what to look at in the game), checks (the questions:
    key, label, options or None), plyl (the stock play), overrides, plan, reads, alignment (what to give build_custom_play)."""
    base = find_base(lib)
    detail = lib.detail(base)
    setl = detail["set"]["setl"]
    where = lib.form_names.get(detail["set"]["form"], "")
    start = f"{BASE_PLAY} ({where}, set {BASE_SET})"
    align = lib.alignment(setl)
    wr1, te1 = _slot(detail, "WR1"), _slot(detail, "TE1")
    if wr1 is None or wr1["poso"] not in align:
        raise RuntimeError("The test play has no WR1, so the test plays cannot be made.")
    x0, y0 = align[wr1["poso"]]["x"], align[wr1["poso"]]["y"]
    side = "right" if x0 > 0 else "left"

    def spec(tid, name, title, changed, look, checks, overrides=None, plan=None, reads=None, alignment=None):
        return {"id": tid, "name": name, "title": title, "changed": changed, "look": look, "checks": checks, "plyl": base, "overrides": overrides or {}, "plan": plan, "reads": reads,
                "alignment": alignment}

    tests = [spec("T1", "T1 Slants", "The control: a copy of Slants, nothing changed", f"Nothing: a copy of {start}.",
                  "It should look and run like the original Slants. This one shows whether the game accepts a custom play from the editor at all.",
                  _checks(("behaves", "Does it run like the original Slants (the receivers run slants, the quarterback throws)?", YES),
                          ("wr_before", f"Before the snap, where does WR1, the wide receiver on the {side}, stand? (yards from the sideline or the hash marks, your own words)", None)))]

    ov, plan, first = kind_plan(lib, types, base, "play_action")
    tests.append(spec("T2", "T2 Slants PA", "The kind of play: play-action pass", f"{len(first['changes'])} players changed so that it works as a play-action pass ({first['source']}).",
                      "The quarterback turns and fakes the handoff, the linemen fire out as if to run block and then pass block, the back fakes taking the ball, the receivers run their routes and the quarterback throws.",
                      _checks(("fakes", "The quarterback turns and fakes the handoff, then throws", YES), ("line", "The linemen fire out as if to run block, then pass block", YES),
                              ("back", "The back fakes taking the ball", YES), ("routes", "The receivers run their routes and a pass is thrown", YES)), overrides=ov, plan=plan))
    ov, plan, first = kind_plan(lib, types, base, "handoff")
    tests.append(spec("T3", "T3 Slants Run", "The kind of play: handoff run", f"{len(first['changes'])} players changed so that it works as a handoff run ({first['source']}).",
                      "The quarterback hands off, a back takes the ball and runs, the linemen run block and the receivers block downfield instead of running routes.",
                      _checks(("hands", "The quarterback hands off", YES), ("runs", "A back takes the handoff and runs", YES), ("line", "The linemen run block", YES),
                              ("wr", "The receivers block downfield instead of running routes", YES)), overrides=ov, plan=plan))
    ov, plan, first = kind_plan(lib, types, base, "triple_option")
    tests.append(spec("T4", "T4 To Triple", "The kind of play: triple option (no triple option in this set)", f"{len(first['changes'])} players changed so that it works as a triple option ({first['source']}).",
                      "No triple option uses this set, so the assignments come from other formations. Does the quarterback run the option (ride, then keep or pitch) and does a back take a pitch? Does anything stand still or run into the wrong place?",
                      _checks(("option", "The quarterback runs the option (rides, then keeps or pitches)", YES), ("pitch", "A back takes a pitch", YES),
                              ("odd", "Does anything stand still or run into the wrong place?", ("", "nothing odd", "yes (describe below)"))), overrides=ov, plan=plan))

    ch = catalog.choices("offense", wr1["epos"], wr1["dpos"], wr1["x"], kind=types.family_of_play(base), only_fitting=True)
    out = next((c for c in ch if c["label"] == "Out, medium"), None)
    if out is None:
        raise RuntimeError("The route 'Out, medium' was not found for WR1, so test T5 cannot be made.")
    tests.append(spec("T5", "T5 WR Out", "One receiver's route: WR1 runs an out", "WR1 now runs an out, medium (up the field, then toward the sideline).",
                      "Watch WR1: up the field, then toward the sideline.", _checks(("out", "WR1 runs an out route (up the field, then toward the sideline)", YES)), overrides={wr1["poso"]: out["entry"]}))

    own = [(int(detail["passing"][f"rcv{k}"]), int(detail["passing"][f"per{k}"])) for k in range(1, 6)] if detail["passing"] else []
    if len(own) != 5:
        raise RuntimeError("The test play has no pass reads, so test T6 cannot be made.")
    first_reads = [wr1["poso"]] + ([te1["poso"]] if te1 is not None else [])
    order = first_reads + [p for p, _c in own if p not in first_reads]
    reads = [(poso, READ_CHANCES[k]) for k, poso in enumerate(order)]
    names = {s["poso"]: s["label"] for s in detail["slots"]}
    tests.append(spec("T6", "T6 Reads", "The quarterback's reads: WR1 first, TE1 second", "The reads are in this order: " + ", ".join(names[p] for p in order) + ".",
                      "On the play's diagram in the playbook the numbers 1 to 5 stand on the receivers in that order. With no pressure the quarterback looks to WR1 first.",
                      _checks(("numbers", "On the diagram the numbers 1 to 5 stand on the receivers in this order: " + ", ".join(names[p] for p in order), YES),
                              ("first", "With no pressure the quarterback looks to WR1 first", YES)), reads=reads))

    x1 = MOVED_TO if x0 > 0 else -MOVED_TO
    tests.append(spec("T7", "T7 Moved WR", f"One player's place: WR1 moved to {abs(x1):.0f} yards from the middle",
                      f"WR1 stands {_yards(x1)} and {abs(y0):.1f} yards behind the line (in T1 he stands {_yards(x0)}).",
                      f"Before the snap, WR1 should stand about {abs(x1):.0f} yards from the middle of the field (near the hash marks, inside the numbers) instead of out by the sideline like in T1.",
                      _checks(("wr_after", "Before the snap, where does WR1 stand now? (yards from the middle, or near the hash marks, your own words)", None),
                              ("moved", f"He stands about {abs(x1):.0f} yards from the middle (not out by the sideline like in T1)", YES),
                              ("diagram", "The play's diagram in the playbook shows him moved", YES),
                              ("flip", "If the game lets you flip the play: the whole formation is the mirror image", ("", "yes", "no", "could not flip it"))), alignment={wr1["poso"]: (x1, y0)}))
    for t in tests:
        if len(t["name"]) > 24:
            raise RuntimeError(f"The name {t['name']} is longer than 24 characters.")
    return tests


def by_id(tests):
    return {t["id"]: t for t in tests}


def existing_names(pbpl_rows, tests):
    """The test plays' names that the profile already has (a run before): names of the profile's PBPL rows, compared without regard to case."""
    have = {(r.get("name") or "").strip().lower() for r in pbpl_rows}
    return [t["name"] for t in tests if t["name"].lower() in have]


def report(state, tests, game=""):
    """The tester's answers as text to paste into the chat: one block per test. state: {"results": {test_id: {key: value}}, "made": {...}}."""
    lines = ["**HC09 test plays results**"]
    made = state.get("made") or {}
    if made.get("playbook"):
        lines.append(f"The seven plays were added to custom playbook {made['playbook']}" + (f" on {made['time']}" if made.get("time") else "") + ".")
    if game:
        lines.append(game)
    lines.append("")
    results = state.get("results", {})
    for t in tests:
        r = results.get(t["id"])
        lines.append(f"**{t['id']} - {t['name']}** ({t['title']})")
        if not r:
            lines.append("not done")
            lines.append("")
            continue
        for key, label, _options in t["checks"]:
            v = (r.get(key) or "").strip()
            if v:
                lines.append(f"- {label.split(' (')[0].rstrip('?').strip()}: {v}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
