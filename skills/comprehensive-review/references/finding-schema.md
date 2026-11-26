# Reviewer output contract

Every specialist agent returns **exactly one JSON object** and nothing else, optionally inside a ```json fence. The orchestrator saves it verbatim, and `scripts/validate-findings.py` checks it.

```json
{
  "agent": "security-reviewer",
  "files_reviewed": ["src/auth/auth.service.ts", "src/users/users.controller.ts"],
  "findings": [
    {
      "severity": "High",
      "category": "Security",
      "title": "SQL injection in user search",
      "description": "UsersRepository.search() concatenates the `q` query parameter into a raw SQL string.",
      "file": "src/users/users.repository.ts",
      "line": 42,
      "end_line": 44,
      "evidence": "const sql = `SELECT * FROM users WHERE name LIKE '%${q}%'`;\nreturn this.db.query(sql);",
      "impact": "Any caller of GET /users?q= can read or modify arbitrary tables.",
      "recommendation": "Use a parameterized query: this.db.query('SELECT ... WHERE name LIKE $1', [`%${q}%`]).",
      "confidence": "High",
      "status": "Confirmed",
      "cwe": "CWE-89",
      "owasp": "A03:2021",
      "related_locations": [{"file": "src/users/users.controller.ts", "line": 18}]
    }
  ],
  "no_issue_areas": [
    "Password hashing uses bcrypt with cost 12 (src/auth/auth.service.ts:31)"
  ],
  "notes": "Did not review generated files under src/generated/."
}
```

## Field rules

| Field | Required | Rule |
|---|---|---|
| `severity` | yes | `Critical`, `High`, `Medium`, `Low`, or `Informational`; see severity-rubric.md |
| `category` | yes | `Architecture`, `Code Quality`, `Security`, `Performance`, `API & Backend`, `Frontend`, `Database`, `Testing`, or `DevOps & Infrastructure` |
| `title` | yes | ≤ 80 chars; names the defect, not the fix |
| `description` | yes | What is wrong and why, grounded in the cited code |
| `file` | yes | Repository-relative path exactly as it exists (no `./`, no absolute paths) |
| `line` | yes | 1-based line where the evidence starts, taken from the Read tool's line numbers or `grep -n` |
| `end_line` | no | Last line of the evidence |
| `evidence` | yes | Code copied **verbatim** from the file at `line` (1–8 lines). No line-number prefixes, no paraphrase. Secret values replaced with `[REDACTED]`. `...` may stand for skipped lines |
| `impact` | yes | Concrete consequence: who can do what, what breaks, what it costs |
| `recommendation` | yes | Specific fix that fits the existing code and conventions; a short code sketch is welcome |
| `confidence` | yes | `High`: the cited code alone proves it. `Medium`: relies on one stated, reasonable assumption. `Low`: plausible but unverified (prefer not to report) |
| `status` | yes | `Confirmed`: a defect demonstrated by the code. `Potential`: a risk that depends on runtime, deployment or caller context you could not see |
| `cwe`, `owasp` | security only | e.g. `CWE-89`, `A03:2021` |
| `security_relevant` | no | `true` when a non-Security finding also has security impact (it appears in security-review.md) |
| `related_locations` | no | Other places with the same problem: `[{"file", "line"}]`. Prefer one finding with related locations over many copies |
| `evidence_type` | no | `"absence"` for "something is missing" findings (no tests for X, no USER in Dockerfile). Then `evidence` describes what you searched for and `line` points at the most relevant existing line (often 1) |

## Added by the validator, not by reviewers

When the code was downloaded from a GitHub link, `findings.json` also has a top-level `source`: `name` (`owner/repo`), `url`, `ref`, `ref_type` (`branch`, `tag`, `commit`, or `pull`), `commit`, `subdir`, `pull`, `history` (`full` or `shallow`), and the `blob_base` and `commit_base` URLs the reports link to. It is `null` for a local repository.

Reviewers never fill these in. `validate-findings.py` adds `id`, `reported_by`, `evidence_verified`, `validation_notes`, and, for security findings in a Git repository, `git`:

```json
"git": {
  "status": "traced",
  "lines": "42-44",
  "introduced":   {"commit": "<40 hex>", "short": "a1b2c3d4", "author": "Ana Cruz", "committer": "Ana Cruz", "date": "2025-03-02", "summary": "Add user search"},
  "last_changed": {"commit": "<40 hex>", "short": "d4e5f6a7", "author": "Ben Reyes", "committer": "GitHub", "date": "2026-01-11", "summary": "Support partial matches"},
  "same": false,
  "changes": 2
}
```

`introduced` is the oldest commit in the history of the first cited line (`git log -L`); `last_changed` is the most recent commit that changed any cited line (`git blame -w`, so whitespace-only commits do not count). Other statuses are `uncommitted` and `untraced`, each with a `reason`. Do not write a `git` object yourself, and do not name authors or commits in any other field.

## Must-nots

- No invented paths, lines, APIs, or execution results. If you did not open the file, do not cite it.
- No findings about code you did not read. Grep hits must be opened and read in context.
- No duplicates of the same issue: use `related_locations` instead.
- No findings in another agent's territory when that agent is running (see category-ownership.md).
- No secrets in any field.
- An empty `findings` array is a valid, useful result. Record what you checked in `no_issue_areas`.
