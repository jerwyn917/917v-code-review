# 917v-code-review

A Claude Code plugin that runs the **917Ventures standardized code review** on any existing repository. It needs no changes to the target project.

- **Full codebase review**, or a **Git diff review** (uncommitted, staged, branch vs. base, or commit range).
- **Automatic stack detection** from manifests *and* source usage. A folder name alone never counts as evidence.
- **Eight specialist agents**: architecture, security, performance, backend, frontend, database, testing, devops. They are selected by the detected stack and have non-overlapping responsibilities.
- **Validation of every finding against the source**. The file must exist, the line must exist, and the evidence must appear in the file. Wrong line numbers are corrected, unverifiable claims are rejected, duplicates are merged, and secrets are redacted.
- **Consolidated reports** in `docs/code-review/`: executive summary, detailed findings, security review, architecture review, recommendations, an interactive HTML dashboard, and `findings.json`.
- **Read-only by default.** Every file is hashed before and after the review, and the report states whether anything outside `docs/code-review/` changed.

## Commands

| Command | What it does |
|---|---|
| `/917v-code-review:review [path]` | Full codebase review with every relevant agent |
| `/917v-code-review:review-diff [--staged \| --branch <base> \| --range a..b]` | Review only changed code. Default: uncommitted changes, including untracked files |
| `/917v-code-review:security [path]` | Security-focused review (OWASP Top 10, injection, XSS, authn/authz, secrets, config, infrastructure security) |
| `/917v-code-review:architecture [path]` | Architecture and code quality (SOLID, DRY, layering, circular dependencies, modularity) |

Common options: `--agents a,b` (run only these agents), `--skip a,b`, `--no-html`.

You can also ask in plain words, for example "review this repo" or "do a security review of my branch against main". The `comprehensive-review` skill triggers automatically.

### Examples

```text
/917v-code-review:review
/917v-code-review:review services/payments
/917v-code-review:review-diff --branch main
/917v-code-review:review-diff --staged
/917v-code-review:security
/917v-code-review:architecture --no-html
```

## How a review runs

```
 1. integrity.py snapshot      hash every file (proves read-only at the end)
 2. detect-stack.py            languages, frameworks, DBs, tests, infra, CI, entry points, critical paths
 3. read README / standards    conventions the reviewers must respect
 4. diff-scope.py (diff only)  changed files + changed line ranges
    scan-signals.py            regex hints with file:line (unverified leads, secrets redacted)
    import-graph.py            file-level import graph + circular dependencies
 5. select agents              from the stack and the mode; skipped agents are listed with reasons
 6. run agents in parallel     each returns JSON per references/finding-schema.md
 7. consolidate                raw agent outputs saved verbatim
 8-9. validate-findings.py     verify file/line/evidence, fix line drift, enforce severity rules,
                               auto-merge strong duplicates, redact secrets, assign IDs (SEC-001, ...)
      + orchestrator decides cross-agent merge candidates (merges.json, auditable)
      + orchestrator re-reads every Critical/High finding in context
10. integrity.py verify + render-reports.py → docs/code-review/
```

The scripts are deterministic and use only the Python standard library. The judgment comes from the agents, and the scripts keep it honest.

### Agents and ownership

| Agent | Categories | Runs when |
|---|---|---|
| `architecture-reviewer` | Architecture, Code Quality | always |
| `security-reviewer` | Security | always |
| `performance-reviewer` | Performance | always |
| `backend-reviewer` | API & Backend | a server framework or API handlers are detected |
| `frontend-reviewer` | Frontend | a UI framework or component files are detected |
| `database-reviewer` | Database | an ORM, DB driver, SQL, or migrations are detected |
| `testing-reviewer` | Testing | always (no tests is itself a finding) |
| `devops-reviewer` | DevOps & Infrastructure | Docker, IaC, CI/CD, env files, or deploy config are detected |

