---
description: Security-focused read-only review (OWASP Top 10, injection, XSS, authn/authz, secrets, configuration, infra security)
argument-hint: "[path | GitHub link] [--no-html]"
---

Run the 917Ventures **security-focused review**.

Invoke the `917v-code-review:comprehensive-review` skill and follow it exactly, with:

- mode=security
- arguments: $ARGUMENTS

A public GitHub link (`https://github.com/<owner>/<repo>`) can be given instead of a path; it is downloaded to `~/.917v-code-review/repos/` and reviewed from there. Only `security-reviewer` runs. `devops-reviewer` is added, limited to infrastructure-security items, when Docker, IaC, or CI configuration is detected. The review is **analysis only**: it never edits project files or applies fixes. Do not run online scanners or send code anywhere unless the user explicitly authorizes it.
