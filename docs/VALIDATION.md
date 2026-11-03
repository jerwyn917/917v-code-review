# Validation results: v1.0.0

Recorded on 2026-11-03 with Claude Code 2.1.198 on macOS and Python 3.14. Every result below comes from a command that was actually run. Anything not executed is marked **NOT RUN**, with the reason.

## Summary

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Test against a NestJS repository | ✅ Passed | Full live review of `tests/fixtures/nestjs-orders-api`: 7 agents, 53 findings, **recall 19/19** of seeded issues (see [Live review](#live-review-nestjs-full-codebase)) |
| 2 | Test against a Next.js repository | ⚠️ Partial | Deterministic stages pass (stack detection, entry points, signals, import graph incl. `@/` alias). Live agent review **NOT RUN**: blocked by CLI auth (see [Blocked](#blocked-headless-end-to-end-runs)) |
| 3 | Test against a Java/Spring Boot repository | ⚠️ Partial | Deterministic stages pass (Spring Boot 3.2.1 confirmed, Maven, JPA/Flyway, 13 signals incl. native-query SQLi, CSRF disable, `ddl-auto`). Live agent review **NOT RUN**: same blocker |
| 4 | Full codebase review | ✅ Passed | NestJS live review, all reports generated |
| 5 | Git diff review | ⚠️ Partial | `diff-scope.py` verified for uncommitted (incl. untracked), `--staged`, `--branch`, `--range`. Scoped signal scan flags the injected `execSync` on changed lines. Validator `in_changed_lines` flags unit-tested. Live diff review with agents **NOT RUN** |
| 6 | File references and line numbers | ✅ Passed | 53/53 findings re-verified by `tests/evaluate.py` (file exists, line exists, evidence present). Rejection of invented files, lines, and evidence, plus line relocation, unit-tested |
| 7 | Severity classification | ✅ Passed | Rubric rules unit-tested (Critical⇒Confirmed, Low-confidence cap, Confirmed⇒≥Medium confidence). Evaluator found no violations. Orchestrator reasoning check done on all 4 Critical / 14 High |
| 8 | Target codebase not modified | ✅ Passed | `integrity.py verify`: 22 files hashed before and after, unchanged, HEAD unchanged. Evaluator byte-compare against a pristine copy: 0 differences |
| 9 | Duplicate findings consolidated | ✅ Passed | 57 submitted → 53 reported. 4 cross-agent duplicates merged via `merges.json`, 0 unmerged duplicates per evaluator. See the over-merge bug fixed below |
| 10 | Plugin installation and command execution | ⚠️ Partial | `claude plugin validate . --strict` passes (marketplace and plugin). `claude --plugin-dir` loads it (`917v-code-review@inline ✔ loaded`). `plugin details` lists 4 commands, 1 skill, 8 agents, about 1k always-on tokens. Executing `/917v-code-review:review` headlessly **NOT RUN**: the CLI's OAuth token is revoked (`401`) |
| – | Script unit tests | ✅ Passed | `python3 -m unittest discover -s tests`: **21 tests OK** |

## Live review: NestJS, full codebase

The orchestrator followed `skills/comprehensive-review/SKILL.md` step by step on a throwaway Git copy of the fixture. Each of the 7 selected reviewers ran from its exact `agents/*.md` definition. The frontend reviewer was skipped because no UI was detected. The agents ran as subagents of an authenticated Claude session, because headless `claude -p` could not authenticate (see below).

| Metric | Result |
|---|---|
| Stack detected | NestJS ^10.3.0 (confirmed in source), TypeORM, PostgreSQL (manifest-only), Jest/Supertest, Docker, .env, GitHub Actions |
| Agents run / skipped | 7 / 1 (frontend: no UI detected) |
| Files read by at least one agent | 22 / 22 |
| Findings submitted / accepted / rejected | 57 / 57 / 0 |
| Duplicates merged | 4 (orchestrator decisions in `merges.json`) |
| Reported findings | 53: 4 Critical, 14 High, 26 Medium, 9 Low; 50 Confirmed, 3 Potential |
| Seeded issues found | **19 / 19** (recall 1.0) |
| Extra findings beyond the seeded list | 39, all location-verified. Examples: missing `@nestjs/cli` breaks `nest build`, client-controlled prices allow balance credit, no idempotency on POST /orders |
| Secret values in any report file | 0 (evaluator grep for the fixture's fake DB password and JWT key) |
| Repository modified | No |

The output is in [`examples/nestjs-orders-api/`](../examples/nestjs-orders-api/).

## Defects found by validation and fixed

1. **Over-merging (correctness).** The first de-duplication merged findings that shared a location and had similar evidence. In the live run, 13 merges took place, and about 8 combined *different* issues on the same lines. Examples: N+1 with missing index, ValidationPipe with health checks, SQL injection with leading-wildcard ILIKE. **Fix:** auto-merge only strong duplicates. These are same location plus a similar title or the same CWE, or same category with near-identical evidence. Findings from the same agent are never merged unless their titles match. Other cross-agent same-line pairs become `merge_candidates`, which the orchestrator decides in an auditable `merges.json`. Covered by `test_dedupe_auto_and_candidates` and `test_orchestrator_merges`.
2. **Secrets in free text.** A secret quoted in a description, not in a `key=value` form, survived redaction. **Fix:** the validator collects secret values from the cited source lines and scrubs them from every field.
3. **Over-redaction of code.** `const token = getToken(req)` was masked. **Fix:** unquoted call expressions and identifiers are recognized as code.
4. **tsconfig parsing.** The JSONC comment stripper treated `"**/*.ts"` as a comment, so `@/` aliases did not resolve and the Next.js import graph was empty. **Fix:** a string-aware JSONC stripper.
5. **Unquoted config secrets** in `.properties` and `.env` files were not flagged. **Fix:** a config-file secret pattern.
6. **Health score floored at 0** for findings-heavy reviews. **Fix:** a diminishing-returns formula, `100·e^(−P/100)`.
7. **Next.js entry points.** Route handlers and server actions were missing. **Fix:** detected explicitly.
8. **Host without Grep/Glob.** In this host the reviewer agents had only `Read`. They still reached 22/22 file coverage, but the fallback is now formalized: `detect-stack.py --files-out` writes `files.txt`, and the protocol tells agents to use it when Grep/Glob are unavailable. The agents stay strictly read-only.

## Blocked: headless end-to-end runs

`tests/e2e/run-e2e.sh` runs `claude -p "/917v-code-review:review" --plugin-dir <plugin>` against a fresh fixture copy, then scores the result with `tests/evaluate.py`. All four runs (NestJS, Next.js, and Spring Boot full reviews, plus the NestJS diff review) were started and stopped immediately with:

```
Failed to authenticate. API Error: 401 OAuth access token has been revoked.
```

`claude auth status` reports a logged-in claude.ai account, but its stored token is revoked. The plugin itself loaded with no plugin errors in the session init event. To complete these runs, sign in again in a terminal (`claude auth login`), then run:

```bash
B=$(mktemp -d)
tests/e2e/run-e2e.sh nestjs-orders-api full "$B"
tests/e2e/run-e2e.sh nextjs-shop full "$B"
tests/e2e/run-e2e.sh spring-bank-api full "$B"
tests/e2e/run-e2e.sh nestjs-orders-api diff "$B"
```

Each run prints pass/fail, recall, and severity totals, and leaves `evaluation.json` and `transcript.jsonl` in `$B/<fixture>-<mode>/`.

## Assumptions

- The GitHub location `917ventures/917v-code-review` is a placeholder. Replace it in `plugin.json`, `README.md`, and `docs/DISTRIBUTION.md`.
- Seeded-issue recall measures known defects only. It does not measure precision. Extra findings were spot-checked during the orchestrator's reasoning check, not exhaustively.
