#!/usr/bin/env python3
"""Trace security findings back to the commits that put the cited code there.

For every security finding (category Security, security_relevant, or carrying a CWE / OWASP
reference) whose cited lines are tracked by Git, this adds a `git` object to the finding:

  "git": {
    "status": "traced",
    "lines": "23-25",                         the cited lines that were traced
    "introduced":   {commit, short, author, committer, date, summary},
    "last_changed": {commit, short, author, committer, date, summary},
    "same": false,                            true when one commit is both
    "changes": 3                              commits in the history of the first cited line
  }

- last_changed: the most recent commit that changed any of the cited lines (git blame -w).
- introduced:   the oldest commit in the history of the first cited line (git log -L), that is,
                the commit where that code first appeared. A later commit may have made it
                vulnerable, which is why both are reported when they differ.

Other statuses: "uncommitted" (the cited line is a working-tree change that is not committed yet)
and "untraced" with a "reason". Nothing is guessed: without Git history there is no `git` object
and the summary says why.

Read-only: only `git rev-parse`, `git blame` and `git log` run, through the allowlisted helper
with GIT_OPTIONAL_LOCKS=0. Standard library only.

Usage (standalone, to add history to an existing findings.json):
  git-history.py --root <repo> --findings findings.json [-o findings.json]
"""

import argparse
import datetime
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import check_output_path, dump_json, git, is_git_repo, load_json, redact  # noqa: E402

MAX_LINES = 8            # cited lines blamed per finding
CALL_TIMEOUT = 20        # seconds per git call
BUDGET_SECONDS = 120     # total time for one review; later findings are reported as untraced
ZERO = "0" * 40
SEP, REC = "\x1f", "\x1e"


def is_security(f):
    return bool(f.get("category") == "Security" or f.get("security_relevant") or f.get("cwe") or f.get("owasp")
                or "Security" in (f.get("also_categorised_as") or []))


def _date(epoch, tz):
    """Commit date in the committer's own timezone, YYYY-MM-DD."""
    try:
        sign = -1 if tz.startswith("-") else 1
        offset = datetime.timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sign
        return (datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc) + offset).strftime("%Y-%m-%d")
    except (ValueError, IndexError, OverflowError, OSError):
        return None


def _commit(sha, author, committer, date, summary):
    return {"commit": sha, "short": sha[:8], "author": author or None, "committer": committer or None,
            "date": date, "summary": redact(summary or "")[:140]}


def blame(root, path, lo, hi):
    """git blame --porcelain for lines lo..hi of the working-tree file: one entry per line."""
    out = git(root, "blame", "-w", "--porcelain", "-L", "%d,%d" % (lo, hi), "--", path, timeout=CALL_TIMEOUT)
    commits, lines, cur = {}, [], None
    for raw in out.split("\n"):
        m = re.match(r"^([0-9a-f]{40}) (\d+) (\d+)", raw)
        if m and not raw.startswith("\t"):
            cur = commits.setdefault(m.group(1), {"sha": m.group(1)})
            lines.append({"sha": m.group(1), "orig_line": int(m.group(2)), "line": int(m.group(3))})
        elif cur is not None and not raw.startswith("\t") and " " in raw:
            key, value = raw.split(" ", 1)
            cur[key] = value
        elif cur is not None and raw == "boundary":
            cur["boundary"] = True
    for entry in lines:
        entry["info"] = commits[entry["sha"]]
    return lines


def first_commit(root, sha, path, line):
    """Oldest commit in the history of one line, followed back from commit `sha` (git log -L)."""
    fmt = "--format=" + REC + SEP.join(["%H", "%aN", "%cN", "%cd", "%s"])
    out = git(root, "log", "-s", "--date=format:%Y-%m-%d", fmt, "-L%d,%d:%s" % (line, line, path), sha,
              timeout=CALL_TIMEOUT)
    entries = [l[1:].split(SEP) for l in out.split("\n") if l.startswith(REC)]
    entries = [e for e in entries if len(e) == 5]
    return (_commit(*entries[-1]), len(entries)) if entries else (None, 0)