Overlaps, such as a hard-coded secret in a Dockerfile, are settled by the tie-breakers in [`category-ownership.md`](skills/comprehensive-review/references/category-ownership.md).

### Supported technologies

Stack detection covers, from manifests and source usage: **Node.js, NestJS, Next.js, React, Vue, Nuxt, Angular, Svelte/SvelteKit, Express, Fastify, Koa, Hapi, tRPC, Apollo GraphQL, Java, Kotlin, Spring Boot (Web MVC, WebFlux, Security), Quarkus, Micronaut, Python, Django (+DRF), FastAPI, Flask, PHP, Laravel, Symfony, Go (Gin, Echo, Fiber, Chi), Ruby on Rails, Sinatra, Rust (Actix, Axum), ASP.NET Core**. Data layers: Prisma, TypeORM, Sequelize, Mongoose, Knex, Drizzle, JPA/Hibernate, Flyway, Liquibase, Django ORM, SQLAlchemy, Alembic, Eloquent, Doctrine, GORM, Active Record, EF Core. Testing: Jest, Vitest, Mocha, Playwright, Cypress, JUnit, Mockito, Testcontainers, pytest, PHPUnit, Pest, testify, RSpec, xUnit. Infrastructure: **Docker, Docker Compose, Terraform** (with providers), Kubernetes, Helm, Kustomize, Serverless, Pulumi, PaaS configs; GitHub Actions, GitLab CI, Jenkins, CircleCI, Azure Pipelines, Bitbucket.

Other languages are still reviewed. The agents read any code, and only the automatic framework hints are missing.

## Finding format and severity

Every finding has an ID, severity, category, title, description, file path, line, evidence, potential impact, recommended solution, confidence, and status. Status separates **Confirmed** defects from **Potential** risks.

| Severity | Meaning |
|---|---|
| Critical | Immediate security or business-critical risk |
| High | Significant security, reliability, or functional issue |
| Medium | Maintainability, performance, or operational concern |
| Low | Minor improvement or code quality concern |
| Informational | Recommendation or best practice |

Rules the validator enforces:
- Critical requires Confirmed.
- Low confidence is capped at Medium.
- Confirmed requires at least Medium confidence.

See [`severity-rubric.md`](skills/comprehensive-review/references/severity-rubric.md).

## Output

```
docs/code-review/
├── executive-summary.md     summary, health score, counts by severity/category, critical risks, top recommendations
├── detailed-findings.md     every finding with all fields (diff mode: grouped by changed lines / context)
├── security-review.md       OWASP Top 10 table, security findings, areas checked
├── architecture-review.md   structure, dependency analysis (import cycles), architecture + code quality findings
├── recommendations.md       strategic themes, then Priority 1/2/3 actions
├── dashboard.html           self-contained interactive dashboard (no network requests)
├── findings.json            validated findings, for tooling/CI
└── .work/                   scratch: stack, signals, raw agent output, integrity proof (git-ignored)
```

`docs/code-review/` is the only place the plugin writes. Commit it, or add it to `.gitignore`; the plugin never decides for you. Each run replaces the previous reports.

An example report generated from the bundled NestJS fixture is in [`examples/nestjs-orders-api/`](examples/nestjs-orders-api/).

## Review principles

- Read-only. Nothing is modified, installed, built, executed, staged, or committed in the target repository.
- No source code is sent to external services, including online audit tools, unless you authorize it in the conversation.
- No invented paths, line numbers, vulnerabilities, or execution results. Unverifiable claims are rejected, and the rejections are listed in the report.
- Secrets are never printed. Values are redacted in agent output, by the validator, and in the reports.
- Recommendations respect the existing architecture and avoid new libraries unless they are genuinely needed.

## Installation

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for organization rollout, private GitHub hosting, version pinning, and upgrades. Quick start for a developer:

