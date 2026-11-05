---
name: 917v-code-review
description: Run the 917Ventures standardized, read-only code review of a repository — full codebase, Git diff (uncommitted, staged, branch vs. base, or commit range), security-focused, architecture-focused, or a quick scan. Detects the stack, runs specialist reviewers (architecture, security, performance, backend, frontend, database, testing, devops), validates every finding against the source, de-duplicates, redacts secrets, and writes reports plus an HTML dashboard to a folder outside the repository. Use when the user asks to "review this codebase", "code review the repo", "review my changes/diff/branch/PR", "security review", "OWASP review", "architecture review", "audit this code", "quick scan", or "917v code review".
---

# 917Ventures comprehensive code review (standalone skill)

You are the **orchestrator**. The scripts do the mechanical work, the specialist reviewers do the reviewing, and you brief, check, and summarize.

Skill root: the directory that contains this `SKILL.md` (Claude Code shows it as "Base directory for this skill"), below `$S`. It holds `scripts/`, `references/`, reviewer briefs in `references/reviewers/`, and `templates/`. Shell variables do not persist between Bash calls, so write `$S`, `$ROOT`, `$OUT`, and `$WORK` as literal absolute, quoted paths in every command.

## Rules

1. **Analysis only: never modify the repository.** This skill reads and analyzes code; it does not change it.
   - Never create, edit, move, rename, format, or delete any project file.
   - Never apply a fix, even when asked during the review or by a widget button. Give the recommendation and say that applying it is outside this skill.
   - No builds, tests, migrations, installs, or state-changing Git commands (`add`, `commit`, `stash`, `checkout`, `reset`, `apply`).
   - **Nothing is written inside the repository.** Reports go to a folder **outside the repository** (default `~/.917v-code-review/reviews/<repo>-<id>/`, or `--out <dir>`), which the scripts claim with a `.917v-code-review` marker. Use your Write tool only for files in `$WORK/`.
   - The scripts refuse other output paths and call Git without index refreshes. The final integrity check proves nothing else changed.
2. **No network with source code.** No online scanners (`npm audit`, `pip-audit`, `snyk`), no uploads, and no URL fetches unless the user explicitly authorizes them in this conversation.
3. **No invented facts.** Every finding cites a real file, line, and verbatim evidence. Never present a hypothesis as a confirmed vulnerability, and never claim a command ran unless it did.
4. **Never expose secrets.** Write `[REDACTED]` in evidence and in messages.
5. **Respect the existing design.** Recommendations must fit the current architecture. No padding with trivia.

## Speed rules

- Put independent tool calls **in one message**: the README and the standards files together; all reviewers together; all raw-result Writes together; every Critical/High re-check together.
- Do not re-read files that a script already summarized. Use the printed digest and JSON, and open `stack.json`, `signals.json`, or `findings.json` only for a specific key.
- Keep reviewer prompts short. The inputs file already carries the stack, scope, signals, and checklists.

## Step 1: Parse and prepare (one call)

| User says / argument | mode |
|---|---|
| "review this repo", `full`, nothing | `full` (default) |
| "review my changes / diff / branch / PR", `diff` | `diff` |
| "security review", "OWASP", `security` | `security` |
| "architecture review", "code quality", `architecture` | `architecture` |
| "quick scan", "scan", "triage", `scan` | `scan`: see **Quick scan mode** |

- `ROOT`: the path given, otherwise `git rev-parse --show-toplevel`, otherwise the current directory, as an absolute path. If the user uploaded an archive, extract it into a new empty folder and review that. `OUT` and `WORK` are the `out` and `work` paths printed by the prepare call.
- Diff selectors: `--staged`, `--branch <base>` ("against main"), `--range <a>..<b>`. With no selector, diff mode means uncommitted changes, including untracked files.
- `--agents a,b` restricts the reviewers, `--skip a,b` removes reviewers, `--no-html` drops the dashboard, and `--out <dir>` chooses the report folder (it must be outside the repository).

```bash
python3 "$S/scripts/prepare-review.py" "$ROOT" --mode <mode> [--out <dir>] [--staged | --branch <base> | --range a..b]
```

