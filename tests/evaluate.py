#!/usr/bin/env python3
"""Score a finished review of a test fixture.

Checks (hard failures make the exit code 1):
  * all required report files exist
  * every finding has the required fields, a valid severity, a unique ID
  * every finding's file/line/evidence is re-verified against the source
  * no seeded secret value appears anywhere in the report folder
  * no duplicate findings remain (same place, similar title)
  * severity rules hold (Critical => Confirmed; Low confidence => <= Medium)
  * the reviewed copy is byte-identical to the original fixture (nothing excluded: reports live outside it)
Metric (reported, gated only with --min-recall):
  * recall of the seeded issues listed in tests/expected/<fixture>.json

Usage: evaluate.py --repo <reviewed copy> --expected tests/expected/X.json [--original tests/fixtures/X]
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
from _common import SEVERITIES, SEVERITY_RANK, default_output_dir, iter_repo_files  # noqa: E402

spec = importlib.util.spec_from_file_location("validate_findings", os.path.join(SCRIPTS, "validate-findings.py"))
vf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vf)

REPORTS = ["executive-summary.md", "detailed-findings.md", "security-review.md", "architecture-review.md",
           "recommendations.md", "findings.json"]


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def anchor_line(repo, rel, pattern):
    if not pattern:
        return None
    with open(os.path.join(repo, rel), encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if pattern in line:
                return i
    return None


def matches(seed, findings, repo):
    window = seed.get("window", 3)
    files = [seed["file"]] + seed.get("alt_files", [])
    for f in findings:
        cats = {f["category"]} | set(f.get("also_categorised_as") or [])
        if not cats & set(seed["categories"]):
            continue
        locs = [(f["file"], f["line"], f.get("end_line", f["line"]))] + [
            (l["file"], int(l["line"]), int(l["line"])) for l in f.get("related_locations") or []]
        for file, start, end in locs:
            if file not in files:
                continue
            if file != seed["file"] or not seed.get("pattern"):
                return f["id"]  # alt file or whole-file seed: same file is enough
            a = anchor_line(repo, file, seed["pattern"])
            if a is None:
                return f["id"]
            if start - window <= a <= end + window:
                return f["id"]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", help="report folder (default: the review's default folder outside the repo)")
    ap.add_argument("--expected", required=True)
    ap.add_argument("--original")
    ap.add_argument("--min-recall", type=float, default=0.0)
    ap.add_argument("--diff", action="store_true", help="diff review: skip recall, check in_changed_lines flags")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    out_dir = os.path.abspath(a.out) if a.out else default_output_dir(repo)
    exp = json.load(open(a.expected))
    failures, result = [], {"fixture": exp["fixture"], "repo": repo}

    missing = [r for r in REPORTS if not os.path.isfile(os.path.join(out_dir, r))]
    if missing:
        failures.append("missing report files: " + ", ".join(missing))
    result["dashboard"] = os.path.isfile(os.path.join(out_dir, "dashboard.html"))
    if "findings.json" in missing:
        result["failures"] = failures
        print(json.dumps(result, indent=2))
        return 1
    data = json.load(open(os.path.join(out_dir, "findings.json")))
    findings = data["findings"]

    ids = [f.get("id") for f in findings]
    if len(ids) != len(set(ids)):
        failures.append("duplicate finding IDs")
    bad_loc = []
    for f in findings:
        miss = [k for k in vf.REQUIRED + ["id", "status"] if f.get(k) in (None, "")]
        if miss:
            failures.append("%s missing fields %s" % (f.get("id"), miss))
        if f.get("severity") not in SEVERITIES:
            failures.append("%s invalid severity" % f.get("id"))
        if f["severity"] == "Critical" and f["status"] != "Confirmed":
            failures.append("%s Critical but not Confirmed" % f["id"])
        if f["confidence"] == "Low" and SEVERITY_RANK[f["severity"]] < SEVERITY_RANK["Medium"]:
            failures.append("%s Low confidence above Medium" % f["id"])
        g = dict(f)
        ok, reason, _ = vf.verify_location(repo, g)
        if not ok or g["line"] != f["line"]:
            bad_loc.append("%s: %s" % (f["id"], reason or "line drift %s->%s" % (f["line"], g["line"])))
    if bad_loc:
        failures.append("unverifiable locations: " + "; ".join(bad_loc))
    result["locations_verified"] = len(findings) - len(bad_loc)

    leaks = []
    for dirpath, _, names in os.walk(out_dir):
        for n in names:
            p = os.path.join(dirpath, n)
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for s in exp.get("secrets", []):
                if s in text:
                    leaks.append(os.path.relpath(p, repo))
    if leaks:
        failures.append("secret values leaked into: " + ", ".join(sorted(set(leaks))))
    result["secret_leaks"] = sorted(set(leaks))

    dups = []
    for i, f in enumerate(findings):
        for g in findings[i + 1:]:
            if vf._overlap(f, g) and vf._jaccard(f["title"], g["title"]) >= 0.5:
                dups.append("%s~%s" % (f["id"], g["id"]))
    if dups:
        failures.append("unmerged duplicates: " + ", ".join(dups))
    result["validation"] = data.get("validation")

    if a.original:
        orig = os.path.abspath(a.original)
        before = {r: sha(os.path.join(orig, r)) for r in iter_repo_files(orig, exclude_prefixes=())}
        after = {r: sha(os.path.join(repo, r)) for r in iter_repo_files(repo, exclude_prefixes=())}   # nothing excluded
        changed = sorted(set(before) ^ set(after)) + sorted(r for r in set(before) & set(after) if before[r] != after[r])
        result["modified_outside_output"] = changed
        if changed:
            failures.append("reviewed repository was modified: " + ", ".join(changed))

    if a.diff:
        result["in_changed_lines"] = sum(1 for f in findings if f.get("in_changed_lines"))
        if any("in_changed_lines" not in f for f in findings):
            failures.append("diff review findings lack in_changed_lines flags")
    found, missed = {}, []
    for seed in exp["seeded"]:
        hit = matches(seed, findings, repo)
        if hit:
            found[seed["key"]] = hit
        else:
            missed.append(seed["key"])
    recall = len(found) / len(exp["seeded"])
    result.update(recall=round(recall, 3), seeded=len(exp["seeded"]), found=found, missed=missed)
    if recall < a.min_recall:
        failures.append("recall %.2f below %.2f" % (recall, a.min_recall))
    seeded_hits = set(found.values())
    result["unseeded_findings"] = [{"id": f["id"], "title": f["title"], "file": f["file"], "line": f["line"],
                                    "severity": f["severity"]} for f in findings if f["id"] not in seeded_hits]

    result["totals"] = data["totals"]
    result["failures"] = failures
    result["passed"] = not failures
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
