---
name: comprehensive-review
description: Run the 917Ventures standardized, read-only code review of a repository — full codebase, Git diff (uncommitted, staged, or branch), security-focused, or architecture-focused. Detects the stack, dispatches the 917v-code-review specialist agents, validates every finding against the source, de-duplicates, and writes reports to docs/code-review/. Use when the user asks to "review this codebase", "code review the repo", "review my changes/diff/branch", "security review", "architecture review", or runs a /917v-code-review command.
argument-hint: "mode=full|diff|security|architecture [path] [--staged | --branch <base> | --range a..b] [--agents a,b] [--skip a,b] [--no-html]"
---

# 917Ventures comprehensive code review

You are the **orchestrator**. You run the deterministic scripts, brief the specialist agents, collect their findings, validate them, and write the reports. The specialist agents do the reviewing.

Plugin root: `${CLAUDE_PLUGIN_ROOT}` (below: `$P`). Scripts: `$P/scripts/`. References: `$P/skills/comprehensive-review/references/`.

## Non-negotiable rules

1. **Read-only.** Never modify, format, fix, or delete anything in the reviewed repository. Write only inside `<ROOT>/docs/code-review/`. Do not run builds, tests, migrations, package installs, or anything that writes outside that folder or changes Git state (no `git add/commit/stash/checkout/reset`). If the user asks for fixes, finish the review first, then tell them fixes are a separate step they must ask for.
2. **No network with source code.** Do not send code to external services, do not run `npm audit`, `pip-audit`, `snyk`, or similar online scanners, and do not fetch URLs, unless the user explicitly authorizes it in this conversation.
3. **No invented facts.** Every finding must cite a real file, a real line, and evidence copied from that line. Never present a hypothetical issue as a confirmed vulnerability. Never claim a test or command ran unless it did.
4. **Never expose secrets.** Redact secret values as `[REDACTED]` in evidence and in your messages. The scripts redact again as a safety net.
5. **Respect the existing design.** Prefer recommendations that fit the current architecture, avoid recommending new libraries unless genuinely necessary, and do not pad the report with trivia.

## Step 0: Parse the request and prepare

Parse the arguments. Commands pass `mode=...` first.
- `mode`: `full` (default), `diff`, `security`, `architecture`.
- `path`: directory to review. Default: the Git top level of the current directory (`git rev-parse --show-toplevel`), otherwise the current directory. Call its absolute path `ROOT`.
- Diff selectors: `--staged`, `--branch <base>`, `--range <a>..<b>`. No selector means uncommitted changes, including untracked files.
- `--agents a,b` restricts the agents. `--skip a,b` removes agents. `--no-html` skips the dashboard.

Set `OUT=<ROOT>/docs/code-review` and `WORK=$OUT/.work`. Shell variables do not persist between Bash calls, so write `$P`, `$ROOT`, `$OUT`, and `$WORK` as literal absolute paths, quoted, in every command below. Then run `python3 --version` and `mkdir -p "$WORK/raw"` as two separate commands. Use the Write tool to create `$WORK/.gitignore` containing `*`, so the scratch files are never committed.

If `python3` is missing, tell the user. Continue in **manual mode**: do every step with Read/Grep/Glob, write the reports by hand in the format of `$P/templates/`, and state in the executive summary that automated validation was unavailable.

If `$OUT` already has reports from an earlier run, they will be replaced. Say so in your final message. They are this plugin's own output, not project files.

## Step 1: Baseline (proves read-only)

```bash
python3 "$P/scripts/integrity.py" snapshot "$ROOT" -o "$WORK/baseline.json"
```

## Step 2: Inspect the structure and identify the stack

```bash
python3 "$P/scripts/detect-stack.py" "$ROOT" -o "$WORK/stack.json" --files-out "$WORK/files.txt" --brief
```

The `--brief` digest on stderr is enough for most decisions. Read specific keys of `stack.json` only when needed. A framework marked `[manifest-only]` is declared but has no usage found in source. Treat it as unconfirmed and never assume a framework from folder names.

## Step 3: Entry points, critical modules, documentation and standards

- Read the README and any coding-standards documents listed under `docs/standards`, such as CONTRIBUTING, CLAUDE.md, ADRs, and lint or format configs. Skim them; do not read huge files fully. Note the conventions reviewers must respect, such as the error-handling pattern, layering rules, or naming.
- From `stack.json` take the `entry_points` and `critical_paths`, which cover security-sensitive files, business-critical files, request handlers, and data access. Open the main entry points to understand how the app is wired (module registration, routing, DI, middleware).
- Write a **review brief** of 10–25 lines: what the system does, its stack, layout, main modules, conventions, and the 10–30 files most worth reviewing. Every agent receives it.