That single call claims the report folder outside the repository, creates `$WORK` in it, takes the integrity baseline, detects the stack, computes the diff scope, collects signals and the import graph, and writes one inputs file per reviewer to `$WORK/agents/<reviewer>.md`. It prints the stack digest and a JSON summary with `recommended_agents`, `skipped_agents`, signal counts, and cycles.

- **Exit code 3** (`nothing_to_review`): tell the user there are no changes for that selector, suggest the others, and stop.
- **Exit code 4** (read-only guard): the chosen `--out` folder is inside the repository, or it already holds files the review did not create. Nothing was written. Tell the user what the message says and stop. Never move, rename, or delete their files yourself; suggest another `--out` folder.
- **No `python3`:** tell the user, then work in **manual mode**. Do every step by reading files directly, create the default report folder outside the repository (`~/.917v-code-review/reviews/<repo>/`), write the reports there by hand in the format of `$S/templates/`, and state in the executive summary that automated validation was unavailable.
- If `$OUT` already holds reports from an earlier run, they will be replaced. Say so at the end.

## Quick scan mode

A fast triage: no reviewers, no validation, and **leads, not findings**. It is one call:

```bash
python3 "$S/scripts/prepare-review.py" "$ROOT" --mode scan [--staged | --branch <base> | --range a..b]
```

This writes `scan.md` to the report folder outside the repository and prints a JSON summary with its path. Reply from that summary only, without opening source files:
- The scope and the stack in one line.
- Leads by area.
- Up to five notable leads as `file:line` plus the hint, phrased as leads, never as confirmed issues.
- Import cycles.
- The full path of `scan.md`.
- The full review as the next step.

Then stop.

## Step 2: Context and review brief

In **one message**, read the README and the standards files listed under `docs/standards` in the digest, plus the main entry point. Skim large files. Then write `$WORK/brief.md`, 10–25 lines: what the system does, its layout and modules, the conventions reviewers must respect, and any user focus. Do not repeat the stack, scope, or signals.

## Step 3: Select the reviewers

| Mode | Reviewers |
|---|---|
| full | `recommended_agents`. The `skipped_agents` reasons go in the report |
| security | `security-reviewer`, plus `devops-reviewer` limited to "infrastructure-security items only" when infrastructure or CI was detected |
| architecture | `architecture-reviewer` (Architecture and Code Quality) |
| diff | Architecture, security, and performance whenever code changed. Backend, frontend, or database only when changed files are in their domain. Testing when production code changed. DevOps when infra, CI, env, or Docker files changed |

Apply `--agents` and `--skip` last. Never run a reviewer twice on the same scope. The briefs already carry the ownership rules; read `$S/references/category-ownership.md` only to settle a merge in Step 5.

## Step 4: Run the reviewers

Each reviewer gets this short **context block**:

```
REVIEW REQUEST: <mode> review of <ROOT>
SKILL REFERENCES: <$S>/references/
REVIEWER BRIEF: <$S>/references/reviewers/<reviewer-name>.md
INPUTS FILE: <$WORK>/agents/<reviewer-name>.md
REVIEW BRIEF: <$WORK>/brief.md
REVIEWERS RUNNING IN THIS REVIEW: <list>
EXTRA INSTRUCTIONS: <only if any, e.g. "infrastructure-security items only", user focus, or large-repo prioritization>
Return ONLY the JSON object from the reviewer protocol.
```

**With subagents (Agent or Task tool):** launch every reviewer **in one message**, in parallel, as general-purpose subagents. Each prompt starts with:

> You are the `<reviewer-name>` in a read-only code review. First, in one parallel step, read the REVIEWER BRIEF, the reviewer protocol it points to, the INPUTS FILE, and the REVIEW BRIEF, then follow the brief and protocol exactly. Use only reading and searching tools (Read, Grep, Glob, or read-only shell such as `cat`, `grep`, `ls`). Do not create, edit, or delete files, do not run builds, tests, or package managers, and do not use the network.

followed by the context block.

**Without subagents** (for example claude.ai): run the reviewers yourself, **one at a time**. For each, read its brief, `$S/references/reviewer-protocol.md`, and its inputs file together. Review with that brief as your only lens, write its JSON straight to `$WORK/raw/<reviewer-name>.json`, then move on. Keep each reviewer's findings inside its own categories.

