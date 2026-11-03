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

## Must-nots

- No invented paths, lines, APIs, or execution results. If you did not open the file, do not cite it.
- No findings about code you did not read. Grep hits must be opened and read in context.
- No duplicates of the same issue: use `related_locations` instead.
- No findings in another agent's territory when that agent is running (see category-ownership.md).
- No secrets in any field.
- An empty `findings` array is a valid, useful result. Record what you checked in `no_issue_areas`.
