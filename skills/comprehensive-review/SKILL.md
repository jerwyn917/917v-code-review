---
name: comprehensive-review
description: Run the 917Ventures standardized, read-only code review of a repository — full codebase, Git diff (uncommitted, staged, or branch), security-focused, or architecture-focused. Detects the stack, dispatches the 917v-code-review specialist agents, validates every finding against the source, de-duplicates, and writes reports to docs/code-review/. Use when the user asks to "review this codebase", "code review the repo", "review my changes/diff/branch", "security review", "architecture review", or runs a /917v-code-review command.
argument-hint: "mode=full|diff|security|architecture [path] [--staged | --branch <base> | --range a..b] [--agents a,b] [--skip a,b] [--no-html]"
---

# 917Ventures comprehensive code review

You are the **orchestrator**. The scripts do the mechanical work, the specialist agents do the reviewing, and you brief, check, and summarize.

Plugin root: `${CLAUDE_PLUGIN_ROOT}` (below: `$P`). Shell variables do not persist between Bash calls, so write `$P`, `$ROOT`, `$OUT`, and `$WORK` as literal absolute, quoted paths in every command.

## Rules

1. **Read-only.** Write only inside `<ROOT>/docs/code-review/`. No builds, tests, migrations, installs, formatting, or Git changes (`add`, `commit`, `stash`, `checkout`, `reset`). If the user asks for fixes, finish the review first; fixes are a separate step they must ask for.
2. **No network with source code.** No online scanners (`npm audit`, `pip-audit`, `snyk`), no uploads, and no URL fetches unless the user explicitly authorizes them in this conversation.
3. **No invented facts.** Every finding cites a real file, line, and verbatim evidence. Never present a hypothesis as a confirmed vulnerability, and never claim a command ran unless it did.
4. **Never expose secrets.** Write `[REDACTED]` in evidence and in messages.
5. **Respect the existing design.** Recommendations must fit the current architecture. No padding with trivia.

## Speed rules

- Put independent tool calls **in one message**: the README and the standards files together; all agents together; all raw-result Writes together; every Critical/High re-check together.
- Do not re-read files that a script already summarized. Use the printed digest and JSON, and open `stack.json`, `signals.json`, or `findings.json` only for a specific key.
- Keep agent prompts short. The inputs file already carries the stack, scope, signals, and checklists.

## Step 1: Parse and prepare (one call)

- `mode` (commands pass it first): `full` (default), `diff`, `security`, `architecture`.
- `ROOT`: the path argument, otherwise `git rev-parse --show-toplevel`, otherwise the current directory, as an absolute path. `OUT=$ROOT/docs/code-review`, `WORK=$OUT/.work`.
- Diff selectors: `--staged`, `--branch <base>`, `--range <a>..<b>`. With no selector, diff mode means uncommitted changes, including untracked files.
- `--agents a,b` restricts the agents, `--skip a,b` removes agents, and `--no-html` drops the dashboard.

```bash
python3 "$P/scripts/prepare-review.py" "$ROOT" --mode <mode> [--staged | --branch <base> | --range a..b]
```

That single call creates `$WORK` with its `.gitignore`, takes the integrity baseline, detects the stack, computes the diff scope, collects signals and the import graph, and writes one inputs file per agent to `$WORK/agents/<agent>.md`. It prints the stack digest and a JSON summary with `recommended_agents`, `skipped_agents`, signal counts, and cycles.

- **Exit code 3** (`nothing_to_review`): tell the user there are no changes for that selector, suggest the others, and stop without writing reports.
- **No `python3`:** tell the user, then work in **manual mode**. Do every step with Read, Grep, and Glob, write the reports by hand in the format of `$P/templates/`, and state in the executive summary that automated validation was unavailable.
- If `$OUT` already holds reports, they will be replaced. Say so at the end.

## Step 2: Context and review brief

In **one message**, read the README and the standards files listed under `docs/standards` in the digest (CONTRIBUTING, CLAUDE.md, ADRs, lint configs), plus the main entry point. Skim large files instead of reading them in full.

Then Write `$WORK/brief.md`, 10–25 lines: what the system does, its layout and main modules, the conventions reviewers must respect (error handling, layering, naming), and any focus the user asked for. Do not repeat the stack, scope, or signals; the inputs files already have them.

## Step 3: Select the agents

| Mode | Agents |
|---|---|
| full | `recommended_agents`. The `skipped_agents` reasons go in the report |
| security | `security-reviewer`, plus `devops-reviewer` limited to "infrastructure-security items only" when infrastructure or CI was detected |
| architecture | `architecture-reviewer` (Architecture and Code Quality) |
| diff | Architecture, security, and performance whenever code changed. Backend, frontend, or database only when changed files are in their domain. Testing when production code changed. DevOps when infra, CI, env, or Docker files changed |

Apply `--agents` and `--skip` last. Never run an agent twice on the same scope. Ownership rules are in `references/category-ownership.md`; the agents already carry them, so read that file only to settle a merge in Step 5.

## Step 4: Run the agents (in parallel)

