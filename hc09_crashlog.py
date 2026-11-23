"""
Problem reports for the HC09 editor: when the editor breaks, a text file says where, so that it can be sent back and read.

Standard library only (no Tk). install() hooks the three places an error can escape from (the main thread, other threads, and the Tk window's own callbacks are hooked by the GUI) and the
interpreter's fault handler (a crash of Python itself); write_report() builds the file. The report is made without the save's data: the error and where it happened, the versions, the kind of save that
is open (its kind and number of tables, never its rows), the last actions and bridge failures, and what the editor wrote lately to the game files and saves (the write log, which is also kept between
runs because a crash of the GAME is usually about those writes). The user's home folder and user name are blanked out. Error messages, window titles and the person's own note can still quote a name (a
player, a file), so the report says to read it before sending. Nothing is ever sent anywhere: the file is read and sent by a person.

    note("window opened: Rename in playbooks")      what the person did (a ring of the last 80)
    bridge_failed(args, message)                    a bridge command that failed, with the reason
    log_write(text)                                 something written to the game files or a save
    write_report(exc_info=None, where="", note="")  the file; returns its path
"""
import collections
import datetime
import faulthandler
import getpass
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)         # the editor runs under pythonw: a console program started without this opens a black window (0 off Windows)

REPORT_DIR_NAME = "crash-reports"
WRITE_LOG_NAME = "write_log.txt"
FAULT_NAME = "fault.txt"
KEEP_REPORTS = 30                        # the oldest reports beyond this many are deleted
WRITE_COMMANDS = {"import", "entry-patch", "add-play", "add-play-restore", "entry-grow", "entry-relocate"}      # bridge commands that write a file
MAX_CONFIG_BYTES = 2_000_000             # an entry-patch config larger than this is not read just to count its edits
# the limits tests change; uninstall() puts them back
_DEFAULTS = {"REPEAT_AFTER": 600, "MAX_REPORTS_PER_MINUTE": 3, "WRITE_LOG_MAX": 256 * 1024}
REPEAT_AFTER = _DEFAULTS["REPEAT_AFTER"]                    # the same error is written again only after this many seconds
MAX_REPORTS_PER_MINUTE = _DEFAULTS["MAX_REPORTS_PER_MINUTE"]
WRITE_LOG_MAX = _DEFAULTS["WRITE_LOG_MAX"]                  # the write log is cut to its newer half when it grows past this

_crumbs = collections.deque(maxlen=80)
_bridge_fails = collections.deque(maxlen=6)
_writes = collections.deque(maxlen=120)      # this run's writes, kept in memory as well (the file may not be there: tests, a read-only folder)
_state = {"dir": None, "root": None, "context": None, "notify": None, "fault": None, "stamps": [], "seen": {}, "previous": None, "hooks": None,
          "snapshot": None, "versions": None, "versions_thread": None}
_lock = threading.Lock()
_log_lock = threading.Lock()                 # the write log file: appending and cutting it are one step


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
# what is blanked out
def redact(text):
    """The user's home folder blanked out, and the user name where it stands as a folder in a path, so that a report can be sent without saying whose computer it came from. (A bare word that happens to be
    the user name, like User or Admin, is left alone: that would rewrite ordinary words.)"""
    text = text or ""
    try:
        home = os.path.expanduser("~")
    except Exception:
        home = ""
    if home and home != "~":
        for variant in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
            text = re.sub(re.escape(variant), "<home>", text, flags=re.I)
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    if user and len(user) >= 3:
        name = re.escape(user)
        text = re.sub(r"""(?:(?<=[\\/])""" + name + r"""(?=[\\/\s'"<>:,;)]|$))|(?:(?<![A-Za-z0-9_])""" + name + r"""(?=[\\/]))""", "<user>", text, flags=re.I)         # a folder of a path: after or before a separator
    return text


def shorten(path, keep=2):
    """The last `keep` parts of a path (a save's folder and file), for a report that should not carry whole paths."""
    parts = [p for p in re.split(r"[\\/]+", str(path or "")) if p]
    return "/".join(parts[-keep:])


