---
name: 917v-code-review
description: Run the 917Ventures standardized, read-only code review of a repository — full codebase, Git diff (uncommitted, staged, branch vs. base, or commit range), security-focused, or architecture-focused. Detects the stack, runs specialist reviewers (architecture, security, performance, backend, frontend, database, testing, devops), validates every finding against the source, de-duplicates, redacts secrets, and writes reports plus an HTML dashboard to docs/code-review/. Use when the user asks to "review this codebase", "code review the repo", "review my changes/diff/branch/PR", "security review", "OWASP review", "architecture review", "audit this code", or "917v code review".
---

# 917Ventures comprehensive code review (standalone skill)

You are the **orchestrator**. You run the deterministic scripts, brief the specialist reviewers, collect their findings, validate them, and write the reports. The specialist reviewers do the reviewing.

Skill root: the directory that contains this `SKILL.md` (Claude Code shows it as "Base directory for this skill"). Below it is called `$S`. Scripts: `$S/scripts/`. References: `$S/references/`. Reviewer briefs: `$S/references/reviewers/`. Report templates: `$S/templates/`.

## Non-negotiable rules

1. **Read-only.** Never modify, format, fix, or delete anything in the reviewed repository. Write only inside `<ROOT>/docs/code-review/`. Do not run builds, tests, migrations, package installs, or anything that writes outside that folder or changes Git state (no `git add/commit/stash/checkout/reset`). If the user asks for fixes, finish the review first, then tell them fixes are a separate step they must ask for.
2. **No network with source code.** Do not send code to external services, do not run `npm audit`, `pip-audit`, `snyk`, or similar online scanners, and do not fetch URLs, unless the user explicitly authorizes it in this conversation.
3. **No invented facts.** Every finding must cite a real file, a real line, and evidence copied from that line. Never present a hypothetical issue as a confirmed vulnerability. Never claim a test or command ran unless it did.
4. **Never expose secrets.** Redact secret values as `[REDACTED]` in evidence and in your messages. The scripts redact again as a safety net.
5. **Respect the existing design.** Prefer recommendations that fit the current architecture, avoid recommending new libraries unless genuinely necessary, and do not pad the report with trivia.

## Step 0: Parse the request and prepare

Work out the mode and options from the user's words or the arguments passed to the skill:

| User says / argument | mode |
|---|---|
| "review this repo", `full`, nothing | `full` (default) |
| "review my changes / diff / branch / PR", `diff` | `diff` |
| "security review", "OWASP", `security` | `security` |
| "architecture review", "code quality", `architecture` | `architecture` |

- `path`: directory to review. Default: the Git top level of the current directory (`git rev-parse --show-toplevel`), otherwise the current directory. If the user uploaded an archive, extract it into a new empty folder first and review that folder. Call the absolute path `ROOT`.
- Diff selectors: `--staged`, `--branch <base>` (e.g. "against main"), `--range <a>..<b>`. No selector means uncommitted changes, including untracked files.
- `--agents a,b` restricts the reviewers. `--skip a,b` removes reviewers. `--no-html` skips the dashboard.

Set `OUT=<ROOT>/docs/code-review` and `WORK=$OUT/.work`. Shell variables do not persist between Bash calls, so write `$S`, `$ROOT`, `$OUT`, and `$WORK` as literal absolute paths, quoted, in every command below. Then run `python3 --version` and `mkdir -p "$WORK/raw"` as two separate commands. Create `$WORK/.gitignore` containing `*`, so the scratch files are never committed.

If `python3` is missing, tell the user. Continue in **manual mode**: do every step by reading files directly, write the reports by hand in the format of `$S/templates/`, and state in the executive summary that automated validation was unavailable.

If `$OUT` already has reports from an earlier run, they will be replaced. Say so in your final message. They are this skill's own output, not project files.

## Step 1: Baseline (proves read-only)

```bash
python3 "$S/scripts/integrity.py" snapshot "$ROOT" -o "$WORK/baseline.json"
```

## Step 2: Inspect the structure and identify the stack

