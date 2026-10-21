"""
Update check for the HC09 editor: is the copy you are running behind the main branch on GitHub?

Standard library only, read-only against GitHub's public API, silent when offline. Two ways to tell:

- A git clone (a .git folder next to this file): compare the commit you are on with the main branch (GitHub's compare API).
  Only the main branch is checked, so someone working on a branch never sees a notice. "Update now" can run
  `git pull --ff-only` when that is safe (see can_update_in_place).
- A zip download (no .git folder): compare the git blob hash of this program's files with the ones on main. The hash is
  computed from the file content with line endings as LF (the repository stores LF), so nobody has to remember to bump a
  version number.

check_for_update() never raises; it returns {"status": "update" | "current" | "unknown", ...}.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

REPO = "AndrewLampert/hc09-career-editor"
BRANCH = "main"
API = "https://api.github.com"
PAGE = f"https://github.com/{REPO}"
TRACKED_FILES = ("guiHC09.py", "hc09_update.py", "hc09-bridge/bridge.js", "hc09-bridge/package.json")
# A copy without a git folder is compared file by file: these, and every Python module beside guiHC09.py that the repository has (the editor is
# split into modules such as hc09_plays.py, and a change in any of them is an update).
CHECK_EVERY = 3600          # seconds between checks (the editor remembers the last answer in between)


def blob_sha(data):
    """The git blob hash of file content, line endings taken as LF (how the repository stores them)."""
    data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def tracked_files(remote_paths):
    """The files whose difference means an update: TRACKED_FILES plus the repository's top-level Python modules."""
    modules = {p for p in remote_paths if "/" not in p and p.endswith(".py")}
    return tuple(sorted(modules | set(TRACKED_FILES)))


def local_blob_shas(root, files=TRACKED_FILES):
    out = {}
    for rel in files:
        try:
            with open(os.path.join(root, *rel.split("/")), "rb") as f:
                out[rel] = blob_sha(f.read())
        except OSError:
            out[rel] = None
    return out


# ---------- reading a git clone without needing the git program
def git_dir(root):
    """The .git directory of a clone (or of a worktree, where .git is a file saying where it is), or None."""
    path = os.path.join(root, ".git")
    if os.path.isdir(path):
        return path
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                m = re.match(r"gitdir:\s*(.+)", f.read().strip())
        except OSError:
            return None
        if m:
            target = m.group(1).strip()
            return target if os.path.isabs(target) else os.path.normpath(os.path.join(root, target))
    return None


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def read_git_head(root):
    """{"branch": name or None (detached), "sha": commit or None} of a clone, or None if root is not a git clone."""
    gd = git_dir(root)
    if not gd:
        return None
    head = _read(os.path.join(gd, "HEAD"))
    m = re.match(r"ref:\s*(\S+)", head)
    if not m:
        return {"branch": None, "sha": head if re.fullmatch(r"[0-9a-f]{40}", head) else None}
    ref = m.group(1)
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    # a worktree keeps shared refs in the main git directory
    common = _read(os.path.join(gd, "commondir"))
    bases = [gd] + ([os.path.normpath(os.path.join(gd, common))] if common else [])
    for base in bases:
        sha = _read(os.path.join(base, *ref.split("/")))
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return {"branch": branch, "sha": sha}
        for line in _read(os.path.join(base, "packed-refs")).splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref and re.fullmatch(r"[0-9a-f]{40}", parts[0]):
                return {"branch": branch, "sha": parts[0]}
    return {"branch": branch, "sha": None}


def git_origin_url(root):
    """The url of the clone's origin remote, or ''."""
    gd = git_dir(root)
    if not gd:
        return ""
    common = _read(os.path.join(gd, "commondir"))
    text = _read(os.path.join(gd, "config")) or (_read(os.path.join(os.path.normpath(os.path.join(gd, common)), "config")) if common else "")
    m = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', text, re.S)
    return m.group(1) if m else ""


def is_our_repo(url, repo=REPO):
    return repo.lower() in re.sub(r"/+", "/", url.lower().replace("\\", "/"))


