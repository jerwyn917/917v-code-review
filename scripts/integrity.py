#!/usr/bin/env python3
"""Prove a review did not modify the reviewed repository.

  integrity.py snapshot <repo-root> -o baseline.json
  integrity.py verify   <repo-root> baseline.json

The snapshot hashes every file of the repository (honouring .gitignore). Reports
are written outside the repository, so nothing is excluded: `verify` exits 1 and
lists the paths if any file was added, changed or deleted, or HEAD moved.
"""

import argparse
import datetime
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import check_output_path, dump_json, git, is_git_repo, iter_repo_files, load_json  # noqa: E402


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root):
    root = os.path.abspath(root)
    hashes = {rel: _sha(os.path.join(root, rel)) for rel in iter_repo_files(root, exclude_prefixes=())}
    head = None
    if is_git_repo(root):
        try:
            head = git(root, "rev-parse", "HEAD").strip()
        except RuntimeError:
            pass
    return {
        "root": root,
        "taken_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "git_head": head,
        "excluded": None,
        "file_count": len(hashes),
        "files": hashes,
    }


def verify(root, baseline):
    now = snapshot(root)
    before, after = baseline["files"], now["files"]
    added = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(p for p in set(before) & set(after) if before[p] != after[p])
    head_changed = baseline.get("git_head") != now.get("git_head")
    ok = not (added or deleted or modified or head_changed)
    return {
        "unchanged": ok,
        "files_checked": now["file_count"],
        "excluded": now["excluded"],
        "git_head_changed": head_changed,
        "added": added, "modified": modified, "deleted": deleted,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("root")
    s.add_argument("-o", "--output", default="-")
    v = sub.add_parser("verify")
    v.add_argument("root")
    v.add_argument("baseline")
    v.add_argument("-o", "--output", default="-")
    a = ap.parse_args()
    check_output_path(a.root, a.output)
    if a.cmd == "snapshot":
        dump_json(snapshot(a.root), a.output)
        return 0
    result = verify(a.root, load_json(a.baseline))
    dump_json(result, a.output)
    return 0 if result["unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
