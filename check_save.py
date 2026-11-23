"""Check what a Head Coach 09 save holds, without opening the editor.

    python check_save.py <save file or its folder>          (or drag the save onto "Check My Save.bat")
    python check_save.py                                    (no save given: lists the saves it can find (HC09 / HC27 PC installs anywhere on the drives; RPCS3 and Xenia in their usual places) and checks the one you pick)

Why it exists: the editor can only show what the save has. When a tab is empty (Draft Picks, Playbooks) this says whether the save has the table at all (MISSING), has it with no rows (EMPTY), or has it
filled (the row count), and writes the same report, with every table of the save, to check_save_report.txt next to this file so it can be sent on. It reads the save; it never changes it.
"""
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import hc09_detect as D                                  # noqa: E402
import hc09_addplay as AP                                # noqa: E402

BRIDGE_JS = os.path.join(HERE, "hc09-bridge", "bridge.js")
REPORT_NAME = "check_save_report.txt"
MAX_SAVES = 12                                           # a folder with more saves than this: the newest are checked, the rest are named

BOOKS_WHY = "The Playbooks tab builds every team's playbook from the four playbook tables (PGPL, PGSL, PGSS, PGFM): without this one the playbooks come out empty."

# (table, what it holds, the editor tab that reads it, rows in a healthy career made by the Xbox game (None: it varies), what it means when it is not there)
CAREER_TABLES = [
    ("DRPK", "draft picks", "Draft Picks", 448, "The Draft Picks tab lists these rows, so it shows nothing."),
    ("PGPL", "playbook plays (book, set, play)", "Playbooks", 9133, BOOKS_WHY),
    ("PGSL", "playbook sets by formation", "Playbooks", 1790, BOOKS_WHY),
    ("PGSS", "playbook sets", "Playbooks", 1763, BOOKS_WHY),
    ("PGFM", "playbook formations", "Playbooks", 666, BOOKS_WHY),
    ("PLAY", "players", "Players", None, "The Players tab lists these rows."),
    ("COCH", "coaches", "Coaches", None, "The Coaches tab lists these rows."),
    ("TEAM", "teams", "Teams", None, "The team lists and drop-downs read these rows."),
]
PROFILE_TABLES = [
    ("PBPL", "custom plays (the game's own editor)", "Playbooks"),
    ("SETL", "custom play sets", "Playbooks"),
    ("PLAB", "custom play book links", "Playbooks"),
    ("SETP", "custom set players", "Playbooks"),
    ("SETG", "custom set places", "Playbooks"),
    ("SGFF", "custom set motions", "Playbooks"),
    ("PLYS", "custom play steps", "Playbooks"),
    ("PLPD", "custom play pass details", "Playbooks"),
    ("PLRD", "custom play run details", "Playbooks"),
    ("PLCM", "custom play comments", "Playbooks"),
]
PLAYBOOK_TABLES = ("PGPL", "PGSL", "PGSS", "PGFM")


class CheckError(Exception):
    """A reason the save could not be checked, in plain words."""


def find_node():
    """The node program, or None."""
    return shutil.which("node")