```bash
# once: make sure git can read the private repo (SSH key, or `gh auth login && gh auth setup-git`)
claude plugin marketplace add 917ventures/917v-code-review
claude plugin install 917v-code-review@917ventures
```

Or inside Claude Code: `/plugin marketplace add 917ventures/917v-code-review`, then `/plugin install 917v-code-review@917ventures`.

Try it without installing:

```bash
claude --plugin-dir /path/to/917v-code-review
```

**Requirements:** Claude Code, `git`, and `python3` 3.8 or newer (preinstalled on macOS and most Linux). Without Python, the skill falls back to a manual review and says so in the report.

### As a standalone skill

The same review also ships as a single self-contained Agent Skill, `917v-code-review`, for places where a plugin is not wanted or not supported (personal `~/.claude/skills/`, claude.ai, the Claude API). Build it from this repo:

```bash
python3 tools/build-skill.py
```

This writes `dist/917v-code-review/` (the skill folder) and `dist/917v-code-review.zip` (the same folder, zipped).

- **Claude Code, every project:** copy `dist/917v-code-review` to `~/.claude/skills/`. **One project only:** copy it to `<project>/.claude/skills/`. Then ask "review this repo", or run `/917v-code-review` with `security`, `architecture`, or `diff --branch main`.
- **claude.ai / Claude Desktop:** upload `dist/917v-code-review.zip` under Settings → Capabilities → Skills, then upload or attach the repository to review.

Differences from the plugin: there are no slash commands (the mode comes from your words or the skill argument), and the eight agents become reviewer briefs in `references/reviewers/`. In Claude Code the orchestrator runs them in parallel as general-purpose subagents told to stay read-only; where subagents are unavailable (claude.ai), it runs them one after another itself. Scripts, templates, schema, rubric, and reports are identical.

## Development

```
.claude-plugin/plugin.json        plugin manifest (name, version)
.claude-plugin/marketplace.json   this repo is also a one-plugin marketplace
commands/                         the four slash commands (thin wrappers around the skill)
skills/comprehensive-review/      orchestration skill + references (schema, rubric, ownership, checklists)
agents/                           the eight specialist reviewers (Read/Grep/Glob only)
scripts/                          deterministic helpers (stdlib Python)
templates/                        report templates + dashboard
skill-src/SKILL.md                orchestrator for the standalone skill build
tools/build-skill.py              packages the standalone skill into dist/ (git-ignored)
tests/                            unit tests, fixtures, expected seeded issues, e2e runner, evaluator
```

When you change `skills/comprehensive-review/SKILL.md`, mirror the change in `skill-src/SKILL.md`. Agents, references, scripts, and templates are copied by the build, so they need no second edit.

```bash
python3 -m unittest discover -s tests -v                # script unit tests (offline, fast)
claude plugin validate . --strict                       # manifest validation
tests/e2e/run-e2e.sh nestjs-orders-api full /tmp/e2e    # live review of a fixture copy + scoring
```

Validation results are recorded in [docs/VALIDATION.md](docs/VALIDATION.md).

## Assumptions and limitations

- **Static review.** Code is never executed, so runtime-only bugs, configuration injected at deploy time, and real coverage numbers are out of reach. Findings that depend on those are marked Potential.
- **Dependency vulnerabilities** are assessed offline from manifests. Online audits (`npm audit`, OWASP Dependency-Check, etc.) are recommended, not run.
- **Large repositories** (more than ~1500 files) are prioritized by entry points and critical paths, not read exhaustively. The report says what was covered.
- **The health score** is a heuristic over this review's findings, not a quality metric of the codebase.
- **The import graph** resolves relative imports and tsconfig path aliases (JS/TS), Python packages, Java/Kotlin packages, and Go module packages. Other languages rely on the architecture agent's own reading.
- **Signals are regex hints.** They speed up the agents but are never reported without an agent confirming them in context.
- **Agent recall is not 100%.** The bundled fixtures measure it; see docs/VALIDATION.md.
