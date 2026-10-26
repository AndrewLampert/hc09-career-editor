"""
Test plays: the nine custom plays of Part A of the test guide, worked out in one go so the editor can make and install them with a single button.

Standard library only (no Tk). All nine start from the same stock play (Slants, set Big, formation Singleback) and each changes one thing (T9 two), so that what the game does with
each kind of change can be told apart:

    T1  nothing (the control: does the game accept a custom play at all?)
    T2  the kind of play: play-action pass
    T3  the kind of play: handoff run
    T4  the kind of play: triple option, in a set that has no triple option (the assignments come from other formations)
    T5  one receiver's route: the receiver alone on the left (WR2 in Slants) runs an out, medium
    T6  the quarterback's reads: that receiver first, the tight end next to him second
    T7  one player's place: that receiver stands 9 yards from the middle of the field (dragging a player on the field in the Play creator writes the same thing)
    T8  the quarterback's named option: a rollout to the right
    T9  a play-action pass whose quarterback is the named option "Play-action boot left"

build_tests(lib, types, catalog) returns one spec per test (what to give hc09_plays.build_custom_play); report() writes the tester's answers as text for the chat.
"""

NUMBER_WORDS = {1: "one", 7: "seven", 9: "nine"}


def count_word(n):
    """The number of tests in words, for the window's texts."""
    return NUMBER_WORDS.get(n, str(n))


BASE_PLAY = "Slants"
BASE_SET = "Big"
MOVED_TO = 9.0                      # T7: the receiver is moved to this many yards from the middle (on the side he stands on): 6 yards in from where Slants has him, 4 yards from the tight end
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


def kind_plan(lib, types, plyl, family, extra=None):
    """(overrides, plan) of turning a play into another kind of play, the way the Play creator does it (Change the kind of play, then Make custom play): the players whose
    assignment does not fit change, and the plan names where the kind's tables are taken from. extra: assignments chosen by hand afterwards ({poso: entry}), which stay."""
    detail = lib.detail(plyl)
    setl = detail["set"]["setl"]
    stock = {sl["poso"]: (sl["psal"], sl["artl"], sl["plrr"]) for sl in detail["slots"]}
    first = types.convert(plyl, family, current=stock, keep=set())
    overrides = dict(first["overrides"])
    overrides.update(extra or {})
    now = types.family_of_assignments(setl, {**stock, **overrides})
    if now != family:
        raise RuntimeError(f"The converted play does not come out as a {family} but as {now}.")
    base = types.family_of_play(plyl)
    plan = types.convert(plyl, now, current={**stock, **overrides}, keep=set(overrides)) if now != base else None
    return overrides, plan, first


def _slot(detail, label):
    return next((s for s in detail["slots"] if s["label"] == label), None)


