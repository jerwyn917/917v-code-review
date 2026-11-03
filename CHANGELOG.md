# Changelog

All notable changes to this plugin are documented here. Versions follow [Semantic Versioning](https://semver.org/). The version in `.claude-plugin/plugin.json` is the source of truth.

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
