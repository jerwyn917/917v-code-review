#!/usr/bin/env python3
"""Merge reviewer outputs, verify every finding against the source, de-duplicate, assign IDs.

Each input is one agent's JSON output ({"agent", "files_reviewed", "findings",
"no_issue_areas"}) or a bare list of findings. A finding survives only when:
  * all required fields are present and enums are valid,
  * its file exists inside the repository,
  * its line number exists in that file, and
  * its evidence snippet actually appears in the file (at the cited line,
    or elsewhere in the file, in which case the line number is corrected).
Evidence and text fields are re-redacted for secrets.

Usage:
  validate-findings.py --root <repo> [--scope scope.json] -o findings.json raw/*.json
"""

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (CATEGORIES, CONFIDENCES, REDACTED, SEVERITIES, SEVERITY_RANK, STATUSES,  # noqa: E402
                     dump_json, eprint, load_json, read_text, redact, rel_inside, secret_values)

REQUIRED = ["severity", "category", "title", "description", "file", "line", "evidence", "impact",
            "recommendation", "confidence"]

SEVERITY_ALIASES = {"crit": "Critical", "critical": "Critical", "high": "High", "medium": "Medium",
                    "moderate": "Medium", "med": "Medium", "low": "Low", "minor": "Low", "info": "Informational",
                    "informational": "Informational", "information": "Informational", "note": "Informational"}
CATEGORY_ALIASES = {
    "architecture": "Architecture", "design": "Architecture",
    "code quality": "Code Quality", "quality": "Code Quality", "maintainability": "Code Quality",
    "security": "Security",
    "performance": "Performance",
    "api & backend": "API & Backend", "api and backend": "API & Backend", "api": "API & Backend",
    "backend": "API & Backend", "api/backend": "API & Backend",
    "frontend": "Frontend", "front-end": "Frontend", "ui": "Frontend",
    "database": "Database", "data": "Database", "db": "Database",
    "testing": "Testing", "tests": "Testing", "test": "Testing",
    "devops & infrastructure": "DevOps & Infrastructure", "devops and infrastructure": "DevOps & Infrastructure",
    "devops": "DevOps & Infrastructure", "infrastructure": "DevOps & Infrastructure", "infra": "DevOps & Infrastructure",
}
STOP = {"the", "and", "for", "with", "without", "from", "into", "are", "is", "not", "use", "uses", "using", "via",
        "in", "of", "on", "to", "a", "an", "be", "can", "may", "this", "that", "missing", "potential", "possible"}
WINDOW = 3  # lines of tolerance around the cited range when matching evidence
NEAR = 3    # lines apart that still count as "the same location" for de-duplication


def _norm_enum(value, aliases, allowed):
    if value is None:
        return None
    v = str(value).strip()
    if v in allowed:
        return v
    return aliases.get(v.lower())


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2 and t not in STOP}