Launch every selected agent **in one message**, one Agent call each, with `subagent_type: "917v-code-review:<agent-name>"`. Keep each prompt this short:

```
REVIEW REQUEST: <mode> review of <ROOT>
PLUGIN REFERENCES: <$P>/skills/comprehensive-review/references/
INPUTS FILE: <$WORK>/agents/<agent-name>.md
REVIEW BRIEF: <$WORK>/brief.md
AGENTS RUNNING IN THIS REVIEW: <list>
EXTRA INSTRUCTIONS: <only if any, e.g. "infrastructure-security items only", user focus, or large-repo prioritization>
Return ONLY the JSON object from the reviewer protocol.
```

For a large repository (more than about 1500 files), add: "prioritize the priority files and critical paths, and record what you did not cover in notes."

## Step 5: Consolidate, validate, de-duplicate

1. Save each agent's JSON **verbatim** to `$WORK/raw/<agent-name>.json`, with **all Writes in one message**. Fix only JSON syntax, never content. If an agent returned nothing parseable, record that as a limitation.
2. Validate:
   ```bash
   python3 "$P/scripts/validate-findings.py" --root "$ROOT" [--scope "$WORK/scope.json"] [--merges "$WORK/merges.json"] -o "$OUT/findings.json" "$WORK"/raw/*.json
   ```
   The validator rejects claims whose file, line, or evidence does not exist, fixes drifted lines, enforces the severity rules, redacts secrets, assigns IDs (`SEC-001`, …), and auto-merges only strong duplicates. It never merges on location alone.
3. **Merges.** For each pair in `merge_candidates` that shares a root cause and fix, add an entry to `$WORK/merges.json`, keeping the owner's record:
   ```json
   [{"keep": {"agent": "security-reviewer", "title": "<exact title>"},
     "merge": {"agent": "backend-reviewer", "title": "<exact title>"}, "reason": "same root cause: ..."}]
   ```
   Leave distinct issues unmerged.
4. **Reasoning check.** The script proves the evidence exists, not that the conclusion holds. For every Critical and High finding, and a sample of the rest, open the cited lines (all in one message). Confirm that the input is really controlled by the caller and that no global guard, pipe, middleware, or ORM parameterization already handles it. Delete wrong claims from the raw JSON. Downgrade uncertain ones to `Potential` and adjust severity and confidence per `references/severity-rubric.md`. Never add a finding you did not verify.
5. Read the `rejected` list. If a rejected item is a real issue at the wrong location, confirm the correct file, line, and evidence and fix the raw JSON.
6. Re-run the validator **once**, with `--merges` if you wrote merges and after all edits.

## Step 6: Summary and reports (one call)

Write `$WORK/summary.json` with the fields in `references/report-guide.md`: overall summary, health assessment, architecture and security overviews, OWASP notes, strategic recommendations with finding IDs, positives, and limitations. Base every statement on validated findings or on code you read. Then:

```bash
python3 "$P/scripts/render-reports.py" --root "$ROOT" --findings "$OUT/findings.json" --stack "$WORK/stack.json" \
  --summary "$WORK/summary.json" [--scope "$WORK/scope.json"] --baseline "$WORK/baseline.json" -o "$OUT" --html --widget "$WORK/chat-widget.html"
```

`--baseline` runs the read-only check in the same call; the result is in `read_only_check`. Omit `--html` for `--no-html`. `--widget` writes the in-chat results widget, which is scratch output, not a report. If the check reports changed files, say so prominently. The user may have edited files during the review; never hide it.

## Show the results in the chat (generative UI)

If this session has an inline visual tool that renders HTML in the conversation (for example `show_widget` from the `visualize` server on Claude Desktop or claude.ai):

1. Call its setup step (such as `read_me`) first if it has one, without mentioning it.
2. Read `$WORK/chat-widget.html` and pass its **entire contents, unchanged**, as the widget code, titled `code_review_<repository>` in snake_case. It is a branded 917 Ventures fragment with KPI cards, amCharts severity and category charts, a severity filter, and the top findings with "Explain ↗" buttons. It already follows the host widget rules.
3. Do not rebuild, restyle, or trim it. If the file is missing or the tool fails, skip this step and say so in one line.

Without such a tool, as in the terminal, skip this step.

The widget's buttons send messages as if the user typed them ("Explain finding SEC-004 …", "Make a prioritized fix plan …", "Open the full code review dashboard …"). Answer them from `findings.json` and the cited source. They do not lift the read-only rule. For the dashboard, open or attach `docs/code-review/dashboard.html` if the host can; otherwise give its path.

## Final message

Keep it short:
- The review type and scope, plus the agents run and skipped, with reasons.
- Counts by severity and the Confirmed/Potential split.
- The top 3–5 risks: ID, title, and `file:line`.
- Links to `docs/code-review/executive-summary.md`, `detailed-findings.md`, `security-review.md`, `architecture-review.md`, `recommendations.md`, `dashboard.html` (amCharts analytics), and `findings.json`.
- The read-only check and the validation stats (rejected and merged counts).
- That `docs/code-review/` is new output the user may commit or add to `.gitignore`. Do not do either yourself.
