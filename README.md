# 917v-code-review

A Claude Code plugin that runs the **917Ventures standardized code review** on any existing repository. It needs no changes to the target project.

- **Full codebase review**, or a **Git diff review** (uncommitted, staged, branch vs. base, or commit range).
- **Automatic stack detection** from manifests *and* source usage. A folder name alone never counts as evidence.
- **Eight specialist agents**: architecture, security, performance, backend, frontend, database, testing, devops. They are selected by the detected stack and have non-overlapping responsibilities.
- **Validation of every finding against the source**. The file must exist, the line must exist, and the evidence must appear in the file. Wrong line numbers are corrected, unverifiable claims are rejected, duplicates are merged, and secrets are redacted.
- **Consolidated reports** in a folder **outside your repository** (`~/.917v-code-review/reviews/<repo>-<id>/` by default): executive summary, detailed findings, security review, architecture review, recommendations, an interactive HTML dashboard with amCharts analytics in 917 Ventures branding, and `findings.json`.
- **Results in the chat.** Where the host can render inline visuals (Claude Desktop, claude.ai), the review ends with a branded results widget in the conversation: KPI cards, severity and category charts, a severity filter, and "Explain ↗" buttons that send follow-up questions back to Claude.
- **Analysis only, never touches your repository.** It never edits, formats, or deletes project files, never applies fixes, and writes nothing inside the repository. Reports go to a folder outside it, claimed with a `.917v-code-review` marker, and a folder you own is never overwritten. The scripts refuse any output path inside the repository and run only read-only Git commands, without rewriting `.git/index`. Every file is hashed before and after, and the report states whether anything changed.

## Commands

| Command | What it does |
|---|---|
| `/917v-code-review:review [path]` | Full codebase review with every relevant agent |
| `/917v-code-review:review-diff [--staged \| --branch <base> \| --range a..b]` | Review only changed code. Default: uncommitted changes, including untracked files |
| `/917v-code-review:security [path]` | Security-focused review (OWASP Top 10, injection, XSS, authn/authz, secrets, config, infrastructure security) |
| `/917v-code-review:architecture [path]` | Architecture and code quality (SOLID, DRY, layering, circular dependencies, modularity) |
| `/917v-code-review:scan [path] [--staged \| --branch <base> \| --range a..b]` | Quick triage in seconds: stack, pattern-based risk leads, import cycles. No agents and no validation, so it reports leads, not findings. Writes `scan.md` outside the repository |

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
/917v-code-review:scan
/917v-code-review:scan --branch main
```

## How a review runs

```
 1. prepare-review.py          ONE call: integrity baseline, stack detection, diff scope, pattern signals,
                               import graph, and one inputs file per agent (.work/agents/<agent>.md with
                               stack digest, scope, priority files, its signals, matching stack checklists)
 2. read README / standards    one parallel batch, then a 10-25 line review brief (.work/brief.md)
 3. select agents              from the stack and the mode; skipped agents are listed with reasons
 4. run agents in parallel     short prompts; each agent reads the self-contained reviewer protocol and
                               its inputs file in one step, batches its reads, returns JSON
 5. validate-findings.py       verify file/line/evidence, fix line drift, enforce severity rules,
                               auto-merge strong duplicates, redact secrets, assign IDs (SEC-001, ...)
      + orchestrator decides cross-agent merge candidates (merges.json, auditable)
      + orchestrator re-reads every Critical/High finding in context (one parallel batch)
 6. render-reports.py          ONE call: read-only integrity check + reports + dashboard + chat widget
```

`/917v-code-review:scan` is step 1 alone (`prepare-review.py --mode scan`): one call, no agents, `scan.md`.

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
~/.917v-code-review/reviews/<repo>-<id>/      (outside the repository; --out <dir> to choose)
├── .917v-code-review        ownership marker
├── executive-summary.md     summary, health score, counts by severity/category, critical risks, top recommendations
├── detailed-findings.md     every finding with all fields (diff mode: grouped by changed lines / context)
├── security-review.md       OWASP Top 10 table, security findings, areas checked
├── architecture-review.md   structure, dependency analysis (import cycles), architecture + code quality findings
├── recommendations.md       strategic themes, then Priority 1/2/3 actions
├── scan.md                  quick-scan leads (only from /917v-code-review:scan)
├── dashboard.html           interactive dashboard: amCharts 5 analytics, cross-filtering findings list
├── findings.json            validated findings, for tooling/CI
└── .work/                   scratch: stack, signals, agent inputs, raw agent output, integrity proof, chat-widget.html
```

Nothing is written inside the reviewed repository, so `git status` stays clean. `<id>` is derived from the repository's path, so each repository keeps its own folder, and each run replaces that folder's previous reports. Override the location with `--out <dir>` (any folder outside the repository) or the `CODE_REVIEW_OUT_DIR` environment variable, which sets the base folder. Source links in the reports are relative paths back to the repository, so they work on the machine that ran the review.

### Dashboard analytics

`dashboard.html` uses the 917 Ventures design system (Unbounded and Montserrat, brand palette, light and dark themes) and draws its charts with [amCharts 5](https://www.amcharts.com) 5.21.5:

| Chart | Shows | Click to |
|---|---|---|
| Health gauge | Heuristic 0–100 score with rating bands | — |
| Severity donut | Findings per severity | filter by severity |
| Category bars | Findings per category, stacked by severity | filter by category and severity |
| OWASP Top 10 | Findings per OWASP 2021 risk | filter by OWASP risk |
| Hotspot files | The 10 files with the most findings, stacked by severity | filter by file |
| Reviewer × severity heatmap | What each specialist agent reported | filter by reviewer and severity |

The page loads amCharts from cdnjs and the fonts from Google Fonts. The review data is inlined and never leaves the page. Offline, every chart falls back to built-in HTML bars, so the dashboard still works. amCharts' free build shows a small amCharts logo in each chart; internal use is fine, while customer-facing or logged-in production use needs a license.

### In-chat results widget

`render-reports.py --widget <path>` writes `.work/chat-widget.html`, an HTML fragment that follows the inline-widget rules of the 917 Ventures generative-UI skill: fragment only, host theme tokens, no comments, amCharts with an HTML fallback, and `sendPrompt` buttons. The orchestrator passes it unchanged to the host's inline visual tool. In the terminal there is no such tool, and the text summary is shown instead.

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
claude plugin marketplace add jerwyn917/917v-code-review
claude plugin install 917v-code-review@917ventures
```

Or inside Claude Code: `/plugin marketplace add jerwyn917/917v-code-review`, then `/plugin install 917v-code-review@917ventures`.

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
commands/                         the slash commands (review, review-diff, security, architecture wrap the skill; scan runs the scripts only)
skills/comprehensive-review/      orchestration skill + references (schema, rubric, ownership, checklists)
agents/                           the eight specialist reviewers (Read/Grep/Glob only)
scripts/                          deterministic helpers (stdlib Python)
templates/                        report templates, dashboard, in-chat widget, 917V logo
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
- **Reports live outside the repository.** Tools scoped to the repository folder, such as an editor's file tree or the Claude app's file pane, don't show them. Open the folder path printed at the end of the run, or pass `--out <dir>` to put the reports somewhere you browse.
