# Code Review — Executive Summary

| | |
|---|---|
| **Repository** | nestjs-orders-api |
| **Review type** | Full codebase review |
| **Scope** | entire repository (22 files) |
| **Date** | 2026-11-03 |
| **Commit** | c7e402e |
| **Reviewed by** | 917v-code-review v1.0.0 (architecture-reviewer, security-reviewer, performance-reviewer, backend-reviewer, database-reviewer, testing-reviewer, devops-reviewer) |

## Overall review summary

The Orders API is a small NestJS 10 service (Auth, Users, Orders modules on TypeORM/PostgreSQL) that debits a user's balance when an order is placed. Module structure is clean and controllers are mostly thin, but the service is not safe to expose. Authentication can be forged (SEC-002), an unauthenticated endpoint is SQL-injectable (SEC-004), clients choose their own prices (SEC-003), and production credentials are committed in three places (SEC-001, SEC-005, OPS-001, OPS-002). The money path (placeOrder) has no transaction, no locking and no tests (API-002, TEST-002).

## Overall code health assessment

**At Risk** — heuristic score **9/100**

The rating is driven by four confirmed Critical security defects that are each exploitable without credentials, plus fourteen High findings concentrated in the order/balance flow and the deployment setup. The codebase is small and conventionally structured, so most fixes are local: verify JWTs, parameterize one query, validate DTOs, wrap placeOrder in a transaction, and move secrets to configuration.

<sub>Score = 100 × e^(−P/100), where P = 15 × Critical + 7 × High + 3 × Medium + 1 × Low and Potential findings count half. Ratings: ≥ 85 Healthy, 70–84 Fair, 50–69 Needs Attention, &lt; 50 or any Critical = At Risk. It summarises this review's findings only and is not a quality metric of the whole codebase.</sub>

## Findings by severity

| Severity | Count |
|---|---:|
| Critical | 4 |
| High | 14 |
| Medium | 26 |
| Low | 9 |
| Informational | 0 |
| **Total** | **53** |

## Findings by category

| Category | Count |
|---|---:|
| Architecture | 4 |
| Code Quality | 1 |
| Security | 11 |
| Performance | 3 |
| API & Backend | 7 |
| Frontend | 0 |
| Database | 9 |
| Testing | 5 |
| DevOps & Infrastructure | 13 |
| **Total** | **53** |

## Critical risks

- **SEC-001** — Hard-coded production database password in source and committed .env (Critical, Confirmed) — [`src/app.module.ts:13`](../../src/app.module.ts#L13)
- **SEC-002** — JwtGuard decodes the JWT without verifying its signature (Critical, Confirmed) — [`src/auth/jwt.guard.ts:8`](../../src/auth/jwt.guard.ts#L8)
- **SEC-003** — Order prices and quantities trusted from the client (balance manipulation) (Critical, Confirmed) — [`src/orders/orders.controller.ts:21`](../../src/orders/orders.controller.ts#L21)
- **SEC-004** — Unauthenticated SQL injection in GET /users/search (Critical, Confirmed) — [`src/users/users.service.ts:23`](../../src/users/users.service.ts#L23)
- **SEC-005** — Hard-coded JWT signing secret in AuthService (High, Confirmed) — [`src/auth/auth.service.ts:6`](../../src/auth/auth.service.ts#L6)
- **SEC-006** — Passwords hashed with unsalted MD5 (High, Confirmed) — [`src/auth/auth.service.ts:12`](../../src/auth/auth.service.ts#L12)
- **SEC-007** — User and order read endpoints have no authentication or ownership check (High, Confirmed) — [`src/users/users.controller.ts:13`](../../src/users/users.controller.ts#L13)
- **SEC-008** — Password hashes and full user rows returned in API responses (High, Confirmed) — [`src/users/users.service.ts:27`](../../src/users/users.service.ts#L27)

## Top recommendations

1. **Make authentication real, then apply it by default** — Replace the hand-written guard with @nestjs/jwt (`JwtService.verifyAsync`) configured once in AuthModule from ConfigService, register it as a global `APP_GUARD` with an `@Public()` decorator for login, and add ownership checks in the services. (SEC-002, SEC-005, SEC-007, SEC-010, ARC-001)
2. **Make placeOrder a single, server-priced transaction** — Accept only `{ sku, quantity }` through a validated DTO, price items server-side, and perform the conditional debit, the order insert and a bulk item insert inside one `dataSource.transaction`, keyed by an idempotency key. Then cover it with unit and e2e tests. (SEC-003, API-002, API-005, PERF-003, DB-006, TEST-002, ARC-003)
3. **Move every secret and setting into validated configuration** — Adopt @nestjs/config with a schema that requires DB_* and JWT_SECRET, use `TypeOrmModule.forRootAsync`, delete `.env` and the Dockerfile ENV, add `.gitignore`, `.dockerignore` and `.env.example`, and rotate the exposed credentials. (SEC-001, SEC-005, OPS-001, OPS-002, OPS-010)
4. **Switch schema management to migrations and fix the money types** — Turn off `synchronize`, generate a baseline migration, then migrate money columns to `numeric(12,2)` or integer cents and add constraints (unique email, FK on order items, non-negative balance, indexes). (DB-001, DB-002, DB-003, DB-004, DB-005, DB-006)
5. **Turn CI into a real gate** — Commit a lockfile, add @nestjs/cli, fix the Jest config, run `npm ci`, tests and `npm audit` on pull requests, and pin actions and the Node image to the same LTS. (OPS-003, OPS-004, OPS-005, OPS-006, TEST-003, OPS-007)

## Technology stack detected

| Area | Detected |
|---|---|
| Languages | TypeScript (16 files) |
| Runtimes | Node.js |
| Frameworks | NestJS ^10.3.0 |
| Databases / ORM | TypeORM, PostgreSQL (manifest only) |
| Testing | Jest, Supertest (2 test files) |
| Infrastructure | Environment files, Docker |
| CI/CD | GitHub Actions |
| Package managers | npm |
| Shape | single project |

## Review coverage and limitations

| Agent | Files reviewed |
|---|---:|
| architecture-reviewer | 18 |
| backend-reviewer | 17 |
| database-reviewer | 12 |
| devops-reviewer | 11 |
| performance-reviewer | 12 |
| security-reviewer | 19 |
| testing-reviewer | 11 |

Repository files considered: 22.
- Skipped **frontend-reviewer**: no frontend framework or UI component files detected

Validation: 57 findings submitted by reviewers, 57 accepted, 0 rejected (location or evidence could not be verified in the source), 4 duplicates merged, 0 line numbers corrected.
Read-only check: 22 repository files hashed before and after the review — no file outside `docs/code-review/` was modified.
- Static review only: no code was executed, built or tested, and no coverage figures are claimed
- Dependency vulnerabilities were not checked online (no network authorization); OPS-004 recommends `npm audit` in CI
- In this validation run the reviewer agents had only the Read tool available (Grep/Glob were not provided by the host), so they located files by path; all 22 repository files were read by at least one agent
- 25 same-location pairs reported by different agents were reviewed by the orchestrator and kept separate as distinct issues; 4 true duplicates were merged (see validation notes)

---
Full details: [detailed-findings.md](detailed-findings.md) · [security-review.md](security-review.md) · [architecture-review.md](architecture-review.md) · [recommendations.md](recommendations.md) · [dashboard.html](dashboard.html)