def focus_receiver(detail, align):
    """The receiver the tests T1, T5, T6 and T7 are about: a wide receiver who stands alone, on the left side if there is one (a tester could not tell the moved receiver from the others
    when he stood in a group), else the most alone one. The most alone = the farthest from every other player. None when the play has no wide receiver."""
    def gap(s):
        a = align[s["poso"]]
        return min(((a["x"] - align[o["poso"]]["x"]) ** 2 + (a["y"] - align[o["poso"]]["y"]) ** 2) ** 0.5 for o in detail["slots"] if o["poso"] != s["poso"] and o["poso"] in align)
    wrs = [s for s in detail["slots"] if s["epos"] == 3 and s["poso"] in align]
    pool = [s for s in wrs if align[s["poso"]]["x"] < 0] or wrs
    return max(pool, key=lambda s: (round(gap(s), 3), -s["dpos"])) if pool else None


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
    wr1 = focus_receiver(detail, align)
    if wr1 is None:
        raise RuntimeError("The test play has no wide receiver, so the test plays cannot be made.")
    wl = wr1["label"]                                           # WR2 in Slants: the receiver alone on the left
    x0, y0 = align[wr1["poso"]]["x"], align[wr1["poso"]]["y"]
    side = "right" if x0 > 0 else "left"
    tes = [sl for sl in detail["slots"] if sl["epos"] == 4 and sl["poso"] in align]
    te1 = min(tes, key=lambda sl: abs(align[sl["poso"]]["x"] - x0)) if tes else None      # the tight end next to him
    tl = te1["label"] if te1 is not None else "TE1"

    def spec(tid, name, title, changed, look, checks, overrides=None, plan=None, reads=None, alignment=None):
        return {"id": tid, "name": name, "title": title, "changed": changed, "look": look, "checks": checks, "plyl": base, "overrides": overrides or {}, "plan": plan, "reads": reads,
                "alignment": alignment}

    tests = [spec("T1", "T1 Slants", "The control: a copy of Slants, nothing changed", f"Nothing: a copy of {start}.",
                  "It should look and run like the original Slants. This one shows whether the game accepts a custom play from the editor at all.",
                  _checks(("behaves", "Does it run like the original Slants (the receivers run slants, the quarterback throws)?", YES),
                          ("wr_before", f"Before the snap, where does {wl}, the wide receiver alone on the {side} side, stand? (yards from the sideline or the hash marks, your own words)", None)))]

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
        raise RuntimeError(f"The route 'Out, medium' was not found for {wl}, so test T5 cannot be made.")
    tests.append(spec("T5", "T5 WR Out", f"One receiver's route: {wl} runs an out", f"{wl} (the receiver alone on the {side}) now runs an out, medium (up the field, then toward the sideline).",
                      f"Watch {wl}: up the field, then toward the sideline.", _checks(("out", f"{wl} runs an out route (up the field, then toward the sideline)", YES)), overrides={wr1["poso"]: out["entry"]}))

    own = [(int(detail["passing"][f"rcv{k}"]), int(detail["passing"][f"per{k}"])) for k in range(1, 6)] if detail["passing"] else []
    if len(own) != 5:
        raise RuntimeError("The test play has no pass reads, so test T6 cannot be made.")
    first_reads = [wr1["poso"]] + ([te1["poso"]] if te1 is not None else [])
    order = first_reads + [p for p, _c in own if p not in first_reads]
    reads = [(poso, READ_CHANCES[k]) for k, poso in enumerate(order)]
    names = {s["poso"]: s["label"] for s in detail["slots"]}
    tests.append(spec("T6", "T6 Reads", f"The quarterback's reads: {wl} first, {tl} second", "The reads are in this order: " + ", ".join(names[p] for p in order) + ".",
                      f"On the play's diagram in the playbook the numbers 1 to 5 stand on the receivers in that order. With no pressure the quarterback looks to {wl} first.",
                      _checks(("numbers", "On the diagram the numbers 1 to 5 stand on the receivers in this order: " + ", ".join(names[p] for p in order), YES),
                              ("first", f"With no pressure the quarterback looks to {wl} first", YES)), reads=reads))

    x1 = MOVED_TO if x0 > 0 else -MOVED_TO
    tests.append(spec("T7", "T7 Moved WR", f"One player's place: {wl} moved to {abs(x1):.0f} yards from the middle",
                      f"{wl} (the receiver alone on the {side}) stands {_yards(x1)} and {abs(y0):.1f} yards behind the line (in T1 he stands {_yards(x0)}).",
                      f"Before the snap, {wl} should stand about {abs(x1):.0f} yards from the middle of the field, between the hash marks and the numbers and about {abs(abs(x1) - abs(align[te1['poso']]['x'])) if te1 is not None else 0:.0f} yards outside the tight end, instead of out wide like in T1 ({abs(x0):.0f} yards).",
                      _checks(("wr_after", f"Before the snap, where does {wl} stand now? (yards from the middle, or how far he is from the tight end, your own words)", None),
                              ("moved", f"He stands about {abs(x1):.0f} yards from the middle (not out by the sideline like in T1)", YES),
                              ("diagram", "The play's diagram in the playbook shows him moved", YES),
                              ("flip", "If the game lets you flip the play: the whole formation is the mirror image", ("", "yes", "no", "could not flip it"))), alignment={wr1["poso"]: (x1, y0)}))

    qb = _slot(detail, "QB")
    if qb is None:
        raise RuntimeError("The test play has no QB, so the tests T8 and T9 cannot be made.")
    qb_options = {c["label"]: c for c in catalog.choices("offense", 0, qb["dpos"], qb["x"])}
    for label in ("Rollout right", "Play-action boot left"):
        if label not in qb_options:
            raise RuntimeError(f"The quarterback option '{label}' was not found, so the tests T8 and T9 cannot be made.")
    roll = {qb["poso"]: qb_options["Rollout right"]["entry"]}
    stock = {sl["poso"]: (sl["psal"], sl["artl"], sl["plrr"]) for sl in detail["slots"]}
    if types.family_of_assignments(setl, {**stock, **roll}) != types.family_of_play(base):
        raise RuntimeError("The rollout is not a dropback pass here, so test T8 cannot be made.")
    tests.append(spec("T8", "T8 QB Rollout Right", "The quarterback's option: a rollout to the right", "The quarterback now runs a rollout to the right instead of dropping straight back; everything else is as in T1.",
                      "After the snap the quarterback runs out to the right, away from the middle, and throws on the move. The receivers still run their slants.",
                      _checks(("rolls", "The quarterback runs out to the right after the snap (he does not just drop straight back)", YES), ("throws", "He throws while he is moving", YES),
                              ("routes", "The receivers run their routes as in T1", YES)), overrides=roll))
    boot = {qb["poso"]: qb_options["Play-action boot left"]["entry"]}
    ov, plan, first = kind_plan(lib, types, base, "play_action", extra=boot)
    tests.append(spec("T9", "T9 PA Boot Left", "The quarterback's option: a play-action boot to the left", f"A play-action pass (as T2, {len(first['changes'])} players changed) whose quarterback fakes the handoff and then runs out to the left.",
                      "The quarterback turns and fakes the handoff, then runs out to the left and throws on the move. The back fakes, the linemen fire out and then pass block.",
                      _checks(("fakes", "The quarterback fakes the handoff first", YES), ("boot", "Then he runs out to the left and not straight back", YES), ("throws", "He throws on the move", YES),
                              ("back", "The back fakes taking the ball", YES)), overrides=ov, plan=plan))
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
        lines.append(f"The {count_word(len(made.get('ids') or tests))} plays were added to custom playbook {made['playbook']}" + (f" on {made['time']}" if made.get("time") else "") + ".")
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
