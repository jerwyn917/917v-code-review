---
description: Architecture and code-quality focused read-only review (SOLID, DRY, layering, dependencies, circular imports, modularity)
argument-hint: "[path | GitHub link] [--no-html]"
---

Run the 917Ventures **architecture-focused review**.

Invoke the `917v-code-review:comprehensive-review` skill and follow it exactly, with:

- mode=architecture
- arguments: $ARGUMENTS

A public GitHub link (`https://github.com/<owner>/<repo>`) can be given instead of a path; it is downloaded to `~/.917v-code-review/repos/` and reviewed from there. Only `architecture-reviewer` runs. It covers the Architecture and Code Quality categories and is given the import-cycle analysis from `scripts/import-graph.py`. The review is **analysis only**: it never edits project files or applies fixes.
