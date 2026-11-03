# Example report

`nestjs-orders-api/` is the complete output of a full review of the bundled fixture `tests/fixtures/nestjs-orders-api`. Seven agents ran; frontend was skipped because no UI was detected. The run was scored by `tests/evaluate.py`, and the results are in [docs/VALIDATION.md](../docs/VALIDATION.md).

- [executive-summary.md](nestjs-orders-api/executive-summary.md)
- [detailed-findings.md](nestjs-orders-api/detailed-findings.md)
- [security-review.md](nestjs-orders-api/security-review.md)
- [architecture-review.md](nestjs-orders-api/architecture-review.md)
- [recommendations.md](nestjs-orders-api/recommendations.md)
- [dashboard.html](nestjs-orders-api/dashboard.html): open it in a browser
- [findings.json](nestjs-orders-api/findings.json): machine-readable findings
- `summary.json` and `merges.json`: the orchestrator's narrative and its duplicate-merge decisions, copied from `.work/` for reference

In a real run these files live in `<repo>/docs/code-review/`, and the `../../src/...` links point into the reviewed repository. In this copy those links do not resolve, because the fixture's sources are under `tests/fixtures/nestjs-orders-api/`. The fixture's credentials are fake, and they are redacted in the reports anyway.