# What a whole path looks like in free text. One commented alternative per case; shorten_paths() cuts each to its last two parts.
_START = r"""(?:
      (?<![A-Za-z0-9])[A-Za-z]:[\\/]       # a drive: C:\ or C:/ (not the 's:/' at the end of https:)
    | \\\\                                  # a network share: \\server\share
    | <home>[\\/]+                          # the home folder, when redact() already blanked it out
    | (?<![\w:./\\-])/(?=[\w.-]+/)          # a posix path: /dir/x (not after a word, a colon or a slash, so not the // of a URL)
)"""
_WORD = r"""[^\s\\/'"<>|*?:,;]+"""             # one word of a folder name: a separator, colon, comma or semicolon ends a path in a sentence
_QUOTED = re.compile(r"""(?x)
    (['"])                                  # an OSError names its file in quotes: the path is everything up to the same quote again
    ( """ + _START + r""" (?:(?!\1).)* )
    (?=\1)
""")
_PLAIN = re.compile(r"""(?x) """ + _START + r"""
    (?: """ + _WORD + r"""(?:[ ]""" + _WORD + r"""){0,9} [\\/]+ )*     # folders: up to ten words each ("Shared Saves", "My Saves 2", "this is a very long folder")
    [^\s'"<>|*?:\\/]*                                                  # the file name: it ends at a space
""")


def shorten_paths(text, keep=2):
    """The text with every whole path in it cut to its last `keep` parts: a quoted path whole (spaces and apostrophes included), any other up to the end of its file name."""
    text = _QUOTED.sub(lambda m: m.group(1) + (shorten(m.group(2), keep) or m.group(2)), str(text or ""))
    return _PLAIN.sub(lambda m: shorten(m.group(0), keep) or m.group(0), text)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
# what is kept while the editor runs
def note(text):
    """One thing the person did or the editor did (a tab, a window, a bridge command): the last 80 are in a report."""
    with _lock:
        _crumbs.append((time.time(), str(text)[:300]))


def bridge_failed(args, message, summary=None):
    """A bridge command that failed, with the reason (the bridge's own words, the first lines). summary: the line summarize_bridge() made for it, when the caller has it."""
    lines = [shorten_paths(ln) for ln in str(message or "").splitlines() if ln.strip()]          # the bridge's own words, with whole paths cut to their last two parts
    summary = summary or summarize_bridge(args)[1]
    with _lock:
        _bridge_fails.append((time.time(), summary, "\n".join(lines[:12])))
    note("bridge FAILED: " + summary)


def summarize_bridge(args):
    """(writes?, a line for the report) for a bridge command line: the command, its mode and the tables or entries it names, never a whole path."""
    args = [str(a) for a in (args or [])]
    if not args:
        return False, "(no command)"
    cmd = args[0]
    parts = [cmd]
    mode = args[1] if len(args) > 1 and not args[1].startswith("--") else ""
    if mode:
        parts.append(mode)
    writes = cmd in WRITE_COMMANDS and not (cmd == "entry-patch" and mode == "dry")         # entry-patch dry only checks
    opts = {}
    for i, a in enumerate(args):
        if a.startswith("--") and i + 1 < len(args) and not args[i + 1].startswith("--"):
            opts[a[2:]] = args[i + 1]
    for key in ("tables", "table", "index", "top-index"):
        if key in opts:
            parts.append(f"{key}={opts[key][:80]}")
    for key in ("db", "ast", "in", "out", "out-dir"):
        if key in opts:
            parts.append(f"{key}={shorten(opts[key])}")
    if writes and cmd == "entry-patch" and "config" in opts:             # the edits per entry, for a write only (a config can hold thousands of edits)
        try:
            size = os.path.getsize(opts["config"])
            if size > MAX_CONFIG_BYTES:
                parts.append(f"[config {size:,} bytes, not read]")
            else:
                with open(opts["config"], encoding="utf-8") as f:
                    cfg = json.load(f)
                for t in cfg.get("targets", [])[:6]:
                    edits = t.get("edits", [])
                    tables = sorted({e.get("table", "?") for e in edits})
                    parts.append(f"[{os.path.basename(str(t.get('ast', '')))} #{t.get('index')}: {len(edits)} edit(s)" + (f" in {','.join(tables)}" if tables else "") + "]")
        except Exception:
            parts.append("[config not readable]")
    return writes, " ".join(parts)


def previous_report():
    """The report that was written when the editor was last found to have closed without warning (the path), or None."""
    return _state.get("previous")


