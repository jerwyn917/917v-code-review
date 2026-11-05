---
description: Quick read-only scan in seconds — stack, pattern-based risk leads and import cycles, no reviewer agents. Writes docs/code-review/scan.md
argument-hint: "[path] [--staged | --branch <base> | --range <a>..<b>]"
---

Run the 917Ventures **quick scan**: a fast triage with the plugin's scripts only. No reviewer agents run and nothing is validated, so the output is **leads, not findings**.

Arguments: $ARGUMENTS

`ROOT` is the path argument, otherwise `git rev-parse --show-toplevel`, otherwise the current directory, as an absolute path. Run exactly one command, passing through any diff selector:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prepare-review.py" "<ROOT>" --mode scan [--staged | --branch <base> | --range a..b]
```

It writes `<ROOT>/docs/code-review/scan.md` (and scratch files in `.work/`, which are git-ignored) and prints the stack digest plus a JSON summary.

- **Exit code 3:** nothing changed for that selector. Say so, suggest the other selectors, and stop.
- **Exit code 4:** the project already has its own `docs/code-review/` folder. Nothing was written. Say so and stop; never move or delete it.
- **No `python3`:** say the quick scan needs Python 3, and stop.

Reply from the printed summary only. Do not open source files to judge the leads; that is what the full review does. Keep it short:
- The scope, files scanned, and stack in one line.
- A small table of leads by area.
- Up to five notable leads as `file:line` plus the hint, phrased as possible issues. Put Security first.
- The number of import cycles, if any.
- A link to `docs/code-review/scan.md`.
- The next step: `/917v-code-review:review` (or `review-diff` with the same selector), naming the agents from `recommended_agents`.

Rules: analysis only (never edit project files or apply fixes; the only output is new files under `docs/code-review/`), no network, never print secret values (they are already redacted), and never present a lead as a confirmed issue. `docs/code-review/` is new output the user may commit or add to `.gitignore`. Do not do either yourself.
