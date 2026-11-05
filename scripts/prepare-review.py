#!/usr/bin/env python3
"""Prepare a review (or run a quick scan) in ONE call, so the orchestrator saves round trips.

Does, in-process and read-only. Nothing is written inside the repository: output goes
to a folder OUTSIDE it (default ~/.917v-code-review/reviews/<repo>-<id>/, or --out,
or $CODE_REVIEW_OUT_DIR as the base folder), printed as "out" in the summary.
  1. claims the output folder (ownership marker) and creates <out>/.work/
  2. integrity snapshot        -> .work/baseline.json         (not for --mode scan)
  3. stack detection           -> .work/stack.json, files.txt
  4. diff scope (selectors)    -> .work/scope.json
  5. pattern signals           -> .work/signals.json
  6. import graph              -> .work/import-graph.json     (full, architecture, scan)
  7. one input file per agent  -> .work/agents/<agent>.md     (stack digest, scope, priority files,
                                  this agent's signals, import cycles, matching stack checklists)
  --mode scan instead renders <out>/scan.md and stops there (no agents).

Prints the stack digest and a JSON summary on stdout. Exit code 3 = nothing to review (empty diff).

Usage: prepare-review.py <root> [--mode full|diff|security|architecture|scan] [--out DIR]
                         [--staged | --branch BASE | --range A..B]
"""

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _common import claim_output_dir, dump_json  # noqa: E402

PLUGIN_ROOT = os.path.dirname(HERE)


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


detect_stack = _load("detect-stack")
diff_scope = _load("diff-scope")
scan_signals = _load("scan-signals")
import_graph = _load("import-graph")
integrity = _load("integrity")

ALL_AGENTS = ["architecture-reviewer", "security-reviewer", "performance-reviewer", "backend-reviewer",
              "frontend-reviewer", "database-reviewer", "testing-reviewer", "devops-reviewer"]
MAX_SIGNALS = 40
MAX_PRIORITY = 30

# Stack-checklist section -> predicate on the stack. Sections are "## " headings in stack-checklists.md.
CHECKLIST_RULES = [
    ("Node.js", lambda s: "Node.js" in s["runtimes"]),
    ("NestJS", lambda s: _fw(s, "nestjs")),
    ("Next.js", lambda s: _fw(s, "next.js")),
    ("React / Vue", lambda s: _fw(s, "react", "vue", "nuxt", "angular", "svelte")),
    ("Java / Spring", lambda s: "JVM" in s["runtimes"]),
    ("Python", lambda s: "Python" in s["runtimes"]),
    ("PHP", lambda s: "PHP" in s["runtimes"]),
    ("Go", lambda s: "Go" in s["runtimes"]),
    ("Docker", lambda s: _infra(s, "docker")),
    ("Terraform", lambda s: _infra(s, "terraform", "pulumi", "kubernetes", "helm")),
    ("CI/CD", lambda s: bool(s.get("ci_cd"))),
]


def _fw(stack, *names):
    return any(any(n in f["name"].lower() for n in names) for f in stack.get("frameworks", []))


def _infra(stack, *names):
    return any(any(n in i["name"].lower() for n in names) for i in stack.get("infrastructure", []))


def checklist_sections(stack):
    path = os.path.join(PLUGIN_ROOT, "skills", "comprehensive-review", "references", "stack-checklists.md")
    if not os.path.exists(path):  # standalone skill layout
        path = os.path.join(PLUGIN_ROOT, "references", "stack-checklists.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return []
    parts = re.split(r"(?m)^## ", text)[1:]
    wanted = [prefix for prefix, pred in CHECKLIST_RULES if pred(stack)]
    return ["## " + p.strip() for p in parts if any(p.startswith(w) for w in wanted)]


def priority_files(agent, stack, files, graph, scope):
    cp = {k: v.get("files", []) for k, v in (stack.get("critical_paths") or {}).items()}
    eps = [e["file"] for e in stack.get("entry_points") or []]
    pick = {
        "security-reviewer": eps + cp.get("security_sensitive", []) + cp.get("request_handlers", [])
        + cp.get("data_access", []),
        "backend-reviewer": eps + cp.get("request_handlers", []) + cp.get("money_or_business_critical", []),
        "database-reviewer": cp.get("data_access", []) + cp.get("money_or_business_critical", [])
        + [f for f in files if re.search(r"(migrat|schema\.prisma|\.sql$|models?\.py$|entity)", f, re.I)],
        "performance-reviewer": cp.get("request_handlers", []) + cp.get("data_access", [])
        + cp.get("money_or_business_critical", []),
        "architecture-reviewer": eps + [m["file"] for m in (graph or {}).get("most_depended_on", [])[:10]]
        + cp.get("money_or_business_critical", []),
        "testing-reviewer": cp.get("money_or_business_critical", []) + cp.get("security_sensitive", [])
        + [f for f in files if re.search(r"(\.spec\.|\.test\.|_test\.|/tests?/|Test\.java$)", f)],
        "frontend-reviewer": [f for f in files if re.search(r"\.(tsx|jsx|vue|svelte)$", f)],
        "devops-reviewer": [f for f in files if re.search(
            r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*|compose\.ya?ml|\.env[^/]*|Jenkinsfile|\.gitlab-ci\.yml)$"
            r"|^\.github/workflows/|\.tf$|(^|/)(k8s|helm|charts)/", f)]
        + [f for f in files if os.path.basename(f) in ("package.json", "pom.xml", "build.gradle", "go.mod",
                                                        "requirements.txt", "pyproject.toml", "composer.json")],
    }.get(agent, eps)
    if scope:
        changed = [f["file"] for f in scope["files"]]
        pick = changed + [p for p in pick if p in changed] + pick
    seen, out = set(), []
    for p in pick:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:MAX_PRIORITY]


