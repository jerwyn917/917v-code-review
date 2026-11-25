# Changelog

All notable changes to this plugin are documented here. Versions follow [Semantic Versioning](https://semver.org/). The version in `.claude-plugin/plugin.json` is the source of truth.

## [Unreleased]

### Added
- **Git history and attribution for security findings** (`scripts/git-history.py`, called by `validate-findings.py`). Each security finding gets a `git` object: `introduced` (the commit where the cited code first appeared) and `last_changed` (the latest commit that changed it), each with author, committer, commit hash, date, and subject, plus the traced lines. `git_attribution` summarizes the run. Read-only Git only (`blame` joins the allowlist); nothing is guessed when history is unavailable, untracked, uncommitted, or shallow. `--no-git-history` skips it.
- **Standard finding sections everywhere**: Title, Description, Evidence, Potential Impact, Recommended Solution, Reference, and Git History when traced, with the same labels in the dashboard, Explore, and the Markdown reports. Reference now links to the CWE entry and the OWASP Top 10 page named by the finding.
- `security-review.md` has a "Git history of the security findings" table.

### Changed
- Dashboard findings list redesigned: each finding is a card with a clear header (severity, ID, category, status, title, location) and, when opened, a facts row and the standard sections with consistent spacing and typography. Bodies are built on first open, "Expand all / Collapse all" was added, and search matches author names and commit hashes.
- Explore's detail panel uses the same sections and labels; the cited location and its "open" actions now sit in Evidence.

### Added (earlier in this release)
- **One-click Explore and dashboard from the results widget.** The widget's "Explore" and "Open the full dashboard" buttons are now real links that open the pages in the browser directly, with no chat message.
  - `scripts/serve-reports.py` is a loopback-only viewer for one report folder: `127.0.0.1`, a free port, a random token in every URL, `GET` only, auto-stop after two idle hours, reused by later renders.
  - `render-reports.py --serve` starts or reuses it, writes its links into the widget, and prints them under `viewer` for the final message.
  - Opened through the viewer, Explore's "View file at line N" shows the file in a read-only, line-numbered page with the cited lines highlighted and secret values redacted.
  - Where a local server cannot start, the buttons fall back to asking in chat.
- **Explore**: `render-reports.py --html` now also writes `explore.html`, the review's findings as an interactive floor plan (`templates/explore.html`).
  - Wings are directories, rooms are files, tiles are findings. Arrange by files, categories, or severity; pan, zoom, minimap; search; filters for severity, category, file, and status.
  - A detail panel shows every field of the selected finding, with previous/next, "Open in VS Code / Cursor", "View file", and "Copy location". Missing file or line metadata is stated, never invented.
  - The page draws only the validated findings from `findings.json`. A test checks that its data equals them exactly.
  - Motion: GSAP 3.13.0 for the camera and layout, Motion 12.23.24 (vanilla Framer Motion) for the panel; the page works offline and with reduced motion.
  - The results widget has a new "Explore ↗" button next to "Open the full dashboard ↗". The dashboard and Explore link to each other, per finding too (`explore.html#<ID>`, `dashboard.html#<ID>`).
- Post-install offer: a `SessionStart` hook (`hooks/hooks.json` → `scripts/welcome.py`) runs once after the plugin is installed and has Claude ask, with the AskUserQuestion tool, whether to run a command now (Quick scan, Review my changes, Full review, Not now; security and architecture under Other). The marker lives in `${CLAUDE_PLUGIN_DATA}` (fallback `~/.917v-code-review/`), so it asks once per install. The standalone skill asks the same question when it is invoked with no request.
- `/917v-code-review:scan`: quick read-only triage that runs only the deterministic scripts (stack detection, pattern leads, import cycles; optional diff selectors) and writes `docs/code-review/scan.md` via the new `scripts/render-scan.py`. No reviewer agents, so results are leads, not findings. The standalone skill gets the same `scan` mode.
- Dashboard analytics with amCharts 5 (5.21.5, cdnjs) in 917 Ventures branding: health gauge, severity donut, category × severity bars, OWASP Top 10 columns, hotspot files, and a reviewer × severity heatmap. Chart clicks cross-filter the findings list. Light and dark themes; HTML-bar fallback offline.
- In-chat results widget (generative UI): `render-reports.py --widget` writes `.work/chat-widget.html`, which the orchestrator renders with the host's inline visual tool when one is available. It has KPI cards, amCharts charts, a severity filter, and `sendPrompt` buttons ("Explain ↗", fix plan, open dashboard).
- `templates/assets/917v-logo.datauri`: 917 Ventures logo for the dashboard header.
- Standalone Agent Skill build: `tools/build-skill.py` packages the review as `dist/917v-code-review/` and `dist/917v-code-review.zip` for `~/.claude/skills/`, claude.ai, or the API. Orchestrator in `skill-src/SKILL.md`; agents become reviewer briefs in `references/reviewers/`, run as read-only general-purpose subagents or sequentially where subagents are unavailable.
- `render-reports.py` reads the version from a `VERSION` file when `.claude-plugin/plugin.json` is absent (skill layout).
- `tests/test_build_skill.py`.

### Changed
- Reports are written **outside the reviewed repository**, by default to `~/.917v-code-review/reviews/<repo>-<id>/`. Override with `--out <dir>` or the `CODE_REVIEW_OUT_DIR` base folder. Nothing is created inside the repository any more (no `docs/code-review/`), so `git status` stays clean.
  - Every script refuses any output path inside the repository.
  - A non-empty folder the review did not create is never written to (exit code 4).
  - Source links in the reports are relative to the report folder.
  - The integrity check now covers every repository file, with no exclusions.
- Stricter analysis-only guarantees:
  - Git runs only allowlisted read-only subcommands, with `GIT_OPTIONAL_LOCKS=0`, so `git status` and `git diff` no longer rewrite `.git/index`.
  - The report folder is claimed with a `.917v-code-review` marker.
  - Skills, commands, and the reviewer protocol now say the review never edits files or applies fixes, even when asked mid-review.
- Faster reviews and scans, with fewer round trips and less instruction text to read:
  - `scripts/prepare-review.py` replaces about 8 orchestrator calls (baseline, stack, scope, signals, import graph, work-dir setup) with one. It also writes a per-agent inputs file (`.work/agents/<agent>.md`: stack digest, scope, priority files, that agent's signals, matching stack-checklist sections), so agent prompts are a few lines instead of hand-assembled context.
  - `render-reports.py --baseline` runs the read-only integrity check in the same call as rendering.
  - `/917v-code-review:scan` is now a single `prepare-review.py --mode scan` call.
  - `reviewer-protocol.md` is self-contained (output contract, severity rules, ownership tie-breakers) and adds speed rules: read the protocol and inputs in one parallel step, batch independent reads, Grep before Read, and a 10–30 call budget. Agents no longer read four further reference files.
  - Both orchestrator `SKILL.md` files are rewritten around these calls, with speed rules for parallel tool use and a single final validator run.
- `render-reports.py` checks template placeholders against the template, not the filled output, so finding text containing `{{...}}` no longer aborts rendering.

## [1.0.0] - 2026-11-03

### Added
- Commands: `review` (full codebase), `review-diff` (uncommitted, `--staged`, `--branch <base>`, `--range a..b`), `security`, `architecture`.
- `comprehensive-review` orchestration skill with a 10-step pipeline: baseline, stack, context, scope, agent selection, parallel review, consolidation, validation, reasoning check, reports.
- Eight read-only specialist agents (Read/Grep/Glob only): architecture (also covers code quality), security, performance, backend, frontend, database, testing, devops.
- Deterministic stdlib-Python scripts:
  - `detect-stack.py`: manifests plus source-usage confirmation for 30+ frameworks; entry points, critical paths, agent recommendations.
  - `diff-scope.py`: changed files and line ranges for uncommitted, staged, branch, and range selectors.
  - `scan-signals.py`: regex hints with file:line, secrets redacted.
  - `import-graph.py`: internal import graph and circular dependencies (JS/TS with tsconfig aliases, Python, Java/Kotlin, Go).
  - `validate-findings.py`: schema checks; file, line, and evidence verification with line correction; severity rules; strong-duplicate auto-merge plus orchestrator merge decisions (`merges.json`); secret scrubbing; ID assignment.
  - `render-reports.py`: five Markdown reports, a self-contained HTML dashboard, and a heuristic health score.
  - `integrity.py`: hash snapshot and verify, proving the review did not modify the repository.
- Report templates, references (finding schema, severity rubric, category ownership, stack checklists, report guide, reviewer protocol).
- Tests: 21 unit tests, NestJS / Next.js / Spring Boot fixtures with seeded issues, a diff overlay, an e2e runner and an evaluator.
- Self-hosted marketplace manifest and organization distribution guide.
- Example report (`examples/nestjs-orders-api/`) and validation record (`docs/VALIDATION.md`).