# ---------- GitHub
def default_fetch(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": "hc09-career-editor-update-check", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _titles(commits, limit=8):
    """What changed, newest first: the pull request titles of merge commits, else the commit subjects."""
    merges, plain = [], []
    for c in commits:
        lines = [ln for ln in (c.get("commit", {}).get("message") or "").splitlines()]
        first = lines[0] if lines else ""
        if first.startswith("Merge pull request"):
            body = [ln for ln in lines[1:] if ln.strip()]
            merges.append(body[0].strip() if body else first)
        elif first.strip():
            plain.append(first.strip())
    return list(reversed(merges or plain))[:limit]


def check_for_update(root, fetch=default_fetch, repo=REPO, branch=BRANCH):
    """Is this copy behind the main branch? Never raises."""
    try:
        head = read_git_head(root)
        if head is not None:
            return _check_clone(root, head, fetch, repo, branch)
        return _check_files(root, fetch, repo, branch)
    except Exception as e:                      # offline, rate limited, private repo, anything: say nothing
        return {"status": "unknown", "error": f"{type(e).__name__}: {e}"}


def _check_clone(root, head, fetch, repo, branch):
    if head["branch"] != branch or not head["sha"]:
        return {"status": "current", "why": "not on the main branch"}
    origin = git_origin_url(root)
    if origin and not is_our_repo(origin, repo):
        return {"status": "current", "why": "a clone of another repository"}
    cmp = fetch(f"{API}/repos/{repo}/compare/{head['sha']}...{branch}")
    if cmp.get("status") == "ahead" and int(cmp.get("ahead_by") or 0) > 0:
        commits = cmp.get("commits") or []
        latest = commits[-1]["sha"] if commits else ""
        return {"status": "update", "kind": "git", "latest": latest, "behind": int(cmp["ahead_by"]), "changes": _titles(commits),
                "date": ((commits[-1].get("commit") or {}).get("committer") or {}).get("date", "") if commits else ""}
    return {"status": "current", "why": cmp.get("status", "")}


def _check_files(root, fetch, repo, branch):
    tree = fetch(f"{API}/repos/{repo}/git/trees/{branch}?recursive=1")
    remote = {e["path"]: e["sha"] for e in tree.get("tree", []) if e.get("type") == "blob"}
    tracked = tracked_files(remote)
    local = local_blob_shas(root, tracked)
    differ = [p for p in tracked if local.get(p) is not None and p in remote and local[p] != remote[p]]
    if not differ:
        return {"status": "current", "why": "files match"}
    latest = hashlib.sha1("".join(remote[p] for p in sorted(differ)).encode()).hexdigest()
    info = {"status": "update", "kind": "files", "latest": latest, "behind": None, "files": differ, "changes": [], "date": ""}
    try:
        newest = fetch(f"{API}/repos/{repo}/commits/{branch}")
        info["date"] = ((newest.get("commit") or {}).get("committer") or {}).get("date", "")
        info["changes"] = _titles([newest]) if newest.get("commit") else []
    except Exception:
        pass
    return info


# ---------- updating a clone in place
def _git(root, *args, timeout=120):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=timeout)


def can_update_in_place(root, repo=REPO, branch=BRANCH):
    """(True, "") if "git pull --ff-only" is safe here, else (False, why): a git clone on the main branch of this repository,
    git installed, and no changes of your own in the working tree."""
    head = read_git_head(root)
    if head is None:
        return False, "this copy is not a git clone"
    if head["branch"] != branch:
        return False, f"not on the {branch} branch"
    origin = git_origin_url(root)
    if not origin or not is_our_repo(origin, repo):
        return False, "origin is not the editor's repository"
    if shutil.which("git") is None:
        return False, "git is not installed"
    try:
        status = _git(root, "status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"git failed: {e}"
    if status.returncode != 0:
        return False, "git could not read the folder"
    if status.stdout.strip():
        return False, "you have changed files here; commit or stash them first"
    return True, ""


def pull_update(root, branch=BRANCH):
    """Run git pull --ff-only. Returns {"ok", "output", "old", "new", "changed": [files], "npm": bool (bridge dependencies changed)}."""
    old = (read_git_head(root) or {}).get("sha")
    try:
        res = _git(root, "pull", "--ff-only", "origin", branch)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "output": str(e), "old": old, "new": old, "changed": [], "npm": False}
    new = (read_git_head(root) or {}).get("sha")
    changed = []
    if res.returncode == 0 and old and new and old != new:
        try:
            diff = _git(root, "diff", "--name-only", old, new)
            changed = [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]
        except (OSError, subprocess.SubprocessError):
            pass
    return {"ok": res.returncode == 0, "output": (res.stdout + res.stderr).strip(), "old": old, "new": new, "changed": changed,
            "npm": any(p.startswith("hc09-bridge/package") for p in changed)}