def trace(root, f, shallow):
    if f.get("evidence_type") == "absence":
        return {"status": "untraced", "reason": "the finding is about something that is missing, so there is no "
                                                "line of code to trace"}
    path, lo = f.get("file"), f.get("line")
    if not path or not isinstance(lo, int) or lo < 1:
        return {"status": "untraced", "reason": "the finding has no file and line to trace"}
    hi = f.get("end_line") if isinstance(f.get("end_line"), int) and f["end_line"] >= lo else lo
    hi = min(hi, lo + MAX_LINES - 1)
    try:
        lines = blame(root, path, lo, hi)
    except Exception as e:                                  # untracked file, binary, line out of range, timeout
        msg = str(e)
        reason = "the file is not tracked by Git" if "no such path" in msg or "not tracked" in msg.lower() else \
            "git blame could not read these lines"
        return {"status": "untraced", "reason": reason}
    if not lines:
        return {"status": "untraced", "reason": "git blame returned nothing for these lines"}
    first = lines[0]
    span = "%d" % lo if hi == lo else "%d-%d" % (lo, hi)
    if first["sha"] == ZERO:
        return {"status": "uncommitted", "lines": span,
                "reason": "the cited line is a working-tree change that has not been committed yet"}

    def info(entry):
        c = entry["info"]
        return _commit(entry["sha"], c.get("author"), c.get("committer"),
                       _date(c.get("committer-time"), c.get("committer-tz", "+0000")), c.get("summary"))
    committed = [e for e in lines if e["sha"] != ZERO]
    newest = max(committed, key=lambda e: int(e["info"].get("committer-time", 0)))
    out = {"status": "traced", "lines": span, "last_changed": info(newest)}
    try:
        introduced, changes = first_commit(root, first["sha"], first["info"].get("filename") or path,
                                           first["orig_line"])
    except Exception:
        introduced, changes = None, 0
    if changes:
        out["changes"] = changes
    out["introduced"] = introduced or info(first)
    if not introduced:
        out["note"] = "the line's earlier history could not be followed; the introducing commit shown is the one " \
                      "git blame reports"
    out["same"] = out["introduced"]["commit"] == out["last_changed"]["commit"]
    notes = []
    if len(committed) < len(lines):
        notes.append("some of the cited lines also have uncommitted changes")
    if shallow:
        notes.append("the clone is shallow, so the code may have been introduced earlier than Git can show here")
    if notes:
        out["note"] = "; ".join(([out["note"]] if out.get("note") else []) + notes)
    return out


def attribute(root, findings):
    """Add `git` to each security finding in place; return a summary for findings.json."""
    targets = [f for f in findings if is_security(f)]
    summary = {"available": False, "security_findings": len(targets), "traced": 0, "uncommitted": 0, "untraced": 0}
    if not is_git_repo(root):
        summary["reason"] = "the reviewed folder is not a Git repository"
        return summary
    try:
        git(root, "rev-parse", "--verify", "--quiet", "HEAD", timeout=CALL_TIMEOUT)
    except Exception:
        summary["reason"] = "the repository has no commits yet"
        return summary
    try:
        shallow = git(root, "rev-parse", "--is-shallow-repository", timeout=CALL_TIMEOUT).strip() == "true"
    except Exception:
        shallow = False
    summary.update(available=True, shallow=shallow)
    started = time.time()
    for f in targets:
        if time.time() - started > BUDGET_SECONDS:
            f["git"] = {"status": "untraced", "reason": "the time budget for reading Git history was used up"}
        else:
            f["git"] = trace(root, f, shallow)
        summary[f["git"]["status"]] += 1
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True)
    ap.add_argument("--findings", required=True, help="findings.json from validate-findings.py")
    ap.add_argument("-o", "--output", help="where to write the result (default: the --findings file)")
    a = ap.parse_args()
    out = a.output or a.findings
    check_output_path(a.root, out)
    data = load_json(a.findings)
    data["git_attribution"] = attribute(os.path.abspath(a.root), data.get("findings") or [])
    dump_json(data, out)
    dump_json(data["git_attribution"])


if __name__ == "__main__":
    main()
