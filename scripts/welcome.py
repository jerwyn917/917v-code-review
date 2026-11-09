#!/usr/bin/env python3
"""SessionStart hook: after the plugin is installed, offer to run one of its commands.

On the first session start after installation this prints a SessionStart hook
result whose `additionalContext` tells Claude to ask the user, with the
AskUserQuestion tool, whether to run a 917v-code-review command now. It then
writes a marker so the offer is made only once.

The marker lives in ${CLAUDE_PLUGIN_DATA} (Claude Code's persistent per-plugin
folder, removed on uninstall, so a reinstall offers again). Without that
variable it falls back to ~/.917v-code-review/. Override with
CODE_REVIEW_WELCOME_DIR (used by the tests).

Never touches the current project, needs no network, and never fails the
session: any error is swallowed and the hook prints nothing.
"""

import json
import os
import sys

MARKER = ".welcomed"

CONTEXT = """\
The 917v-code-review plugin was just installed. Make this offer once, at the start of your first reply in this session:

- If the user's first message already asks for a code review, diff review, security or architecture review, or scan, skip the offer and just do what they asked.
- Otherwise, before anything else, call the AskUserQuestion tool with one question (header "Code review"):
  "917v-code-review is installed. Run one of its commands on this repository now? (Security and architecture reviews are also available: type them under Other.)"
  with these options, in this order:
  1. "Quick scan" - /917v-code-review:scan: stack, risk leads and import cycles in seconds, no reviewer agents.
  2. "Review my changes" - /917v-code-review:review-diff: review only uncommitted changes (or a branch / commit range).
  3. "Full review" - /917v-code-review:review: every relevant specialist reviewer, validated findings, reports and a dashboard.
  4. "Not now" - do nothing; the commands stay available any time.
- If the user picks a command (including "security" -> /917v-code-review:security or "architecture" -> /917v-code-review:architecture typed under Other), run it with the Skill tool (skill "917v-code-review:scan", "917v-code-review:review-diff", "917v-code-review:review", "917v-code-review:security" or "917v-code-review:architecture") and then continue with the user's original message.
- If they pick "Not now", say in one line that the commands are /917v-code-review:scan, :review-diff, :review, :security and :architecture, then carry on with their message.
- All commands are read-only: they never modify the repository and write reports outside it.
"""


def marker_dir():
    for var in ("CODE_REVIEW_WELCOME_DIR", "CLAUDE_PLUGIN_DATA"):
        if os.environ.get(var):
            return os.environ[var]
    return os.path.join(os.path.expanduser("~"), ".917v-code-review")


def main():
    try:
        sys.stdin.read()                        # drain the hook payload; nothing in it is needed
    except Exception:
        pass
    try:
        folder = marker_dir()
        marker = os.path.join(folder, MARKER)
        if os.path.exists(marker):
            return 0
        os.makedirs(folder, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write("offered\n")
    except Exception:
        return 0                                # cannot record the offer: stay silent rather than repeat it
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": CONTEXT},
        "systemMessage": "917v-code-review installed: Claude will offer to run a scan or review.",
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