def agent_input(agent, mode, root, work, stack, digest, files, signals, graph, scope, checklists):
    sigs = [s for s in signals.get("signals", []) if s.get("agent") == agent]
    lines = ["# Inputs for %s" % agent, "",
             "Prepared by scripts/prepare-review.py. ROOT: `%s` · MODE: %s" % (root, mode), "",
             "## Stack", "", "```", digest, "```", "", "## Scope", ""]
    if scope:
        lines.append("Diff: %s — %d files, %d changed lines. Review the changed lines and their direct call "
                     "context." % (scope["description"], scope["files_changed"], scope["lines_changed"]))
        lines += ["- `%s` lines %s" % (f["file"], ", ".join("%d-%d" % tuple(r) for r in f.get("ranges", [])) or
                                       f.get("status", "changed")) for f in scope["files"][:80]]
    else:
        lines.append("Whole repository (%d reviewable files; inventory in `%s`)." % (len(files), os.path.join(work, "files.txt")))
    lines += ["", "## Priority files", ""]
    lines += ["- `%s`" % p for p in priority_files(agent, stack, files, graph, scope)] or ["- (none detected)"]
    lines += ["", "## Signals for you (unverified leads: open each and decide)", ""]
    if sigs:
        lines += ["- `%s:%s` [%s] %s — %s" % (s["file"], s["line"], s["rule"], s.get("hint", ""),
                                              code_span((s.get("snippet") or "").strip()[:140]))
                  for s in sigs[:MAX_SIGNALS]]
        if len(sigs) > MAX_SIGNALS:
            lines.append("- … %d more in `%s` (filter by agent)" % (len(sigs) - MAX_SIGNALS, os.path.join(work, "signals.json")))
    else:
        lines.append("- none")
    if agent == "architecture-reviewer" and graph is not None:
        lines += ["", "## Import cycles", ""]
        lines += ["- " + " → ".join("`%s`" % f for f in c["example_path"]) for c in graph["cycles"][:20]] or ["- none"]
    if checklists:
        lines += ["", "## Stack checklist (check only the items in your categories)", "", "\n\n".join(checklists)]
    return "\n".join(lines).rstrip() + "\n"


def code_span(text):
    if not text:
        return "(no snippet)"
    return "`` %s ``" % text if "`" in text else "`%s`" % text


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("--mode", default="full", choices=["full", "diff", "security", "architecture", "scan"])
    ap.add_argument("--out", help="report folder outside the repository (default: ~/.917v-code-review/reviews/<repo>-<id>)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true")
    g.add_argument("--branch", metavar="BASE")
    g.add_argument("--range", metavar="A..B")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    out = claim_output_dir(root, a.out)   # outside the repository; never a folder the user owns
    work = os.path.join(out, ".work")
    os.makedirs(os.path.join(work, "raw"), exist_ok=True)

    scope = None
    selector = a.staged or a.branch or a.range
    if a.mode == "diff" or selector:
        if a.staged:
            scope = diff_scope.compute(root, "staged")
        elif a.branch:
            scope = diff_scope.compute(root, "branch", base=a.branch)
        elif a.range:
            scope = diff_scope.compute(root, "range", rng=a.range)
        else:
            scope = diff_scope.compute(root, "uncommitted")
        write_json(os.path.join(work, "scope.json"), scope)
        if not scope["files"]:
            dump_json({"nothing_to_review": True, "out": out, "scope": scope["description"],
                       "hint": "no changed files for this selector; try --staged, --branch <base> or --range a..b"})
            return 3

    if a.mode != "scan":
        write_json(os.path.join(work, "baseline.json"), integrity.snapshot(root))

    stack = detect_stack.detect(root)
    write_json(os.path.join(work, "stack.json"), stack)
    files = list(detect_stack.iter_repo_files(root))
    with open(os.path.join(work, "files.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(files) + "\n")
    digest = detect_stack.brief(stack)

    signals = scan_signals.scan(root, scope=scope)
    write_json(os.path.join(work, "signals.json"), signals)
    graph = None
    if a.mode in ("full", "architecture", "scan"):
        graph = import_graph.analyze(root)
        write_json(os.path.join(work, "import-graph.json"), graph)

    summary = {"root": root, "mode": a.mode, "out": out, "work": work,
               "scope": scope["description"] if scope else "whole repository",
               "files": len(files), "signals": len(signals.get("signals", [])),
               "signals_by_agent": signals.get("by_agent", {}),
               "import_cycles": len(graph["cycles"]) if graph is not None else None,
               "recommended_agents": [r["agent"] for r in stack.get("recommended_agents", [])],
               "skipped_agents": stack.get("skipped_agents", [])}
    if scope:
        summary.update(files_changed=scope["files_changed"], lines_changed=scope["lines_changed"])

    if a.mode == "scan":
        render_scan = _load("render-scan")
        _, scan_summary = render_scan.render(root, stack, signals, graph, scope, out)
        scan_summary["written"] = os.path.join(out, "scan.md")
        print(digest)
        dump_json(scan_summary)
        return 0

    checklists = checklist_sections(stack)
    agents_dir = os.path.join(work, "agents")
    os.makedirs(agents_dir, exist_ok=True)
    for agent in ALL_AGENTS:
        with open(os.path.join(agents_dir, agent + ".md"), "w", encoding="utf-8") as fh:
            fh.write(agent_input(agent, a.mode, root, work, stack, digest, files, signals, graph, scope, checklists))
    summary["agent_inputs"] = os.path.join(agents_dir, "<agent>.md")
    summary["checklist_sections"] = [c.splitlines()[0][3:] for c in checklists]
    print(digest)
    dump_json(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
