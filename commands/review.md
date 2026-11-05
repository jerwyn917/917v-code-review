---
description: Full read-only code review of the repository (all relevant specialist agents) with reports in docs/code-review/
argument-hint: "[path] [--agents a,b] [--skip a,b] [--no-html]"
---

Run the 917Ventures **full codebase review**.

Invoke the `917v-code-review:comprehensive-review` skill and follow it exactly, with:

- mode=full
- arguments: $ARGUMENTS

If no path is given, review the current repository root. The review is **analysis only**: it never creates, edits, or deletes project files and never applies fixes. Its only output is new files in `docs/code-review/`.