```bash
python3 "$S/scripts/detect-stack.py" "$ROOT" -o "$WORK/stack.json" --files-out "$WORK/files.txt" --brief
```

The `--brief` digest on stderr is enough for most decisions. Read specific keys of `stack.json` only when needed. A framework marked `[manifest-only]` is declared but has no usage found in source. Treat it as unconfirmed and never assume a framework from folder names.

## Step 3: Entry points, critical modules, documentation and standards

- Read the README and any coding-standards documents listed under `docs/standards`, such as CONTRIBUTING, CLAUDE.md, ADRs, and lint or format configs. Skim them; do not read huge files fully. Note the conventions reviewers must respect, such as the error-handling pattern, layering rules, or naming.
- From `stack.json` take the `entry_points` and `critical_paths`, which cover security-sensitive files, business-critical files, request handlers, and data access. Open the main entry points to understand how the app is wired (module registration, routing, DI, middleware).
- Write a **review brief** of 10–25 lines: what the system does, its stack, layout, main modules, conventions, and the 10–30 files most worth reviewing. Every reviewer receives it.

## Step 4: Identify the review scope

- **full / security / architecture**: the whole repository, honoring .gitignore. Vendored and build directories are excluded automatically.
- **diff**:
  ```bash
  python3 "$S/scripts/diff-scope.py" "$ROOT" [--staged | --branch <base> | --range a..b] -o "$WORK/scope.json"
  ```
  If `files_changed` is 0, tell the user there is nothing to review for that selector, suggest the other selectors, and stop without writing reports.

Then collect the hint data. These are unverified starting points, not findings:

```bash
python3 "$S/scripts/scan-signals.py" "$ROOT" [--scope "$WORK/scope.json"] -o "$WORK/signals.json"
python3 "$S/scripts/import-graph.py" "$ROOT" -o "$WORK/import-graph.json"   # full + architecture modes
```

## Step 5: Select the reviewers

Reviewer ownership and the no-overlap rules are in `$S/references/category-ownership.md`. Read it once.

| Mode | Reviewers |
|---|---|
| full | `recommended_agents` from stack.json; `skipped_agents` are not run, and their reasons go in the report |
| security | `security-reviewer`. Add `devops-reviewer` with the instruction "infrastructure-security items only" when infrastructure or CI was detected |
| architecture | `architecture-reviewer`, which covers Architecture and Code Quality |
| diff | the recommended reviewers whose domain the changed files touch: architecture, security, and performance whenever code changed; backend, frontend, or database only when changed files are in their domain; testing when production code changed; devops when infra/CI/env/Docker files changed |

Apply `--agents` and `--skip` last. Never run the same reviewer twice on the same scope.

Each reviewer's brief is `$S/references/reviewers/<reviewer-name>.md` (architecture, security, performance, backend, frontend, database, testing, devops).

## Step 6: Execute the specialist reviewers

Build this **context block** once per reviewer:

```
REVIEW REQUEST: <mode> review
ROOT: <absolute path>
SKILL REFERENCES: <absolute $S>/references/
REVIEWER BRIEF: <absolute $S>/references/reviewers/<reviewer-name>.md
REVIEWERS RUNNING IN THIS REVIEW: <list>  (do not report topics owned by these other reviewers)
REVIEW BRIEF:
<the brief from step 3>
STACK: <the --brief digest>
SCOPE: <"whole repository"  |  diff: list of changed files with line ranges from scope.json>
FILE INVENTORY: <$WORK/files.txt> (every reviewable file; use it if search tools are unavailable)
PRIORITY FILES: <entry points + critical files relevant to this reviewer>
SIGNALS FOR YOU: <the signals.json entries whose agent == this reviewer: rule, file:line, hint; at most 40, or say to read signals.json and filter by agent>
IMPORT CYCLES: <architecture-reviewer only: cycles from import-graph.json>
EXTRA INSTRUCTIONS: <e.g. "infrastructure-security items only", user focus areas>
Return ONLY the JSON object described in references/finding-schema.md.
```

**If you can launch subagents (the Agent / Task tool is available):** launch every selected reviewer **in one message**, one call each, in parallel, using the general-purpose subagent. Each prompt starts with:

