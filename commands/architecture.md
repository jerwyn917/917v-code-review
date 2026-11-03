---
description: Architecture and code-quality focused read-only review (SOLID, DRY, layering, dependencies, circular imports, modularity)
argument-hint: "[path] [--no-html]"
---

Run the 917Ventures **architecture-focused review**.

Invoke the `917v-code-review:comprehensive-review` skill and follow it exactly, with:

- mode=architecture
- arguments: $ARGUMENTS

Only `architecture-reviewer` runs. It covers the Architecture and Code Quality categories and is given the import-cycle analysis from `scripts/import-graph.py`. The review is read-only.