def _jaccard(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def _evidence_lines(evidence):
    """Meaningful evidence lines: strip fences, line-number prefixes, ellipses and blank lines."""
    out = []
    for raw in evidence.splitlines():
        line = raw.rstrip()
        if re.match(r"^\s*```", line):
            continue
        line = re.sub(r"^\s*\d+\s*[|:→\t]\s?", "", line)  # "12 | code", "12: code", "12→code"
        s = _norm_ws(line)
        if not s or s in ("...", "…", "// ...", "# ...", "/* ... */") or len(s) < 3:
            continue
        out.append(s)
    return out


def _line_pattern(ev_line):
    parts = [re.escape(p) for p in ev_line.split(REDACTED)]
    parts = [p.replace(r"\ ", r"\s+").replace(r"\.\.\.", ".*?") for p in parts]
    return re.compile(".*?".join(parts))


def _find(lines_norm, pat, lo, hi):
    for i in range(max(0, lo), min(len(lines_norm), hi)):
        if pat.search(lines_norm[i]):
            return i + 1
    return None


def verify_location(root, f):
    """Return (ok, reason, notes) and correct f['line']/f['end_line'] in place when needed."""
    notes = []
    rel = str(f["file"]).strip().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    if os.path.isabs(rel):
        if not rel_inside(root, os.path.relpath(rel, root)):
            return False, "file path is outside the repository", notes
        rel = os.path.relpath(rel, root).replace(os.sep, "/")
    if not rel_inside(root, rel):
        return False, "file path escapes the repository", notes
    f["file"] = rel
    full = os.path.join(root, rel)
    if not os.path.isfile(full):
        return False, "file does not exist: %s" % rel, notes
    text = read_text(root, rel)
    if text is None:
        return False, "file is binary or unreadable: %s" % rel, notes
    lines = text.splitlines() or [""]
    try:
        line = int(f["line"])
    except (TypeError, ValueError):
        return False, "line is not an integer: %r" % f.get("line"), notes
    end = f.get("end_line")
    try:
        end = int(end) if end not in (None, "") else line
    except (TypeError, ValueError):
        end = line
    if line < 1 or line > len(lines):
        return False, "line %d does not exist (%s has %d lines)" % (line, rel, len(lines)), notes
    end = min(max(end, line), len(lines))

    if f.get("evidence_type") == "absence":
        f["line"], f["end_line"] = line, end
        f["evidence_verified"] = "absence"
        return True, None, notes

    ev_lines = _evidence_lines(redact(str(f["evidence"])))
    if not ev_lines:
        return False, "evidence is empty after normalisation", notes
    norm = [_norm_ws(redact(l)) for l in lines]
    pats = [_line_pattern(e) for e in ev_lines]
    in_window = [_find(norm, p, line - 1 - WINDOW, end + WINDOW) for p in pats]
    found = sum(1 for x in in_window if x)
    if found == len(pats):
        hits = [x for x in in_window if x]
        f["line"], f["end_line"] = line, max(end, max(hits))
        f["evidence_verified"] = "exact"
        return True, None, notes
    # Evidence elsewhere in the file: correct the line number from the first evidence line.
    first = _find(norm, pats[0], 0, len(norm))
    if first:
        rest = [_find(norm, p, first - 1, first + len(pats) + 2 * WINDOW) for p in pats[1:]]
        if all(rest):
            span = (max(rest) if rest else first) - first
            notes.append("line corrected from %d to %d" % (line, first))
            f["line"], f["end_line"] = first, first + span
            f["evidence_verified"] = "relocated"
            return True, None, notes
    if found and found * 2 >= len(pats):
        f["line"], f["end_line"] = line, end
        f["evidence_verified"] = "partial"
        notes.append("only %d of %d evidence lines matched the source" % (found, len(pats)))
        return True, None, notes
    return False, "evidence not found in %s" % rel, notes


def _secrets_near(root, f):
    text = read_text(root, f["file"]) or ""
    lines = text.splitlines()
    lo, hi = max(0, f["line"] - 1 - WINDOW), f.get("end_line", f["line"]) + WINDOW
    return secret_values("\n".join(lines[lo:hi]))


def _scrub(obj, secrets):
    ordered = sorted(secrets, key=len, reverse=True)
    if isinstance(obj, str):
        return redact(obj, ordered)
    if isinstance(obj, list):
        return [_scrub(x, secrets) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub(v, secrets) for k, v in obj.items()}
    return obj


def normalise(f, agent):
    notes = []
    missing = [k for k in REQUIRED if f.get(k) in (None, "")]
    if missing:
        return None, "missing required field(s): " + ", ".join(missing)
    sev = _norm_enum(f["severity"], SEVERITY_ALIASES, SEVERITIES)
    cat = _norm_enum(f["category"], CATEGORY_ALIASES, CATEGORIES)
    conf = _norm_enum(f["confidence"], {c.lower(): c for c in CONFIDENCES}, CONFIDENCES)
    status = _norm_enum(f.get("status") or "Potential", {s.lower(): s for s in STATUSES}, STATUSES)
    if not sev:
        return None, "invalid severity %r" % f["severity"]
    if not cat:
        return None, "invalid category %r" % f["category"]
    if not conf:
        return None, "invalid confidence %r" % f["confidence"]
    if not status:
        return None, "invalid status %r" % f.get("status")
    # Severity / certainty consistency rules (see references/severity-rubric.md).
    if status == "Confirmed" and conf == "Low":
        status = "Potential"
        notes.append("status set to Potential (Low confidence cannot be Confirmed)")
    if sev == "Critical" and status != "Confirmed":
        sev = "High"
        notes.append("severity capped at High (Critical requires a Confirmed finding)")
    if conf == "Low" and SEVERITY_RANK[sev] < SEVERITY_RANK["Medium"]:
        notes.append("severity capped at Medium (Low confidence)")
        sev = "Medium"
    out = {}
    for k, v in f.items():
        out[k] = redact(v) if isinstance(v, str) else v
    out.update(severity=sev, category=cat, confidence=conf, status=status)
    out["reported_by"] = sorted(set(([agent] if agent else []) + list(f.get("reported_by") or [])))
    out.pop("id", None)
    return out, notes


def _overlap(a, b):
    return a["file"] == b["file"] and a["line"] <= b.get("end_line", b["line"]) + NEAR and \
        b["line"] <= a.get("end_line", a["line"]) + NEAR


def _better(a, b):
    """Pick the primary record when two findings are duplicates."""
    key = lambda f: (SEVERITY_RANK[f["severity"]], CONFIDENCES.index(f["confidence"]),
                     0 if f["status"] == "Confirmed" else 1, -len(f.get("description", "")))
    return a if key(a) <= key(b) else b


def _merge(primary, other, adopt_severity=False):
    p = dict(primary)
    p["reported_by"] = sorted(set(p.get("reported_by", [])) | set(other.get("reported_by", [])))
    if other["status"] == "Confirmed":
        p["status"] = "Confirmed"
    if adopt_severity and SEVERITY_RANK[other["severity"]] < SEVERITY_RANK[p["severity"]]:
        p.setdefault("validation_notes", []).append(
            "severity raised from %s to %s on merge with a duplicate" % (p["severity"], other["severity"]))
        p["severity"] = other["severity"]
        if p["severity"] == "Critical" and p["status"] != "Confirmed":
            p["severity"] = "High"
    related = list(p.get("related_locations") or [])
    for loc in [{"file": other["file"], "line": other["line"]}] + list(other.get("related_locations") or []):
        if loc.get("file") == p["file"] and abs(int(loc.get("line", 0)) - p["line"]) <= NEAR:
            continue
        if loc not in related:
            related.append(loc)
    if related:
        p["related_locations"] = related
    p["merged_count"] = p.get("merged_count", 1) + other.get("merged_count", 1)
    p.setdefault("merged_titles", [])
    p["merged_titles"] = p["merged_titles"] + [other["title"]] + list(other.get("merged_titles") or [])
    if other["category"] != p["category"]:
        p.setdefault("also_categorised_as", [])
        for c in [other["category"]] + list(other.get("also_categorised_as") or []):
            if c != p["category"] and c not in p["also_categorised_as"]:
                p["also_categorised_as"].append(c)
    return p


def _ref(f):
    return {"agent": (f.get("reported_by") or [None])[0], "title": f["title"]}


def _matches(f, ref):
    if not isinstance(ref, dict) or not ref.get("title"):
        return False
    titles = [f["title"]] + list(f.get("merged_titles") or [])
    return ref["title"] in titles and (not ref.get("agent") or ref["agent"] in (f.get("reported_by") or []))


def _strong_duplicate(f, g):
    """Same root cause beyond reasonable doubt: auto-merged."""
    if _overlap(f, g):
        t = _jaccard(f["title"], g["title"])
        if set(f.get("reported_by") or []) & set(g.get("reported_by") or []):
            return t >= 0.5  # one agent split these on purpose unless it repeated itself
        same_cat = f["category"] == g["category"]
        return t >= 0.5 or bool(f.get("cwe") and f.get("cwe") == g.get("cwe")) or \
            (same_cat and (t >= 0.3 or _jaccard(f["evidence"], g["evidence"]) >= 0.8))
    return f["category"] == g["category"] and _jaccard(f["title"], g["title"]) >= 0.8 and \
        _jaccard(f["recommendation"], g["recommendation"]) >= 0.5


def dedupe(findings, merges=()):
    """Apply orchestrator merge decisions, then auto-merge strong duplicates.

    Findings that only share a location are NOT merged automatically (distinct
    issues often sit on the same lines); they are returned as merge candidates
    for the orchestrator to decide in merges.json.
    """
    pool = list(findings)
    merged, unresolved = 0, []
    for m in merges or ():
        keep = next((f for f in pool if _matches(f, m.get("keep"))), None)
        drop = next((f for f in pool if f is not keep and _matches(f, m.get("merge"))), None)
        if keep is None or drop is None:
            unresolved.append(m)
            continue
        combined = _merge(keep, drop, adopt_severity=True)
        combined.setdefault("validation_notes", []).append(
            "merged by orchestrator decision: %s" % (m.get("reason") or "same root cause"))
        pool = [combined if f is keep else f for f in pool if f is not drop]
        merged += 1
    out = []
    for f in sorted(pool, key=lambda x: (x["file"], x["line"])):
        for i, g in enumerate(out):
            if _strong_duplicate(f, g):
                primary = _better(g, f)
                out[i] = _merge(primary, f if primary is g else g)
                merged += 1
                break
        else:
            out.append(f)
    candidates = []
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            strict = a["file"] == b["file"] and a["line"] <= b.get("end_line", b["line"]) and \
                b["line"] <= a.get("end_line", a["line"])
            if strict and not set(a.get("reported_by") or []) & set(b.get("reported_by") or []):
                candidates.append({"a": _ref(a), "b": _ref(b), "file": a["file"],
                                   "lines": [a["line"], b["line"]], "categories": [a["category"], b["category"]]})
    return out, merged, candidates, unresolved


def assign_ids(findings):
    findings.sort(key=lambda f: (SEVERITY_RANK[f["severity"]], list(CATEGORIES).index(f["category"]),
                                 f["file"], f["line"]))
    counters = {}
    ordered = []
    for f in findings:
        prefix = CATEGORIES[f["category"]][0]
        counters[prefix] = counters.get(prefix, 0) + 1
        rec = {"id": "%s-%03d" % (prefix, counters[prefix])}
        rec.update(f)
        ordered.append(rec)
    return ordered


def apply_scope(findings, scope):
    ranges = {f["file"]: f["ranges"] for f in scope["files"]}
    for f in findings:
        rs = ranges.get(f["file"])
        start, end = f["line"], f.get("end_line", f["line"])
        f["in_changed_lines"] = bool(rs) and any(s <= end and start <= e for s, e in rs)
        f["in_changed_file"] = rs is not None


def run(root, inputs, scope=None, merges=None):
    root = os.path.abspath(root)
    accepted, rejected, coverage, no_issue = [], [], {}, {}
    known_secrets = set()
    for path in inputs:
        data = load_json(path)
        if isinstance(data, list):
            agent, items = None, data
        else:
            agent = data.get("agent")
            items = data.get("findings") or []
            if agent:
                coverage[agent] = {"files_reviewed": len(data.get("files_reviewed") or []),
                                   "files": sorted(set(data.get("files_reviewed") or []))}
                if data.get("no_issue_areas"):
                    no_issue[agent] = data["no_issue_areas"]
        for raw in items:
            f, info = normalise(raw, agent or raw.get("agent"))
            if f is None:
                rejected.append({"title": raw.get("title"), "file": raw.get("file"), "line": raw.get("line"),
                                 "agent": agent or raw.get("agent"), "reason": info})
                continue
            ok, reason, loc_notes = verify_location(root, f)
            if not ok:
                rejected.append({"title": f.get("title"), "file": f.get("file"), "line": f.get("line"),
                                 "agent": agent or f.get("agent"), "reason": reason})
                continue
            notes = list(info) + loc_notes
            known_secrets.update(_secrets_near(root, f))
            if f.get("evidence_verified") == "partial" and f["confidence"] == "High":
                f["confidence"] = "Medium"
                notes.append("confidence lowered to Medium (partial evidence match)")
            if notes:
                f["validation_notes"] = notes
            accepted.append(f)
    # Scrub secret values seen in the cited source lines from every text field (free text included).
    if known_secrets:
        accepted = [_scrub(f, known_secrets) for f in accepted]
        rejected = [_scrub(r, known_secrets) for r in rejected]
    corrections = sum(1 for f in accepted if f.get("evidence_verified") == "relocated")
    findings, merged, candidates, unresolved = dedupe(accepted, merges)
    findings = assign_ids(findings)
    ids = {(f["title"], tuple(f["reported_by"])): f["id"] for f in findings}
    for c in candidates:
        for side in ("a", "b"):
            c[side]["id"] = next((fid for (t, agents), fid in ids.items()
                                  if t == c[side]["title"] and c[side]["agent"] in agents), None)
    if scope:
        apply_scope(findings, scope)
    by_sev = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    by_cat = {c: sum(1 for f in findings if f["category"] == c) for c in CATEGORIES}
    by_status = {s: sum(1 for f in findings if f["status"] == s) for s in STATUSES}
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "root": root,
        "totals": {"findings": len(findings), "by_severity": by_sev, "by_category": by_cat, "by_status": by_status},
        "validation": {"submitted": len(accepted) + len(rejected), "accepted": len(accepted),
                       "rejected": len(rejected), "duplicates_merged": merged,
                       "line_corrections": corrections,
                       "orchestrator_merges_unresolved": unresolved,
                       "merge_candidates": len(candidates)},
        "coverage": coverage,
        "no_issue_areas": no_issue,
        "findings": findings,
        "merge_candidates": candidates,
        "rejected": rejected,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True)
    ap.add_argument("--scope", help="scope.json from diff-scope.py (marks findings on changed lines)")
    ap.add_argument("--merges", help="merges.json: orchestrator decisions [{keep:{agent,title}, merge:{agent,title}, reason}]")
    ap.add_argument("-o", "--output", default="-")
    ap.add_argument("inputs", nargs="+")
    a = ap.parse_args()
    result = run(a.root, a.inputs, load_json(a.scope) if a.scope else None,
                 load_json(a.merges) if a.merges and os.path.exists(a.merges) else None)
    dump_json(result, a.output)
    v = result["validation"]
    eprint("validated: %d submitted, %d accepted, %d rejected, %d duplicates merged, %d line corrections -> %d findings"
           % (v["submitted"], v["accepted"], v["rejected"], v["duplicates_merged"], v["line_corrections"],
              result["totals"]["findings"]))
    if v["merge_candidates"]:
        eprint("%d same-location pairs from different agents were kept separate; review merge_candidates and record true duplicates in merges.json" % v["merge_candidates"])
    if v["orchestrator_merges_unresolved"]:
        eprint("warning: %d merges.json entries matched no finding" % len(v["orchestrator_merges_unresolved"]))


if __name__ == "__main__":
    main()