## Step 4: Identify the review scope

- **full / security / architecture**: the whole repository, honoring .gitignore. Vendored and build directories are excluded automatically.
- **diff**:
  ```bash
  python3 "$P/scripts/diff-scope.py" "$ROOT" [--staged | --branch <base> | --range a..b] -o "$WORK/scope.json"
  ```
  If `files_changed` is 0, tell the user there is nothing to review for that selector, suggest the other selectors, and stop without writing reports.

Then collect the hint data. These are unverified starting points, not findings:

```bash
python3 "$P/scripts/scan-signals.py" "$ROOT" [--scope "$WORK/scope.json"] -o "$WORK/signals.json"
python3 "$P/scripts/import-graph.py" "$ROOT" -o "$WORK/import-graph.json"   # full + architecture modes
```

## Step 5: Select the agents

Agent ownership and the no-overlap rules are in `references/category-ownership.md`. Read it once.

| Mode | Agents |
|---|---|
| full | `recommended_agents` from stack.json; `skipped_agents` are not run, and their reasons go in the report |
| security | `security-reviewer`. Add `devops-reviewer` with the instruction "infrastructure-security items only" when infrastructure or CI was detected |
| architecture | `architecture-reviewer`, which covers Architecture and Code Quality |
| diff | the recommended agents whose domain the changed files touch: architecture, security, and performance whenever code changed; backend, frontend, or database only when changed files are in their domain; testing when production code changed; devops when infra/CI/env/Docker files changed |

Apply `--agents` and `--skip` last. Never run the same agent twice on the same scope.

## Step 6: Execute the specialist agents (in parallel)

Launch all selected agents **in one message**, one Agent tool call each, with `subagent_type: "917v-code-review:<agent-name>"`. Each prompt must contain the following. The agents start with no context.

```
REVIEW REQUEST: <mode> review
ROOT: <absolute path>
PLUGIN REFERENCES: <absolute $P>/skills/comprehensive-review/references/
AGENTS RUNNING IN THIS REVIEW: <list>  (do not report topics owned by these other agents)
REVIEW BRIEF:
<the brief from step 3>
STACK: <the --brief digest>
SCOPE: <"whole repository"  |  diff: list of changed files with line ranges from scope.json>
FILE INVENTORY: <$WORK/files.txt> (every reviewable file; use it if Grep/Glob are unavailable)
PRIORITY FILES: <entry points + critical files relevant to this agent>
SIGNALS FOR YOU: <the signals.json entries whose agent == this agent: rule, file:line, hint; at most 40, or tell the agent to read signals.json and filter by agent>
IMPORT CYCLES: <architecture-reviewer only: cycles from import-graph.json>
EXTRA INSTRUCTIONS: <e.g. "infrastructure-security items only", user focus areas>
Return ONLY the JSON object described in references/finding-schema.md.
```

In diff mode, tell agents to review the changed lines and their immediate call context. They should report pre-existing issues outside the changed lines only when those issues are Critical/High or directly interact with the change.

For a large repository (`file_count` above ~1500), tell each agent to prioritize the priority files and its domain's critical paths, and to record what it did not cover in `notes`. Do not pretend coverage that did not happen.

## Step 7: Consolidate

For each agent result, extract the JSON object and save it **verbatim** with the Write tool to `$WORK/raw/<agent-name>.json`. If the JSON is malformed, fix only the syntax, never the content. If an agent returned no parseable result, record that as a limitation.

## Steps 8–9: De-duplicate and validate against the source

```bash
python3 "$P/scripts/validate-findings.py" --root "$ROOT" [--scope "$WORK/scope.json"] [--merges "$WORK/merges.json"] -o "$OUT/findings.json" "$WORK"/raw/*.json
```

The validator:
- rejects findings whose file, line, or evidence does not exist;
- corrects line numbers when the evidence is elsewhere in the file;
- enforces the severity rules in `references/severity-rubric.md`;
- redacts secrets, including secret values quoted in free text;
- assigns IDs (`SEC-001`, `ARC-002`, …).

