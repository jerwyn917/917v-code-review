# Severity rubric

| Severity | Definition | Typical examples |
|---|---|---|
| **Critical** | Immediate security or business-critical risk, exploitable or failing as the code stands | Hard-coded production credentials or private keys; unauthenticated SQL/command injection; auth bypass on a sensitive endpoint; money/ledger logic that double-charges or loses data; destructive migration that drops live data |
| **High** | Significant security, reliability, or functional issue | Missing authorization check (IDOR); XSS on user content; JWT verified without signature/expiry; N+1 on a hot list endpoint; unhandled promise rejection that crashes the process; missing transaction around a multi-write money operation; container running as root with secrets baked in |
| **Medium** | Maintainability, performance, or operational concern | God class / layering violation; circular dependency; missing input validation without a direct exploit; unbounded query on a growing table; missing index on a filtered column; no tests for a core service; `:latest` base image |
| **Low** | Minor improvement or code quality concern | Inconsistent naming; small duplication; `console.log` instead of the logger; missing alt text on a decorative image; magic numbers |
| **Informational** | Recommendation or best practice, no defect | Suggest an ADR; consider a lint rule; note on future scaling |

## Rules enforced by `validate-findings.py`

1. **Critical requires `status: Confirmed`.** A Potential issue is capped at High.
2. **Low confidence is capped at Medium.** Low-confidence High or Critical claims become Medium.
3. **Confirmed requires Medium or High confidence.** Confirmed with Low confidence is turned into Potential.
4. **A partial evidence match lowers confidence.** If only part of the evidence matched the source, High confidence becomes Medium.

## Calibration questions

Before assigning **Critical/High**, answer in the description:
- **Reachability**: Is the code on a live path (routed endpoint, scheduled job, imported module)? Dead code is at most Low.
- **Control**: Who controls the input: anonymous user, authenticated user, admin, or nobody (constants/config)?
- **Mitigations**: Is there a global guard, middleware, validation pipe, ORM parameterization, framework auto-escaping, or WAF config in the repo that already handles it? Search for it before reporting.
- **Blast radius**: data exposure, money, availability, or developer inconvenience?

Test, fixture, and example files: secrets or unsafe code there are usually **Low/Informational**, unless the values look like real production credentials.

## Status vs. confidence

- `Confirmed` + `High` → the code alone proves the defect.
- `Potential` + `Medium` → the defect depends on context (e.g. "if this service is internet-facing").
- Prefer not reporting over reporting `Low` confidence speculation.
