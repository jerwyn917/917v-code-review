# Category ownership (no redundant reviews)

Each topic has exactly **one owner**. An agent reports only topics it owns. If it notices something owned by another agent **that is running in this review** (listed in the prompt as AGENTS RUNNING), it leaves it alone. If the owner is **not** running, the agent may report it, using the owner's category.

| Agent | Categories | Owns | Does NOT own (→ owner) |
|---|---|---|---|
| `architecture-reviewer` | Architecture, Code Quality | SOLID, DRY at module/design level, separation of concerns, layering, design patterns, dependency direction, circular dependencies, modularity, coupling/cohesion; readability, naming conventions, duplication, error-handling *consistency*, logging *practices*, complexity, dead code | Security of error messages (security), API status codes (backend), query efficiency (performance) |
| `security-reviewer` | Security | OWASP Top 10, injection (SQL/NoSQL/command/LDAP/template), XSS, CSRF, SSRF, authn/authz, session/JWT, secrets and credentials in code/config, sensitive data exposure and logging of PII, crypto, deserialization, path traversal, open redirect, security headers/CORS, frontend security (token storage, unsafe HTML) | Docker/IaC/CI hardening (devops); rate limiting as API design (backend) |
| `performance-reviewer` | Performance | N+1 queries, queries in loops, inefficient algorithms, unnecessary loops/computation, blocking I/O, memory leaks (listeners, timers, caches, closures), inefficient API calls (sequential awaits, over-fetching), caching opportunities, resource utilization (pools, streams) | Missing indexes/schema (database); React re-renders/bundle size (frontend) |
| `backend-reviewer` | API & Backend | REST conventions, request validation (DTOs/schemas), response shape consistency, HTTP status codes, exception handling and error mapping, rate limiting, API versioning, pagination contracts, transaction boundaries in service code, idempotency, background jobs | Injection/authz (security); SQL performance (performance); schema/migrations (database) |
| `frontend-reviewer` | Frontend | Component architecture, state management, rendering performance and unnecessary re-renders, effect dependencies, accessibility (WCAG), responsive design, client/server boundaries (Next.js), data fetching patterns, bundle size | XSS/token storage (security); backend APIs (backend) |
| `database-reviewer` | Database | Schema design, normalization, constraints and data integrity, indexing, query optimization at the SQL/ORM-definition level, transaction isolation and locking, migration safety (destructive, locking, irreversible), connection/ORM config (auto-sync/DDL) | Raw-SQL injection (security); N+1 in service loops (performance); transactions in service code (backend) |
| `testing-reviewer` | Testing | Unit/integration/e2e coverage gaps, critical business logic without tests, missing edge cases, mocking practices, flaky patterns, test maintainability, test config | Bugs in production code found while reading tests: report only if no other owner is running |
| `devops-reviewer` | DevOps & Infrastructure | Dockerfiles and compose, env-variable management and `.env` handling, CI/CD pipelines, dependency versions and lockfiles (offline review only), logging/monitoring/health checks, deployment config, Kubernetes/Helm, Terraform/IaC security | Secrets inside application code (security) |

## Overlap tie-breakers

- **Hard-coded secret**: in application code, the owner is security. In Dockerfile, CI, IaC, or compose files, the owner is devops, with `security_relevant: true`.
- **Missing validation**: if it enables an exploit, the owner is security. If it only causes a bad contract or a 500, the owner is backend.
- **Slow query**: a missing index or schema problem belongs to database. The calling pattern (loop, N+1, over-fetch) belongs to performance.
- **Error handling**: leaking stack traces or internals belongs to security. Wrong status codes or inconsistent error shapes belong to backend. Swallowed exceptions and inconsistent style belong to architecture (Code Quality).
- **Logging**: PII or secrets in logs belong to security. Missing logging or monitoring infrastructure belongs to devops. Logger misuse or `console.log` belongs to architecture (Code Quality).

The validator still merges anything that slips through: findings at the same location with similar titles, or the same issue repeated across files.