> You are the `<reviewer-name>` in a read-only code review. First read `<REVIEWER BRIEF path>` and follow it exactly, together with the reviewer protocol it points to. Use only reading and searching tools (Read, Grep, Glob, or read-only shell such as `cat`, `grep`, `ls`). Do not create, edit, or delete any file, do not run builds, tests, or package managers, and do not use the network.

followed by the context block. The subagents start with no context, so the prompt must be complete.

**If you cannot launch subagents** (for example in claude.ai): run the reviewers yourself, **one at a time**. For each one, read its brief and `$S/references/reviewer-protocol.md`, review with that brief as your only lens, write its JSON straight to `$WORK/raw/<reviewer-name>.json`, then move to the next. Keep each reviewer's findings inside its own categories.

In diff mode, tell reviewers to review the changed lines and their immediate call context. They should report pre-existing issues outside the changed lines only when those issues are Critical/High or directly interact with the change.

For a large repository (`file_count` above ~1500), tell each reviewer to prioritize the priority files and its domain's critical paths, and to record what it did not cover in `notes`. Do not pretend coverage that did not happen.

## Step 7: Consolidate

For each reviewer result, extract the JSON object and save it **verbatim** to `$WORK/raw/<reviewer-name>.json`. If the JSON is malformed, fix only the syntax, never the content. If a reviewer returned no parseable result, record that as a limitation.

## Steps 8–9: De-duplicate and validate against the source

```bash
python3 "$S/scripts/validate-findings.py" --root "$ROOT" [--scope "$WORK/scope.json"] [--merges "$WORK/merges.json"] -o "$OUT/findings.json" "$WORK"/raw/*.json
```

The validator:
- rejects findings whose file, line, or evidence does not exist;
- corrects line numbers when the evidence is elsewhere in the file;
- enforces the severity rules in `references/severity-rubric.md`;
- redacts secrets, including secret values quoted in free text;
- assigns IDs (`SEC-001`, `ARC-002`, …).

It **auto-merges only strong duplicates**: the same location with a similar title, the same CWE, or the same category; or the same issue repeated across files. Different issues often sit on the same lines, such as an N+1 loop and a missing index, so the validator never merges on location alone.

**De-duplication decision.** Read `merge_candidates` in `findings.json`. These are pairs from different reviewers whose cited lines overlap. For each pair, decide whether they share a root cause and fix. Record only the true duplicates in `$WORK/merges.json`, keeping the record whose category owns the topic (`references/category-ownership.md`):

```json
[{"keep": {"agent": "security-reviewer", "title": "<exact title>"},
  "merge": {"agent": "backend-reviewer", "title": "<exact title>"},
  "reason": "same root cause: ..."}]
```

Re-run the validator with `--merges`. The kept record takes the higher severity, lists both reviewers in `reported_by`, and records the merge in `validation_notes`. Leave distinct issues unmerged.

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
python3 "$S/scripts/integrity.py" verify "$ROOT" "$WORK/baseline.json" -o "$WORK/integrity.json"
python3 "$S/scripts/render-reports.py" --root "$ROOT" --findings "$OUT/findings.json" --stack "$WORK/stack.json" \
  --summary "$WORK/summary.json" [--scope "$WORK/scope.json"] --integrity "$WORK/integrity.json" -o "$OUT" --html
```

Omit `--html` when `--no-html` was requested. If the integrity check reports changes, report them prominently. They may come from the user editing files during the review; never hide them.

## Final message to the user

Keep it short:
- The review type and scope, and the reviewers run and skipped, each with a reason.
- Finding counts by severity, and the Confirmed/Potential split.
- The top 3–5 risks: ID, title, and `file:line`.
- Links to `docs/code-review/executive-summary.md`, `detailed-findings.md`, `security-review.md`, `architecture-review.md`, `recommendations.md`, `dashboard.html`, and `findings.json`.
- The read-only check result and the validation stats (rejected and merged counts).
- That `docs/code-review/` is new output the user may want to commit or add to `.gitignore`. Do not do either yourself.