def log_playbook_rows(action, tables):
    """Log only the playbook link rows changed by a validated editor operation (IDs only, never player data)."""
    columns = {
        "PGFM": ("BOKL", "PBFM", "SRFM"),
        "PGSS": ("BOKL", "SETL"),
        "PGSL": ("BOKL", "SETL", "PBFM"),
        "PGPL": ("BOKL", "SETL", "PLYL", "PLTP"),
    }
    total = 0
    limit = 500
    for table in ("PGFM", "PGSS", "PGSL", "PGPL"):
        keys = columns[table]
        for row in (tables or {}).get(table, []):
            if total >= limit:
                log_write(f"playbook {action}: audit row limit {limit} reached; remaining rows omitted")
                return
            values = ([row.get(key, "") for key in keys] if isinstance(row, dict) else list(row))
            detail = " ".join(f"{key}={str(value)[:32]}" for key, value in zip(keys, values))
            log_write(f"playbook {action} {table} {detail}")
            total += 1


def log_write(text):
    """Something the editor wrote to the game files or to a save (and how it went): kept in memory and, once install() has run, in the write log file next to the reports."""
    text = " ".join(str(text).split())                       # one line per record, whatever the text holds (an error message with line breaks)
    text = shorten_paths(text)                               # first, while the drive and folders are still there to be recognized: every whole path (an error message names its files) is cut to its last two parts
    line = redact(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {text[:400]}")          # the file is private to this computer, but it is also read into reports: then the home folder and user name are blanked out wherever they are left
    with _lock:
        _writes.append(line)
        folder = _state["dir"]
    if not folder:
        return
    path = os.path.join(folder, WRITE_LOG_NAME)
    with _log_lock:                                           # appending and cutting the file are one step: two threads cannot lose each other's lines
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if os.path.getsize(path) > WRITE_LOG_MAX:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    data = f.read()
                half = data[len(data) // 2:].split("\n", 1)[-1]
                with open(path + ".tmp", "w", encoding="utf-8") as f:
                    f.write(half)
                os.replace(path + ".tmp", path)               # the new file replaces the old in one step
        except OSError:
            pass


def recent_writes(limit=60):
    """The write log: the file's last lines (earlier runs included) when there is one, else this run's writes."""
    folder = _state["dir"]
    if folder:
        try:
            with open(os.path.join(folder, WRITE_LOG_NAME), "r", encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()[-limit:]
        except OSError:
            pass
    with _lock:
        return list(_writes)[-limit:]


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
# where the reports go
def report_dir():
    return _state["dir"]


def _writable_dir(candidates):
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".probe")
            with open(probe, "w") as f:
                f.write("x")
            os.remove(probe)
            return d
        except OSError:
            continue
    return None


def install(root, context=None, notify=None, folder=None):
    """Hook the main thread, the other threads and the interpreter's fault handler, and choose the folder (crash-reports next to the editor, else a folder in Temp). context: a function that returns a
    dict about what is open (the GUI gives it); notify: a function called with (report path or None when none could be saved, short text) after an error was handled (the GUI shows its box). A crash of
    Python itself in the LAST run (what the fault handler wrote) becomes a report now. Returns the folder, or None when no folder can be written (the reports are then only shown, not kept).
    Called a second time it only takes the new context and notify."""
    if _state["hooks"] is not None:
        attach(context, notify)
        return _state["dir"]
    _state["root"], _state["context"], _state["notify"] = root, context, notify
    _state["hooks"] = (sys.excepthook, threading.excepthook)
    _state["dir"] = _writable_dir([folder] if folder else [os.path.join(root, REPORT_DIR_NAME), os.path.join(tempfile.gettempdir(), "hc09-editor-reports")])
    sys.excepthook = _excepthook
    threading.excepthook = _threading_hook
    previous = _read_previous_fault()
    if previous:
        path = write_report(where="The editor closed without warning the last time it ran (a crash of Python or of a library it uses)", fault_text=previous)
        if path:
            _state["previous"] = path
            _clear_fault()                                        # only now: if the report could not be written the trace stays for the next start
    if _state["dir"]:
        try:
            _state["fault"] = open(os.path.join(_state["dir"], FAULT_NAME), "a", buffering=1)      # sys.stderr is None under pythonw: the fault handler needs a file of its own
            faulthandler.enable(file=_state["fault"], all_threads=True)
        except (OSError, RuntimeError, ValueError):
            _state["fault"] = None
    t = threading.Thread(target=_load_versions, args=(root,), name="crashlog-versions", daemon=True)      # node and the file hashes: read once, in the background, not in the middle of an error
    _state["versions_thread"] = t
    t.start()
    note("editor started")
    return _state["dir"]


def attach(context=None, notify=None):
    """Give the GUI's two functions after the window exists (install() runs earlier, so that an error while the window is being built is reported too)."""
    if context is not None:
        _state["context"] = context
    if notify is not None:
        _state["notify"] = notify


def uninstall():
    """Put the interpreter's hooks and the limits back and close the fault file (for tests; the editor never calls it)."""
    reading = _state["versions_thread"]
    if reading is not None:
        reading.join(timeout=6)                               # its answer belongs to this run, not the next
    hooks = _state["hooks"]
    if hooks:
        sys.excepthook, threading.excepthook = hooks
    try:
        faulthandler.disable()
    except Exception:
        pass
    if _state["fault"]:
        try:
            _state["fault"].close()
        except OSError:
            pass
    _state.update({"dir": None, "root": None, "context": None, "notify": None, "fault": None, "stamps": [], "seen": {}, "previous": None, "hooks": None,
                   "snapshot": None, "versions": None, "versions_thread": None})
    globals().update(_DEFAULTS)
    with _lock:
        _crumbs.clear()
        _bridge_fails.clear()
        _writes.clear()


def _read_previous_fault():
    folder = _state["dir"]
    if not folder:
        return ""
    try:
        with open(os.path.join(folder, FAULT_NAME), "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _clear_fault():
    try:
        open(os.path.join(_state["dir"], FAULT_NAME), "w").close()
    except OSError:
        pass


def _chain(index, *args):
    """Call the hook that was there before ours (the default one prints the traceback) when there is somewhere to print it: a console run shows its errors as it always did."""
    prev = (_state["hooks"] or (None, None))[index]
    if prev is not None and prev not in (_excepthook, _threading_hook) and sys.stderr is not None:
        try:
            prev(*args)
        except Exception:
            pass


def _excepthook(etype, value, tb):
    handle_exception((etype, value, tb), "the main thread")
    _chain(0, etype, value, tb)


def _threading_hook(args):
    handle_exception((args.exc_type, args.exc_value, args.exc_traceback), f"the background thread {getattr(args.thread, 'name', '?')}")
    _chain(1, args)


def handle_exception(exc_info, where):
    """An error nobody caught: write the report (not more than three a minute, and a repeat of the same error is not written again) and tell the GUI (with the path, or None when no report could be
    saved). Never raises."""
    try:
        if exc_info[0] is KeyboardInterrupt:
            return None
        key = _signature(exc_info)
        now = time.time()
        with _lock:
            _state["stamps"] = [t for t in _state["stamps"] if now - t < 60]
            repeat = now - _state["seen"].get(key, -REPEAT_AFTER) < REPEAT_AFTER
            flood = len(_state["stamps"]) >= MAX_REPORTS_PER_MINUTE
            if not repeat and not flood:
                _state["stamps"].append(now)
                _state["seen"][key] = now
        if repeat or flood:
            note(f"error again, no new report: {exc_info[0].__name__}: {exc_info[1]}")
            return None
        path = write_report(exc_info, where)
        if _state["notify"]:
            _state["notify"](path, f"{exc_info[0].__name__}: {exc_info[1]}")
        return path
    except Exception:
        return None


def _signature(exc_info):
    tb = exc_info[2]
    last = traceback.extract_tb(tb)[-1] if tb else None
    return (exc_info[0].__name__, str(exc_info[1])[:120], (os.path.basename(last.filename), last.lineno) if last else None)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
# the report
def _versions(root):
    out = [f"python: {platform.python_version()} ({platform.architecture()[0]}), {platform.system()} {platform.release()} {platform.version()}"]
    try:
        import tkinter
        out.append(f"tk: {tkinter.TkVersion}")
    except Exception:
        out.append("tk: not available")
    try:
        node = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW)
        out.append("node: " + (node.stdout.strip() or node.stderr.strip() or "no answer"))
    except Exception as e:
        out.append(f"node: not found ({type(e).__name__})")
    try:
        import hc09_update as U
        head = U.read_git_head(root)
        if head:
            out.append(f"editor: git clone, branch {head.get('branch')}, commit {head.get('sha')}")
        else:
            out.append("editor: not a git clone (a download)")
        shas = U.local_blob_shas(root, tuple(sorted({"guiHC09.py", "hc09-bridge/bridge.js"} | {f for f in os.listdir(root) if f.startswith("hc09_") and f.endswith(".py")})))
        out.append("files: " + ", ".join(f"{k} {v[:10] if v else 'missing'}" for k, v in shas.items()))
    except Exception as e:
        out.append(f"editor version: not known ({type(e).__name__})")
    return out


def _load_versions(root):
    _state["versions"] = _versions(root)


def _versions_cached():
    """The versions, read once per run (install() starts reading them in the background): a report does not start node or hash the files again."""
    t = _state["versions_thread"]
    if t is not None:
        t.join(timeout=6)
    if _state["versions"] is None:
        _state["versions"] = _versions(_state["root"] or os.getcwd())
    return _state["versions"]


def refresh_context():
    """Take what is open now. The window's widgets may only be read on the thread that owns them, so the GUI calls this on its own thread every few seconds and a report made on that thread takes a fresh
    one; a report made on another thread (an error in a background job) uses the last one taken."""
    fn = _state["context"]
    if not fn:
        return
    try:
        _state["snapshot"] = (time.time(), dict(fn() or {}))
    except Exception as e:
        _state["snapshot"] = (time.time(), {"context": f"could not be read ({type(e).__name__})"})


def build_report(exc_info=None, where="", note_text="", fault_text=""):
    """The text of a report (see the module's description for what it holds and what it never holds)."""
    lines = ["HC09 editor problem report", "=" * 26,
             f"When: {datetime.datetime.now():%Y-%m-%d %H:%M:%S} (this computer's time)",
             f"What: {where or 'a report saved by the person using the editor'}"]
    if note_text:
        lines += ["", "What the person says went wrong:", str(note_text).strip()]
    lines += ["", "This file is made without the save's data (no players, no rows), and your user name and home folder are blanked out. Error messages, window titles and a note can still quote a name "
              "(a player, a file): read it before you send it on.", ""]
    if exc_info and exc_info[0] is not None:
        lines += ["--- The error", "".join(traceback.format_exception(*exc_info)).rstrip(), ""]
    if fault_text:
        lines += ["--- What the fault handler wrote (a crash below Python)", fault_text.strip(), ""]
    lines += ["--- The editor and this computer"] + _versions_cached() + [""]
    on_main = threading.current_thread() is threading.main_thread()
    if on_main:
        refresh_context()
    snap = _state["snapshot"]
    ctx = dict(snap[1]) if snap else {}
    if snap and not on_main:
        ctx["taken"] = f"{int(time.time() - snap[0])} s ago on the window's own thread (this report is from another thread)"
    elif not snap and not on_main and _state["context"]:
        ctx["context"] = "not taken yet (this report is from a background thread)"
    lines += ["--- What was open"] + ([f"{k}: {v}" for k, v in ctx.items()] or ["(nothing known)"]) + [""]
    with _lock:
        fails = list(_bridge_fails)
        crumbs = list(_crumbs)
    if fails:
        lines += ["--- Bridge commands that failed (the last few)"]
        for t, summary, why in fails:
            lines += [f"{datetime.datetime.fromtimestamp(t):%H:%M:%S}  {summary}"] + ["    " + ln for ln in why.splitlines()]
        lines += [""]
    writes = recent_writes()
    lines += ["--- What the editor wrote to the game files and saves lately (oldest first; earlier runs are included)"] + (writes or ["(nothing)"]) + [""]
    lines += ["--- The last things done (oldest first)"]
    lines += [f"{datetime.datetime.fromtimestamp(t):%H:%M:%S}  {text}" for t, text in crumbs] or ["(nothing)"]
    return redact("\n".join(lines) + "\n")


def write_report(exc_info=None, where="", note_text="", fault_text=""):
    """Write a report file and return its path (None when there is nowhere to write it). The oldest reports beyond 30 are deleted."""
    text = build_report(exc_info, where, note_text, fault_text)
    folder = _state["dir"] or _writable_dir([os.path.join(tempfile.gettempdir(), "hc09-editor-reports")])
    if not folder:
        return None
    base = f"report_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    n = 1
    while True:
        path = os.path.join(folder, base + (".txt" if n == 1 else f"_{n}.txt"))
        try:
            with open(path, "x", encoding="utf-8") as f:           # exclusive: a report made in the same second by another thread is never overwritten
                f.write(text)
            break
        except FileExistsError:
            n += 1
        except OSError:
            return None
    try:
        old = sorted(p for p in os.listdir(folder) if p.startswith("report_") and p.endswith(".txt"))
        for p in old[:-KEEP_REPORTS]:
            try:
                os.remove(os.path.join(folder, p))
            except OSError:
                pass
    except OSError:
        pass
    return path
