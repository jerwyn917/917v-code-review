#!/usr/bin/env python3
"""Compute the review scope for a Git diff review (read-only git commands only).

Modes:
  --uncommitted        working tree + index vs HEAD, plus untracked files (default)
  --staged             index vs HEAD
  --branch <base>      merge-base(<base>, HEAD)..HEAD  (what a PR would contain)
  --range <a>..<b>     explicit commit range

Output JSON lists each changed file with its added/modified line ranges in
the new version, so reviewers and the validator know which lines changed.

Usage: diff-scope.py <repo-root> [mode] [-o scope.json]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import OUTPUT_DIR, dump_json, eprint, git, is_git_repo, read_text  # noqa: E402

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_unified(diff_text):
    """Return {path: {"status": str, "ranges": [[start, end], ...]}} for new-side lines."""
    files, current = {}, None
    old_path = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current, old_path = None, None
            continue
        if line.startswith("--- "):
            old_path = None if line[4:] == "/dev/null" else line[6:]
            continue
        if line.startswith("+++ "):
            if line[4:] == "/dev/null":
                current = None  # deletion: nothing to review on the new side
                if old_path:
                    files[old_path] = {"status": "deleted", "ranges": []}
                continue
            current = line[6:] if line[4:6] == "b/" else line[4:]
            files.setdefault(current, {"status": "added" if old_path is None else "modified", "ranges": []})
            continue
        m = HUNK.match(line)
        if m and current:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count > 0:
                files[current]["ranges"].append([start, start + count - 1])
    return files


def merge_ranges(ranges):
    out = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def compute(root, mode, base=None, rng=None):
    root = os.path.abspath(root)
    if not is_git_repo(root):
        raise SystemExit("error: %s is not a Git repository; diff review needs Git" % root)
    head = None
    try:
        head = git(root, "rev-parse", "--verify", "HEAD").strip()
    except RuntimeError:
        pass  # repository without commits yet
    args = ["-c", "core.quotePath=false", "diff", "--no-color", "--no-ext-diff", "-U0", "--find-renames"]
    untracked = []
    if mode == "staged":
        args.append("--cached")
        desc = "staged changes (index vs HEAD)"
    elif mode == "branch":
        try:
            mb = git(root, "merge-base", base, "HEAD").strip()
        except RuntimeError as exc:
            raise SystemExit("error: cannot find merge-base with %r: %s" % (base, exc))
        args.append(mb + "..HEAD")
        desc = "branch changes since merge-base with %s (%s)" % (base, mb[:12])
    elif mode == "range":
        args.append(rng)
        desc = "commit range " + rng
    else:
        if head:
            args.append("HEAD")
        else:
            args.append("--cached")
        desc = "uncommitted changes (staged + unstaged + untracked vs HEAD)"
        untracked = [p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p]
    files = parse_unified(git(root, *args))
    for rel in untracked:
        text = read_text(root, rel)
        n = (text.count("\n") + (0 if text.endswith("\n") else 1)) if text else 0
        files[rel] = {"status": "untracked", "ranges": [[1, n]] if n else []}
    out_prefix = OUTPUT_DIR.replace(os.sep, "/") + "/"
    changed = []
    for rel in sorted(files):
        if rel.startswith(out_prefix):
            continue  # never review the review's own output
        info = files[rel]
        ranges = merge_ranges(info["ranges"])
        changed.append({
            "file": rel, "status": info["status"], "ranges": ranges,
            "changed_lines": sum(e - s + 1 for s, e in ranges),
        })
    return {
        "mode": mode, "description": desc, "head": head, "base": base, "range": rng,
        "files_changed": len(changed),
        "lines_changed": sum(f["changed_lines"] for f in changed),
        "files": changed,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--uncommitted", action="store_true")
    g.add_argument("--staged", action="store_true")
    g.add_argument("--branch", metavar="BASE")
    g.add_argument("--range", metavar="A..B")
    ap.add_argument("-o", "--output", default="-")
    a = ap.parse_args()
    if a.staged:
        scope = compute(a.root, "staged")
    elif a.branch:
        scope = compute(a.root, "branch", base=a.branch)
    elif a.range:
        scope = compute(a.root, "range", rng=a.range)
    else:
        scope = compute(a.root, "uncommitted")
    if not scope["files"]:
        eprint("note: no changed files in scope (%s)" % scope["description"])
    dump_json(scope, a.output)


if __name__ == "__main__":
    main()
