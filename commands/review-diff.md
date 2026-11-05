---
description: Review changed code only — uncommitted (default), staged, a branch vs its base, or a commit range
argument-hint: "[--staged | --branch <base> | --range <a>..<b>] [--agents a,b] [--no-html]"
---

Run the 917Ventures **Git diff review**.

Invoke the `917v-code-review:comprehensive-review` skill and follow it exactly, with:

- mode=diff
- arguments: $ARGUMENTS

Diff selectors:
- No selector: uncommitted changes. This means staged, unstaged, and untracked files compared with HEAD.
- `--staged`: only what is staged.
- `--branch <base>`: everything on the current branch since it diverged from `<base>`, e.g. `--branch main`. This is what a pull request contains.
- `--range <a>..<b>`: an explicit commit range.

The review is **analysis only**: it never edits project files, never applies fixes, and never stages, commits, stashes, or checks out anything. Its only output is new files in `docs/code-review/`.