For a large repository (more than about 1500 files), add: "prioritize the priority files and critical paths, and record what you did not cover in notes."

## Step 5: Consolidate, validate, de-duplicate

1. Save each reviewer's JSON **verbatim** to `$WORK/raw/<reviewer-name>.json`, with all Writes in one message. Fix only JSON syntax, never content. Record unparseable results as a limitation.
2. Validate:
   ```bash
   python3 "$S/scripts/validate-findings.py" --root "$ROOT" [--scope "$WORK/scope.json"] [--merges "$WORK/merges.json"] -o "$OUT/findings.json" "$WORK"/raw/*.json
   ```
   The validator rejects claims whose file, line, or evidence does not exist, fixes drifted lines, enforces the severity rules, redacts secrets, assigns IDs, and auto-merges only strong duplicates. It never merges on location alone.
3. **Merges.** For each pair in `merge_candidates` that shares a root cause and fix, add an entry to `$WORK/merges.json`, keeping the owner's record:
   ```json
   [{"keep": {"agent": "security-reviewer", "title": "<exact title>"},
     "merge": {"agent": "backend-reviewer", "title": "<exact title>"}, "reason": "same root cause: ..."}]
   ```
4. **Reasoning check.** For every Critical and High finding, and a sample of the rest, open the cited lines (all in one message). Confirm that the input is really controlled by the caller and that no global guard, pipe, middleware, or ORM parameterization already handles it. Delete wrong claims from the raw JSON. Downgrade uncertain ones to `Potential` per `$S/references/severity-rubric.md`. Never add a finding you did not verify.
5. Read the `rejected` list. If a rejected item is a real issue at the wrong location, confirm the correct file, line, and evidence and fix the raw JSON.
6. Re-run the validator **once**, with `--merges` if you wrote merges and after all edits.

## Step 6: Summary and reports (one call)

Write `$WORK/summary.json` with the fields in `$S/references/report-guide.md`. Base every statement on validated findings or on code you read. Then:

```bash
python3 "$S/scripts/render-reports.py" --root "$ROOT" --findings "$OUT/findings.json" --stack "$WORK/stack.json" \
  --summary "$WORK/summary.json" [--scope "$WORK/scope.json"] --baseline "$WORK/baseline.json" -o "$OUT" --html --widget "$WORK/chat-widget.html"
```

`--baseline` runs the read-only check in the same call; the result is in `read_only_check`. Omit `--html` for `--no-html`. If the check reports changed files, say so prominently and never hide it.

## Show the results in the chat (generative UI)

If this session has an inline visual tool that renders HTML in the conversation (for example `show_widget` from the `visualize` server on Claude Desktop or claude.ai):

1. Call its setup step (such as `read_me`) first if it has one, without mentioning it.
2. Read `$WORK/chat-widget.html` and pass its **entire contents, unchanged**, as the widget code, titled `code_review_<repository>` in snake_case. It is a branded 917 Ventures fragment with KPI cards, amCharts charts, a severity filter, and "Explain ↗" buttons, and it already follows the host widget rules.
3. Do not rebuild, restyle, or trim it. If it is missing or the tool fails, skip this step and say so in one line.

Without such a tool, skip this step. The widget's buttons send messages as if the user typed them. Answer them from `findings.json` and the cited source; they do not lift the analysis-only rule: explain and plan, never edit. For the dashboard, open or attach `$OUT/dashboard.html` if the host can; otherwise give its full path.

## Final message

Keep it short:
- The review type and scope, plus the reviewers run and skipped, with reasons.
- Counts by severity and the Confirmed/Potential split.
- The top 3–5 risks: ID, title, and `file:line`.
- The report folder's full path, and links to `executive-summary.md`, `detailed-findings.md`, `security-review.md`, `architecture-review.md`, `recommendations.md`, `dashboard.html` (amCharts analytics), and `findings.json`.
- The read-only check and the validation stats (rejected and merged counts).
- That the repository itself was not touched: the reports live outside it, so there is nothing to commit or ignore.