It **auto-merges only strong duplicates**: the same location with a similar title, the same CWE, or the same category; or the same issue repeated across files. Different issues often sit on the same lines, such as an N+1 loop and a missing index, so the validator never merges on location alone.

**De-duplication decision.** Read `merge_candidates` in `findings.json`. These are pairs from different agents whose cited lines overlap. For each pair, decide whether they share a root cause and fix. Record only the true duplicates in `$WORK/merges.json`, keeping the record whose category owns the topic (`references/category-ownership.md`):

```json
[{"keep": {"agent": "security-reviewer", "title": "<exact title>"},
  "merge": {"agent": "backend-reviewer", "title": "<exact title>"},
  "reason": "same root cause: ..."}]
```

Re-run the validator with `--merges`. The kept record takes the higher severity, lists both agents in `reported_by`, and records the merge in `validation_notes`. Leave distinct issues unmerged.

**Reasoning check.** The script proves the evidence exists, not that the conclusion is right. Do this yourself for every Critical and High finding, and for a sample of the others:
- Open the cited lines and confirm the claim.
- Ask whether the input is really user-controlled.
- Look for a guard elsewhere, such as global middleware, a validation pipe, or ORM parameterization.

If a claim is wrong, delete it from the raw JSON. If it is uncertain, set `status` to `Potential` and adjust `severity` and `confidence` per the rubric. Then re-run the validator. Do not add findings you did not verify.

Read the `rejected` list. If a rejected item is a real issue with a wrong location, confirm the correct file, line, and evidence in the source, fix them in the raw JSON, and re-run.

## Step 10: Write the summary and generate the reports

Write `$WORK/summary.json` (fields in `references/report-guide.md`). It holds the narrative: overall summary, health assessment, architecture and security overviews, OWASP notes, strategic recommendations that reference finding IDs, positive observations, and limitations. Base every statement on validated findings or on code you read.

Verify read-only, then render:

```bash
python3 "$P/scripts/integrity.py" verify "$ROOT" "$WORK/baseline.json" -o "$WORK/integrity.json"
python3 "$P/scripts/render-reports.py" --root "$ROOT" --findings "$OUT/findings.json" --stack "$WORK/stack.json" \
  --summary "$WORK/summary.json" [--scope "$WORK/scope.json"] --integrity "$WORK/integrity.json" -o "$OUT" --html --widget "$WORK/chat-widget.html"
```

Omit `--html` when `--no-html` was requested. `--widget` writes the in-chat results widget used in the final message; it is scratch output, not a report. If the integrity check reports changes, report them prominently. They may come from the user editing files during the review; never hide them.

## Show the results in the chat (generative UI)

When this session has an inline visual tool that renders HTML in the conversation (for example `show_widget` from the `visualize` server on Claude Desktop or claude.ai), show the results there before the text summary:

1. If the tool has a setup step (such as `read_me`), call it first and do not mention it.
2. Read `$WORK/chat-widget.html` and pass its **entire contents, unchanged**, as the widget code, titled `code_review_<repository>` in snake_case. It is a branded 917 Ventures fragment: KPI cards, amCharts severity and category charts, a severity filter, and the top findings, each with an "Explain ↗" button. It follows the host widget rules: fragment only, host theme tokens, no comments, and HTML bars if amCharts cannot load.
3. Do not rebuild, restyle, or trim the fragment. If the file is missing or the tool fails, skip this step and say so in one line.

Without such a tool, as in the Claude Code terminal, skip this step. The text summary below covers the same results.

Buttons in the widget send messages to the chat as if the user typed them: "Explain finding SEC-004 …", "Make a prioritized fix plan …", "Open the full code review dashboard …". Answer them from `findings.json` and the cited source, and keep the read-only rule. Explaining or planning a fix is not permission to edit files. For the dashboard, open or attach `docs/code-review/dashboard.html` if the host can, otherwise give its path.

## Final message to the user

Keep it short:
- The review type and scope, and the agents run and skipped, each with a reason.
- Finding counts by severity, and the Confirmed/Potential split.
- The top 3–5 risks: ID, title, and `file:line`.
- Links to `docs/code-review/executive-summary.md`, `detailed-findings.md`, `security-review.md`, `architecture-review.md`, `recommendations.md`, `dashboard.html` (amCharts analytics), and `findings.json`.
- The read-only check result and the validation stats (rejected and merged counts).
- That `docs/code-review/` is new output the user may want to commit or add to `.gitignore`. Do not do either yourself.
