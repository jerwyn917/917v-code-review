---
description: Quick read-only scan in seconds — stack, pattern-based risk leads and import cycles, no reviewer agents. Writes docs/code-review/scan.md
argument-hint: "[path] [--staged | --branch <base> | --range <a>..<b>]"
---

Run the 917Ventures **quick scan**: a fast triage of the repository using only the plugin's deterministic scripts. No reviewer agents run, nothing is validated, and the output is **leads, not findings**. Use it to decide where a full review is needed. Use `/917v-code-review:review` for validated findings.

Arguments: $ARGUMENTS

## Rules

- **Read-only.** Write only inside `<ROOT>/docs/code-review/`. Do not modify, format, build, test, install, or change Git state.
- **No network.** Do not run online scanners or send code anywhere.
- **Never present a lead as a confirmed issue.** Say "possible", "lead", or "worth checking". Secret values are already redacted; never print them.

## Steps

Plugin root: `${CLAUDE_PLUGIN_ROOT}` (below: `$P`). Shell variables do not persist between Bash calls, so write `$P`, `$ROOT`, `$OUT`, and `$WORK` as literal absolute paths, quoted, in every command.

1. `ROOT`: the path argument, otherwise the Git top level of the current directory (`git rev-parse --show-toplevel`), otherwise the current directory. Set `OUT=<ROOT>/docs/code-review` and `WORK=$OUT/.work`. Run `mkdir -p "$WORK"`, then use the Write tool to create `$WORK/.gitignore` containing `*`. If `python3` is missing, tell the user the quick scan needs Python 3 and stop.
2. Detect the stack:
   ```bash
   python3 "$P/scripts/detect-stack.py" "$ROOT" -o "$WORK/stack.json" --files-out "$WORK/files.txt" --brief
   ```
3. Diff selectors only (`--staged`, `--branch <base>`, `--range a..b`): limit the scan to the changed files.
   ```bash
   python3 "$P/scripts/diff-scope.py" "$ROOT" [--staged | --branch <base> | --range a..b] -o "$WORK/scope.json"
   ```
   If `files_changed` is 0, say there is nothing to scan for that selector and stop. Without a selector, scan the whole repository and do not create `scope.json`.
4. Collect leads and the import graph:
   ```bash
   python3 "$P/scripts/scan-signals.py" "$ROOT" [--scope "$WORK/scope.json"] -o "$WORK/signals.json"
   python3 "$P/scripts/import-graph.py" "$ROOT" -o "$WORK/import-graph.json"
   ```
5. Render the report:
   ```bash
   python3 "$P/scripts/render-scan.py" --root "$ROOT" --stack "$WORK/stack.json" --signals "$WORK/signals.json" \
     --imports "$WORK/import-graph.json" [--scope "$WORK/scope.json"] -o "$OUT"
   ```
   It writes `$OUT/scan.md` and prints a JSON summary. Use that summary for your reply; you do not need to read the signals file.

## Reply

Keep it short and do not open source files to judge the leads. That is what the full review does.

- The scope, files scanned, and the stack in one line.
- A small table of leads by area, with counts.
- Up to five notable leads as `file:line` plus the hint, phrased as leads. Favour Security first, then DevOps, Database, and the others.
- The number of import cycles, if any.
- A link to `docs/code-review/scan.md`.
- The next step: `/917v-code-review:review` (or `/917v-code-review:review-diff` with the same selector) to confirm or reject the leads. Name the agents it would run, from `recommended_agents`.
- That `docs/code-review/` is new output the user may want to commit or add to `.gitignore`. Do not do either yourself.