def table_counts(db_path, node=None):
    """{table name: rows} of every table of a save, in the order the save has them, read by the editor's bridge (the same reader the editor uses)."""
    node = node or find_node()
    if not node:
        raise CheckError("Node.js 18 or newer is not installed (the editor needs it too): install the LTS version from https://nodejs.org/ and run this again.")
    if not os.path.isfile(BRIDGE_JS):
        raise CheckError(f"The editor's bridge is missing ({BRIDGE_JS}): run this from the editor's own folder.")
    try:
        r = subprocess.run([node, BRIDGE_JS, "inspect", "--db", db_path], capture_output=True, text=True, timeout=180, creationflags=D.NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise CheckError("Reading the save took more than three minutes: it may be damaged.")
    except OSError as e:
        raise CheckError(f"Node.js could not be started: {e}")
    if r.returncode != 0:
        said = [ln.strip() for ln in (r.stderr or r.stdout or "").splitlines() if ln.strip() and not ln.strip().startswith("at ")]
        raise CheckError("The save could not be read as a Head Coach 09 database:\n" + ("\n".join(said[:3])[:500] or "(no message)"))
    out = {}
    for line in (r.stdout or "").splitlines():
        m = re.match(r"^\s+(\S+): (\d+) records", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    if not out:
        raise CheckError("The save was read but no tables were found in it.")
    return out



def playbook_link_diagnostics(path, counts, node=None):
    """Read-only check of the career's PGPL -> PGSL -> PGFM references."""
    if any(counts.get(name, 0) <= 0 for name in PLAYBOOK_TABLES):
        return []
    node = node or find_node()
    if not node:
        raise CheckError("Node.js 18 or newer is not installed; playbook links could not be checked.")
    with tempfile.TemporaryDirectory(prefix="hc09-playbook-check-") as folder:
        try:
            result = subprocess.run(
                [node, BRIDGE_JS, "export", "--db", path, "--out", folder,
                 "--tables", ",".join(PLAYBOOK_TABLES)],
                capture_output=True, text=True, timeout=180,
                creationflags=D.NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            raise CheckError("Exporting the playbook links took more than three minutes.")
        except OSError as e:
            raise CheckError(f"Node.js could not export the playbook links: {e}")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "no message").strip().splitlines()
            raise CheckError("The playbook links could not be checked: " + detail[0][:400])
        tables = {}
        for name in PLAYBOOK_TABLES:
            csv_path = os.path.join(folder, name.lower() + ".csv")
            if not os.path.isfile(csv_path):
                raise CheckError(f"The bridge did not export {name}; playbook links could not be checked.")
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                tables[name] = list(csv.DictReader(f))
    issues = AP.playbook_link_issues(tables)
    if not issues:
        return ["Playbook link check: no missing PGPL-to-PGSS, PGPL-to-PGSL or PGSL-to-PGFM links found."]
    lines = [f"Playbook link check: {len(issues)} broken reference(s) found (read-only; nothing was changed)."]
    for issue in issues[:20]:
        if issue["kind"] == "play_without_formation_link":
            lines.append(f"  Book {issue['book']}, set {issue['set']}: play membership has no PGSL formation link.")
        else:
            lines.append(f"  Book {issue['book']}, formation {issue['formation']}: PGSL references a formation absent from PGFM.")
    if len(issues) > 20:
        lines.append(f"  ...and {len(issues) - 20} more.")
    return lines


CUSTOM_PLAY_TABLES = ("PBPL", "SETL", "SETP", "SETG", "SGFF", "PLYS", "PLPD", "PLRD", "PLCM")


def custom_play_diagnostics(path, counts, node=None):
    """Read-only integrity check of the custom-play definitions in a profile save."""
    if counts.get("PBPL", 0) <= 0:
        return ["Custom play check: no custom plays to validate."]
    missing = [name for name in CUSTOM_PLAY_TABLES if name not in counts]
    if missing:
        return ["Custom play check skipped: required table(s) missing: " + ", ".join(missing) + "."]
    node = node or find_node()
    if not node:
        raise CheckError("Node.js 18 or newer is not installed; custom plays could not be checked.")
    with tempfile.TemporaryDirectory(prefix="hc09-custom-play-check-") as folder:
        try:
            result = subprocess.run(
                [node, BRIDGE_JS, "export", "--db", path, "--out", folder,
                 "--tables", ",".join(CUSTOM_PLAY_TABLES)],
                capture_output=True, text=True, timeout=180,
                creationflags=D.NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            raise CheckError("Exporting the custom-play definitions took more than three minutes.")
        except OSError as e:
            raise CheckError(f"Node.js could not export the custom-play definitions: {e}")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "no message").strip().splitlines()
            raise CheckError("The custom-play definitions could not be checked: " + detail[0][:400])
        tables = {}
        for name in CUSTOM_PLAY_TABLES:
            csv_path = os.path.join(folder, name.lower() + ".csv")
            if not os.path.isfile(csv_path):
                raise CheckError(f"The bridge did not export {name}; custom plays could not be checked.")
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                tables[name] = list(csv.DictReader(f))
    issues = AP.custom_play_issues(tables)
    if not issues:
        return ["Custom play check: no broken references or incomplete 11-slot definitions found."]
    lines = [f"Custom play check: {len(issues)} issue(s) found (read-only; nothing was changed)."]
    for issue in issues[:20]:
        kind = issue["kind"]
        if kind == "play_set_missing":
            lines.append(f"  Custom play {issue['play']} references missing set {issue['set']}.")
        elif kind in ("set_slots_invalid", "play_slots_invalid"):
            subject = "set" if kind == "set_slots_invalid" else "play"
            lines.append(f"  Custom {subject} {issue['owner']} has {issue['rows']} slot rows; expected positions 0 through 10 exactly once.")
        elif kind == "alignment_slot_missing":
            lines.append(f"  SETG references missing SETP slot {issue['slot']}.")
        elif kind == "alignment_group_missing":
            lines.append(f"  SETG references missing SGFF group {issue['group']}.")
        elif kind == "alignment_set_mismatch":
            lines.append(f"  SETG slot {issue['slot']} and group {issue['group']} belong to different sets.")
        elif kind == "detail_play_missing":
            lines.append(f"  {issue['table']} references missing custom play {issue['play']}.")
        elif kind == "duplicate_play_id":
            lines.append(f"  PBPL has duplicate play id {issue['id']}.")
        elif kind == "duplicate_set_id":
            lines.append(f"  SETL has duplicate set id {issue['id']}.")
        else:
            lines.append(f"  Invalid {issue.get('table', 'custom-play')} id field {issue.get('field', '')}.")
    if len(issues) > 20:
        lines.append(f"  ...and {len(issues) - 20} more.")
    return lines

def saves_in(path):
    """The save files a path stands for: the file itself, or the saves inside a folder (a package folder holds one file of its own name). Newest first."""
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        return []
    same_name = os.path.join(path, os.path.basename(os.path.normpath(path)))
    if os.path.isfile(same_name):
        return [same_name]
    found = list(D._save_files(path))

    def newest_first(p):
        try:
            return -os.path.getmtime(p)
        except OSError:
            return 0                                   # a file that went away since it was listed sorts last; reading it then says so
    found.sort(key=newest_first)
    return found


def find_saves(extra=(), search=True, budget=25.0):
    """Every career or profile save this computer has, newest first: the places the editor looks (RPCS3, Xenia, the PC versions, the folders in `extra`) and, with `search`, a time-limited search for
    a portable RPCS3 or Xenia in the usual folders (emulator_search_roots) and for the PC versions' saves folders (an install can be anywhere). Returns ([{"platform", "name", "path", "mtime", "size", "kind"}], the folders searched, True when the search ran out of time)."""
    found = []
    roots_to_search = D.emulator_search_roots() if search else ()         # the bounded search for an RPCS3 / Xenia folder outside the usual places (it runs only when none turned up)
    for sv in D.list_saves(D.savedata_roots(D.candidate_rpcs3_dirs([], extra, roots_to_search))):
        found.append({"platform": "RPCS3", "name": sv["name"], "path": sv["path"], "mtime": sv["mtime"], "size": sv["size"], "kind": "career"})
    for sv in D.list_xenia_saves(D.candidate_xenia_dirs([], extra, roots_to_search)):
        found.append({"platform": "Xenia", "name": sv["name"], "path": sv["path"], "mtime": sv["mtime"], "size": sv["size"], "kind": sv["kind"]})
    roots = D.candidate_pcport_roots([], extra)
    searched, timed_out = [], False
    if search:
        places = D.pcport_search_places()
        searched = [p for p, _d in places]
        more, timed_out = D.search_pcport_roots(places, budget)
        roots += [r for r in more if os.path.normcase(r) not in [os.path.normcase(x) for x in roots]]
    for sv in D.list_pcport_saves(roots):
        found.append({"platform": "HC27 (PC)" if sv.get("variant") == "HC27" else "HC09 (PC)", "name": sv["name"], "path": sv["path"], "mtime": sv["mtime"], "size": sv["size"], "kind": sv["kind"]})
    seen, out = set(), []
    for f in sorted(found, key=lambda f: -f["mtime"]):
        key = os.path.normcase(os.path.abspath(f["path"]))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out, searched, timed_out


def choose_save(extra=(), search=True):
    """The no-argument flow: list the saves found, let the person pick one by number (Enter = the newest career) or paste a path. Returns a path or ""."""
    print("Looking for saves (RPCS3, Xenia, HC09 and HC27 for PC)... this can take up to half a minute.")
    saves, searched, timed_out = find_saves(extra, search)
    if searched:
        print("Searched: " + ", ".join(searched) + (" (stopped when the time was up: not every folder was looked at)" if timed_out else ""))
    if not saves:
        print("No saves were found. Drag the save (or its folder) onto Check My Save.bat, or paste its path here.")
    for i, f in enumerate(saves, 1):
        print(f"  {i:>2}. [{f['platform']}] {f['kind']} {f['name']}  ({time.strftime('%Y-%m-%d %H:%M', time.localtime(f['mtime']))})")
        print(f"        {f['path']}")
    try:
        typed = input("\nType the number of the save to check (Enter = the newest career), or paste a path: ").strip().strip('"')
    except EOFError:
        return ""
    if typed.isdigit() and 1 <= int(typed) <= len(saves):
        return saves[int(typed) - 1]["path"]
    if typed:
        return typed
    return next((f["path"] for f in saves if f["kind"] == "career"), "")


def judge(kind, counts):
    """What the save holds of the tables the tabs need: a list of dicts {table, what, tab, status ("ok" | "empty" | "missing"), rows, healthy, why} for a career, or for a profile. Other kinds: []."""
    out = []
    if kind == "career":
        for code, what, tab, healthy, why in CAREER_TABLES:
            n = counts.get(code)
            out.append({"table": code, "what": what, "tab": tab, "status": "missing" if n is None else "empty" if n == 0 else "ok", "rows": n or 0, "healthy": healthy, "why": why})
    elif kind == "profile":
        for code, what, tab in PROFILE_TABLES:
            n = counts.get(code)
            out.append({"table": code, "what": what, "tab": tab, "status": "missing" if n is None else "empty" if n == 0 else "ok", "rows": n or 0, "healthy": None, "why": ""})
    return out


def verdict(kind, rows):
    """The conclusion in a few sentences."""
    if kind == "career":
        bad = {r["table"]: r for r in rows if r["status"] != "ok"}
        gone_picks = "DRPK" in bad
        gone_books = [t for t in PLAYBOOK_TABLES if t in bad]
        lines = []
        if not bad:
            return ["Everything the Draft Picks and Playbooks tabs need is in this save."]
        if gone_picks:
            lines.append(f"Draft Picks: this save's DRPK table is {bad['DRPK']['status'].upper()}, so the Draft Picks tab has nothing to show. The editor is showing the save truthfully.")
        if gone_books:
            lines.append("Playbooks: this save's " + ", ".join(f"{t} ({bad[t]['status']})" for t in gone_books) + " cannot give the Playbooks tab any playbook to list. "
                         "(The Play creator reads the game's own files, not the save, so it can still show every book.)")
        why = {r["table"]: r["why"] for r in rows}
        others = [t for t in bad if t != "DRPK" and t not in PLAYBOOK_TABLES]
        if others:
            lines.append("Also not filled: " + "; ".join(f"{t} ({bad[t]['status']}): {why[t]}" for t in others))
        lines.append("The save, not the editor, lacks them. Send this report (check_save_report.txt) to whoever looks after the game, with how the career was made (a new career, a roster import, a copied save).")
        return lines
    if kind == "profile":
        filled = [r["table"] for r in rows if r["status"] == "ok"]
        return ["This is a profile save (the player's settings and the plays made in the game's own play editor). "
                + (f"Custom play tables with rows: {', '.join(filled)}." if filled else "None of its custom play tables has rows: no play was made in the game's own editor.")]
    return ["This is neither a career nor a profile save (a roster save, or a file that is not a Head Coach 09 save), so the Draft Picks and Playbooks tabs do not apply."]


def describe_save(path):
    """The facts of a save file for the top of the report."""
    kind, n = D.classify_save(path)
    try:
        st = os.stat(path)
        size, when = st.st_size, time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
    except OSError:
        size, when = 0, "?"
    origin = "Xbox 360 save (the MC02 container Xenia and the PC versions use)" if D.is_xbox_save(path) else "PS3 save (a bare database)"
    root = D.recomp_install_of(path)
    if root:
        origin += ", in a recompiled PC install" + (" (HC27: today's rosters)" if "userdata-hc27" in path.lower().replace("/", "\\") else "")
    return kind, n, [f"Save:   {path}", f"Kind:   {kind} ({n} tables)" if n is not None else f"Kind:   {kind} (no database found in this file)", f"Origin: {origin}", f"Size:   {size:,} bytes, changed {when}"]


def report(path, node=None):
    """The report for ONE save file: (text lines, full table list lines)."""
    kind, n, head = describe_save(path)
    lines = list(head)
    if n is None:
        lines += ["", "This file holds no Head Coach 09 database (a damaged save, a header or thumbnail, or another game's file)."]
        return lines, []
    counts = table_counts(path, node)
    rows = judge(kind, counts)
    lines.append("")
    if rows:
        lines.append(f"  {'Table':<6}{'Holds':<38}{'Tab':<13}{'Rows':>8}   {'Healthy':>8}   Status")
        for r in rows:
            healthy = f"{r['healthy']:,}" if r["healthy"] else ""
            shown = f"{r['rows']:,}" if r["status"] != "missing" else "-"
            mark = {"ok": "ok", "empty": "<-- EMPTY" if kind == "career" else "no rows", "missing": "<-- MISSING (the save has no such table)"}[r["status"]]
            lines.append(f"  {r['table']:<6}{r['what']:<38}{r['tab']:<13}{shown:>8}   {healthy:>8}   {mark}")
        lines.append("")
    if kind == "career":
        lines += ["  (Healthy: the rows in one healthy career made by the Xbox game, for comparison.)", ""]
    lines += verdict(kind, rows)
    if kind == "career" and all(counts.get(name, 0) > 0 for name in PLAYBOOK_TABLES):
        try:
            lines += [""]
            lines += playbook_link_diagnostics(path, counts, node)
        except CheckError as e:
            lines += ["", f"Playbook link check skipped: {e}"]
    if kind == "profile" and counts.get("PBPL", 0) > 0:
        try:
            lines += [""]
            lines += custom_play_diagnostics(path, counts, node)
        except CheckError as e:
            lines += ["", f"Custom play check skipped: {e}"]
    full = [f"  {name:<8}{rows_:>9,}" for name, rows_ in counts.items()]
    return lines, [f"All {len(counts)} tables of {path}:"] + full


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")           # a path with letters the console cannot show must not stop the report
        except (AttributeError, ValueError):
            pass
    args = [a for a in argv[1:] if not a.startswith("--")]
    write_file = "--no-file" not in argv
    if not args:
        picked = choose_save()
        args = [picked] if picked else []
    if not args:
        return 2
    out, full, empty = [], [], 0                         # empty: how many of the given paths had nothing to check (the exit code says so)
    for given in args:
        saves = saves_in(given)
        if not saves:
            out += [f"Nothing to check at {given}: it is not a file or a folder with a save in it.", ""]
            empty += 1
            continue
        extra = saves[MAX_SAVES:]
        checked = skipped = 0
        for path in saves[:MAX_SAVES]:
            kind, _n = D.classify_save(path)
            if kind == "other" and (len(saves) > 1 or os.path.isdir(given)):         # in a folder, a file that is not a save is skipped (a lone one too); a file given by name is reported on
                skipped += 1
                continue                               # a folder: skip the files that are not saves (headers, thumbnails) without a word, unless nothing in it is a save (below)
            try:
                lines, table_list = report(path)
            except CheckError as e:
                lines, table_list = [f"Save:   {path}", "", str(e)], []
            out += lines + ["", "-" * 100, ""]
            full += table_list + [""]
            checked += 1
        if skipped and not checked:
            out += [f"Nothing to check at {given}: {skipped} file(s) of a useful size were looked at and none is a career or profile save (they may be roster saves, headers or files of another game). "
                    "Give the save itself, or the folder it is in.", ""]
            empty += 1
        if extra:
            out += [f"{len(extra)} more file(s) in {given} were not checked (the {MAX_SAVES} newest were).", ""]
    text = "\n".join(out).rstrip() + "\n"
    print(text)
    if write_file and out:
        target = os.path.join(HERE, REPORT_NAME)
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(text + "\n" + "\n".join(full) + "\n")
        except OSError:
            target = os.path.join(tempfile.gettempdir(), REPORT_NAME)
            try:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(text + "\n" + "\n".join(full) + "\n")
            except OSError:
                target = ""
        if target:
            print(f"The same report, with every table of the save listed, is in {target}")
    return 1 if empty else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
