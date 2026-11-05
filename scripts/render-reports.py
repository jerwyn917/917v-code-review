#!/usr/bin/env python3
"""Render the review reports from validated findings (writes only to --out).

Inputs:
  --findings findings.json   output of validate-findings.py
  --stack    stack.json      output of detect-stack.py
  --summary  summary.json    narrative written by the orchestrating skill
  --scope    scope.json      optional, diff reviews only
  --integrity integrity.json optional, output of integrity.py verify
Outputs (in --out, normally docs/code-review/):
  executive-summary.md, detailed-findings.md, security-review.md,
  architecture-review.md, recommendations.md, and dashboard.html (--html)

Usage: render-reports.py --root <repo> --findings F --stack S --summary M -o docs/code-review [--html]
"""

import argparse
import datetime
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import CATEGORIES, SEVERITIES, dump_json, git, is_git_repo, load_json  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(PLUGIN_ROOT, "templates")
WEIGHTS = {"Critical": 15, "High": 7, "Medium": 3, "Low": 1, "Informational": 0}
OWASP = [
    ("A01", "Broken Access Control"), ("A02", "Cryptographic Failures"), ("A03", "Injection"),
    ("A04", "Insecure Design"), ("A05", "Security Misconfiguration"),
    ("A06", "Vulnerable and Outdated Components"), ("A07", "Identification and Authentication Failures"),
    ("A08", "Software and Data Integrity Failures"), ("A09", "Security Logging and Monitoring Failures"),
    ("A10", "Server-Side Request Forgery"),
]
LANG = {".ts": "ts", ".tsx": "tsx", ".js": "js", ".jsx": "jsx", ".mjs": "js", ".java": "java", ".kt": "kotlin",
        ".py": "python", ".php": "php", ".go": "go", ".rb": "ruby", ".rs": "rust", ".cs": "csharp",
        ".sql": "sql", ".tf": "hcl", ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".xml": "xml",
        ".properties": "properties", ".vue": "vue", ".html": "html", ".sh": "bash", ".prisma": "prisma"}


def cell(text):
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def plugin_version():
    try:
        return load_json(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")).get("version", "?")
    except (OSError, ValueError):
        pass
    try:  # standalone skill layout (tools/build-skill.py writes VERSION)
        with open(os.path.join(PLUGIN_ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def commit_info(root):
    if not is_git_repo(root):
        return "not a Git repository"
    try:
        sha = git(root, "rev-parse", "--short", "HEAD").strip()
    except RuntimeError:
        return "no commits yet"
    dirty = git(root, "status", "--porcelain", "--untracked-files=no").strip()
    return sha + (" (with uncommitted changes)" if dirty else "")


def health(findings):
    penalty = 0.0
    for f in findings:
        w = WEIGHTS[f["severity"]]
        penalty += w if f["status"] == "Confirmed" else w * 0.5
    # Diminishing returns: each finding costs a share of what is left, so large
    # reviews still differentiate instead of all flooring at zero.
    score = int(round(100 * math.exp(-penalty / 100.0)))
    if any(f["severity"] == "Critical" for f in findings) or score < 50:
        rating = "At Risk"
    elif score < 70:
        rating = "Needs Attention"
    elif score < 85:
        rating = "Fair"
    else:
        rating = "Healthy"
    return {"score": score, "rating": rating}


def link(f, line=None):
    line = line or f["line"]
    return "[`%s:%s`](../../%s#L%s)" % (f["file"], line, f["file"], line)


def fence(evidence, path):
    lang = LANG.get(os.path.splitext(path)[1].lower(), "")
    if os.path.basename(path).lower().startswith("dockerfile"):
        lang = "dockerfile"
    ticks = "~~~~" if "```" in evidence else "```"
    return "%s%s\n%s\n%s" % (ticks, lang, evidence.rstrip("\n"), ticks)


def finding_block(f):
    rows = [("Severity", f["severity"]), ("Category", f["category"] + (
        " (also: %s)" % ", ".join(f["also_categorised_as"]) if f.get("also_categorised_as") else "")),
        ("Status", f["status"]), ("Confidence", f["confidence"]),
        ("Location", link(f) + ("–%s" % f["end_line"] if f.get("end_line", f["line"]) != f["line"] else "")),
        ("Reported by", ", ".join(f.get("reported_by") or []) or "—")]
    if "in_changed_lines" in f:
        rows.append(("Diff", "on changed lines" if f["in_changed_lines"] else
                     ("in a changed file, outside the changed lines" if f.get("in_changed_file") else
                      "outside the changed files (context)")))
    refs = [r for r in (f.get("cwe"), f.get("owasp")) if r] + list(f.get("references") or [])
    if refs:
        rows.append(("References", ", ".join(str(r) for r in refs)))
    out = ["### %s · %s" % (f["id"], f["title"]), "", "| Field | Value |", "|---|---|"]
    out += ["| %s | %s |" % (k, v if k == "Location" else cell(v)) for k, v in rows]
    out += ["", "**Description**", "", f["description"], "", "**Evidence**", "", fence(f["evidence"], f["file"]),
            "", "**Potential impact**", "", f["impact"], "", "**Recommended solution**", "", f["recommendation"], ""]
    if f.get("related_locations"):
        out += ["**Also found at:** " + ", ".join(
            "[`%s:%s`](../../%s#L%s)" % (l["file"], l["line"], l["file"], l["line"]) for l in f["related_locations"]), ""]
    if f.get("validation_notes"):
        out += ["<sub>Validation: %s</sub>" % "; ".join(f["validation_notes"]), ""]
    return "\n".join(out)


def blocks(findings, empty):
    return "\n\n".join(finding_block(f) for f in findings) if findings else "_%s_" % empty


def count_table(counts, order, label):
    total = sum(counts.get(k, 0) for k in order)
    rows = ["| %s | Count |" % label, "|---|---:|"]
    rows += ["| %s | %d |" % (k, counts.get(k, 0)) for k in order]
    rows.append("| **Total** | **%d** |" % total)
    return "\n".join(rows)


def index_table(findings):
    if not findings:
        return "_No findings._"
    rows = ["| ID | Severity | Category | Title | Location | Status |", "|---|---|---|---|---|---|"]
    for f in findings:
        rows.append("| [%s](#%s) | %s | %s | %s | `%s:%s` | %s |" % (
            f["id"], anchor(f), f["severity"], f["category"], cell(f["title"]), f["file"], f["line"], f["status"]))
    return "\n".join(rows)


def anchor(f):
    text = ("%s · %s" % (f["id"], f["title"])).lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def rec_list(findings, empty):
    if not findings:
        return "_%s_" % empty
    return "\n".join("- **%s — %s** (%s, %s) — %s  \n  %s" % (
        f["id"], f["title"], f["severity"], f["status"], link(f), f["recommendation"].strip().replace("\n", " "))
        for f in findings)


def stack_summary(stack):
    if not stack:
        return "_Stack detection not available._"

    def names(items):
        return ", ".join("%s%s%s" % (i["name"], " " + i["version"] if i.get("version") else "",
                                     "" if i.get("confidence", "confirmed") == "confirmed" else " (manifest only)")
                         for i in items) or "—"
    langs = ", ".join("%s (%d files)" % (l["name"], l["files"]) for l in stack.get("languages", [])[:8]) or "—"
    pms = sorted({pm for p in stack.get("projects", []) for pm in p.get("package_managers", [])})
    rows = ["| Area | Detected |", "|---|---|",
            "| Languages | %s |" % cell(langs),
            "| Runtimes | %s |" % cell(", ".join(stack.get("runtimes", [])) or "—"),
            "| Frameworks | %s |" % cell(names(stack.get("frameworks", []))),
            "| Databases / ORM | %s |" % cell(names(stack.get("databases", []))),
            "| Testing | %s (%d test files) |" % (cell(", ".join(t["name"] for t in stack.get("testing", {}).get(
                "frameworks", [])) or "—"), stack.get("testing", {}).get("test_file_count", 0)),
            "| Infrastructure | %s |" % cell(", ".join(i["name"] for i in stack.get("infrastructure", [])) or "—"),
            "| CI/CD | %s |" % cell(", ".join(i["name"] for i in stack.get("ci_cd", [])) or "—"),
            "| Package managers | %s |" % cell(", ".join(pms) or "—"),
            "| Shape | %s |" % cell(stack.get("architecture_shape", "—"))]
    return "\n".join(rows)


def coverage_text(fdata, summary, stack, scope, integrity):
    lines = []
    cov = fdata.get("coverage") or {}
    if cov:
        lines.append("| Agent | Files reviewed |")
        lines.append("|---|---:|")
        for agent, c in sorted(cov.items()):
            lines.append("| %s | %d |" % (agent, c["files_reviewed"]))
        lines.append("")
    if stack:
        lines.append("Repository files considered: %d." % stack.get("file_count", 0))
    if scope:
        lines.append("Diff scope: %s — %d files, %d changed lines." % (
            scope["description"], scope["files_changed"], scope["lines_changed"]))
    for s in summary.get("agents_skipped") or []:
        lines.append("- Skipped **%s**: %s" % (s.get("agent"), s.get("reason")))
    v = fdata.get("validation", {})
    lines.append("")
    lines.append("Validation: %d findings submitted by reviewers, %d accepted, %d rejected (location or evidence could "
                 "not be verified in the source), %d duplicates merged, %d line numbers corrected." % (
                     v.get("submitted", 0), v.get("accepted", 0), v.get("rejected", 0),
                     v.get("duplicates_merged", 0), v.get("line_corrections", 0)))
    if integrity is not None:
        if integrity.get("unchanged"):
            lines.append("Read-only check: %d repository files hashed before and after the review — no file outside "
                         "`%s` was modified." % (integrity.get("files_checked", 0), integrity.get("excluded")))
        else:
            lines.append("**Read-only check FAILED**: files changed during the review: %s." % ", ".join(
                integrity.get("added", []) + integrity.get("modified", []) + integrity.get("deleted", [])))
    for lim in summary.get("limitations") or []:
        lines.append("- " + lim)
    return "\n".join(lines).strip()


def owasp_table(findings, notes):
    rows = ["| ID | Category | Findings | Notes |", "|---|---|---:|---|"]
    for code, name in OWASP:
        hits = [f["id"] for f in findings if str(f.get("owasp", "")).upper().startswith(code)]
        rows.append("| %s | %s | %s | %s |" % (code, name, ", ".join(hits) if hits else "0",
                                               cell((notes or {}).get(code, ""))))
    return "\n".join(rows)


def no_issue_list(fdata, agents):
    items = []
    for agent in agents:
        for area in (fdata.get("no_issue_areas") or {}).get(agent, []):
            items.append("- %s _(%s)_" % (area, agent))
    return "\n".join(items) or "_None recorded._"


def fill(template_name, values):
    with open(os.path.join(TEMPLATES, template_name), "r", encoding="utf-8") as fh:
        text = fh.read()
    for k, v in values.items():
        text = text.replace("{{%s}}" % k, str(v))
    leftover = re.findall(r"\{\{(\w+)\}\}", text)
    if leftover:
        raise SystemExit("template %s has unfilled placeholders: %s" % (template_name, ", ".join(leftover)))
    return text


def render(root, fdata, stack, summary, scope=None, integrity=None, out_dir=None, html=False):
    findings = fdata["findings"]
    totals = fdata["totals"]
    hl = health(findings)
    date = datetime.date.today().isoformat()
    review_type = summary.get("review_type") or "Full codebase review"
    scope_desc = scope["description"] if scope else summary.get("scope_description") or "entire repository"
    common = {
        "repository": summary.get("repository") or os.path.basename(os.path.abspath(root)),
        "review_type": review_type, "date": date, "scope_description": scope_desc,
    }
    by_sev = lambda sevs: [f for f in findings if f["severity"] in sevs]
    crit = [f for f in findings if f["severity"] in ("Critical", "High") and f["status"] == "Confirmed"] or \
        [f for f in findings if f["severity"] in ("Critical", "High")]
    critical_risks = "\n".join("- **%s** — %s (%s, %s) — %s" % (f["id"], f["title"], f["severity"], f["status"],
                                                                 link(f)) for f in crit[:8]) or \
        "_No Critical or High findings._"
    strategic = summary.get("strategic_recommendations") or []
    if strategic:
        top = "\n".join("%d. **%s** — %s%s" % (i + 1, s.get("title", ""), s.get("detail", ""),
                                               " (%s)" % ", ".join(s["related"]) if s.get("related") else "")
                        for i, s in enumerate(strategic[:5]))
    else:
        top = "\n".join("%d. %s — %s (%s)" % (i + 1, f["title"], f["recommendation"].split("\n")[0], f["id"])
                        for i, f in enumerate(findings[:5])) or "_No recommendations: no findings._"
    status = totals["by_status"]
    totals_line = "**%d findings** — %s. %d Confirmed, %d Potential." % (
        totals["findings"], ", ".join("%d %s" % (totals["by_severity"][s], s) for s in SEVERITIES),
        status.get("Confirmed", 0), status.get("Potential", 0))

    def scoped_findings_md():
        if not scope:
            return blocks(findings, "No findings.")
        on = [f for f in findings if f.get("in_changed_lines")]
        near = [f for f in findings if not f.get("in_changed_lines") and f.get("in_changed_file")]
        ctx = [f for f in findings if not f.get("in_changed_file")]
        return "\n\n".join([
            "## Findings on changed lines\n\n" + blocks(on, "None."),
            "## Findings elsewhere in changed files\n\n" + blocks(near, "None."),
            "## Related findings outside the changed files (context)\n\n" + blocks(ctx, "None.")])

    rejected = fdata.get("rejected") or []
    rejected_md = ""
    if rejected:
        rejected_md = "## Rejected during validation\n\nThese reviewer claims were dropped because their location " \
                      "or evidence could not be found in the source. They are listed for transparency only.\n\n" + \
                      "| Title | Claimed location | Reason |\n|---|---|---|\n" + "\n".join(
                          "| %s | `%s:%s` | %s |" % (cell(r.get("title")), r.get("file"), r.get("line"),
                                                     cell(r.get("reason"))) for r in rejected)
    sec = [f for f in findings if f["category"] == "Security"]
    sec_other = [f for f in findings if f["category"] != "Security" and (
        f.get("security_relevant") or "Security" in (f.get("also_categorised_as") or []))]
    sec_counts = count_table({s: sum(1 for f in sec if f["severity"] == s) for s in SEVERITIES}, SEVERITIES,
                             "Severity")
    arch = [f for f in findings if f["category"] == "Architecture"]
    cq = [f for f in findings if f["category"] == "Code Quality"]
    dep = summary.get("dependency_analysis") or "_Not provided._"
    files = {
        "executive-summary.md": fill("executive-summary.md", dict(common, **{
            "commit": commit_info(root), "plugin_version": plugin_version(),
            "agents_run": ", ".join(summary.get("agents_run") or sorted((fdata.get("coverage") or {}).keys())) or "—",
            "overall_summary": summary.get("overall_summary") or "_Not provided._",
            "health_rating": hl["rating"], "health_score": hl["score"],
            "health_assessment": summary.get("health_assessment") or "",
            "severity_table": count_table(totals["by_severity"], SEVERITIES, "Severity"),
            "category_table": count_table(totals["by_category"], list(CATEGORIES), "Category"),
            "critical_risks": critical_risks, "top_recommendations": top,
            "stack_summary": stack_summary(stack),
            "coverage": coverage_text(fdata, summary, stack, scope, integrity),
            "dashboard_link": " · [dashboard.html](dashboard.html)" if html else "",
        })),
        "detailed-findings.md": fill("detailed-findings.md", dict(common, **{
            "totals_line": totals_line, "index_table": index_table(findings),
            "findings": scoped_findings_md(), "rejected_section": rejected_md,
        })),
        "security-review.md": fill("security-review.md", dict(common, **{
            "security_overview": summary.get("security_overview") or "_Not provided._",
            "security_counts": sec_counts,
            "owasp_table": owasp_table(findings, summary.get("owasp_notes")),
            "security_findings": blocks(sec, "No security findings."),
            "other_security_findings": blocks(sec_other, "None."),
            "security_no_issue": no_issue_list(fdata, ["security-reviewer"]),
        })),
        "architecture-review.md": fill("architecture-review.md", dict(common, **{
            "architecture_overview": summary.get("architecture_overview") or "_Not provided._",
            "structure": stack_summary(stack),
            "dependency_analysis": dep,
            "architecture_findings": blocks(arch, "No architecture findings."),
            "code_quality_findings": blocks(cq, "No code quality findings."),
            "architecture_no_issue": no_issue_list(fdata, ["architecture-reviewer"]),
        })),
        "recommendations.md": fill("recommendations.md", dict(common, **{
            "strategic": "\n".join("- **%s** — %s%s" % (s.get("title", ""), s.get("detail", ""),
                                                        " (%s)" % ", ".join(s["related"]) if s.get("related") else "")
                                   for s in strategic) or "_None beyond the individual findings below._",
            "priority_1": rec_list(by_sev(("Critical", "High")), "Nothing in this priority."),
            "priority_2": rec_list(by_sev(("Medium",)), "Nothing in this priority."),
            "priority_3": rec_list(by_sev(("Low", "Informational")), "Nothing in this priority."),
            "positives": "\n".join("- " + p for p in summary.get("positive_observations") or []) or "_None recorded._",
        })),
    }
    if html:
        payload = dict(common, commit=commit_info(root), totals=totals, health=hl, findings=findings)
        data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        files["dashboard.html"] = fill("dashboard.html", {"data_json": data_json})
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        for name, text in files.items():
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
                fh.write(text.rstrip("\n") + "\n")
    return files, hl


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True)
    ap.add_argument("--findings", required=True)
    ap.add_argument("--stack")
    ap.add_argument("--summary")
    ap.add_argument("--scope")
    ap.add_argument("--integrity")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--html", action="store_true", help="also write the self-contained dashboard.html")
    a = ap.parse_args()
    opt = lambda p: load_json(p) if p and os.path.exists(p) else None
    files, hl = render(a.root, load_json(a.findings), opt(a.stack), opt(a.summary) or {}, opt(a.scope),
                       opt(a.integrity), a.out, a.html)
    dump_json({"written": sorted(os.path.join(a.out, n) for n in files), "health": hl})


if __name__ == "__main__":
    main()
