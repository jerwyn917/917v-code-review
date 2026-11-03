#!/usr/bin/env python3
"""Pattern scan that gives reviewers precise file:line starting points (read-only).

Signals are HINTS, not findings: a reviewer agent must open the file and
confirm each one before it becomes a finding. Secret values are redacted.

Usage: scan-signals.py <repo-root> [--scope scope.json] [-o signals.json]
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import dump_json, is_text_candidate, iter_repo_files, load_json, read_text, redact  # noqa: E402

CODE = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".java", ".kt", ".py", ".php",
        ".go", ".rb", ".rs", ".cs", ".scala", ".groovy")
JS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
TEMPLATES = (".html", ".vue", ".svelte", ".jsx", ".tsx", ".blade.php", ".erb", ".jinja", ".j2", ".hbs", ".ejs",
             ".twig")
CONFIG = (".yml", ".yaml", ".json", ".properties", ".toml", ".ini", ".cfg", ".conf", ".env", ".xml")
SQL = (".sql",)

# (rule id, agent, hint, regex, file filter). A filter is a tuple of suffixes or a callable(rel).
I = re.IGNORECASE


def _is_dockerfile(rel):
    b = os.path.basename(rel).lower()
    return b.startswith("dockerfile") or b.endswith(".dockerfile")


def _is_ci(rel):
    return rel.startswith(".github/workflows/") or os.path.basename(rel) in (
        ".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml") or rel.startswith(".circleci/")


def _is_migration(rel):
    return bool(re.search(r"(^|/)(migrations?|db/migrate|db/migration|prisma/migrations)/", rel)) or rel.endswith(SQL)


def _is_env(rel):
    b = os.path.basename(rel)
    return (b == ".env" or b.startswith(".env.")) and not re.search(r"\.(example|sample|template|dist)$", b)


RULES = [
    # --- security-reviewer ---------------------------------------------------
    ("sql-string-building", "security-reviewer",
     "SQL built with string concatenation / interpolation: check for injection",
     re.compile(r"""(?:["'`]\s*(?:SELECT|INSERT|UPDATE|DELETE)\b[^"'`]*["'`]\s*(?:\+|%|\.format\())|"""
                r"""(?:`\s*(?:SELECT|INSERT|UPDATE|DELETE)\b[^`]*\$\{)|"""
                r"""(?:f["']\s*(?:SELECT|INSERT|UPDATE|DELETE)\b[^"']*\{)|"""
                r"""(?:\$queryRawUnsafe|\$executeRawUnsafe|\.raw\(\s*f?["'`][^"'`]*(?:\$\{|\{|%s|"\s*\+))|"""
                r"""(?:createQuery|createNativeQuery|nativeQuery|jdbcTemplate\.\w+)\s*\(\s*"[^"]*"\s*\+""", I), CODE),
    ("command-or-code-exec", "security-reviewer",
     "Dynamic code/command execution: check whether input reaches it",
     re.compile(r"\beval\s*\(|new\s+Function\s*\(|child_process|\bexecSync\s*\(|\bexec\s*\(\s*[`'\"]?.*(\$\{|\+)|"
                r"Runtime\.getRuntime\(\)\.exec|ProcessBuilder\(|os\.system\(|subprocess\.\w+\([^)]*shell\s*=\s*True|"
                r"\bshell_exec\(|\bpassthru\(|\bsystem\(\$"), CODE),
    ("raw-html-rendering", "security-reviewer",
     "Unescaped HTML rendering: check for XSS",
     re.compile(r"dangerouslySetInnerHTML|\.innerHTML\s*=|\bv-html\s*=|\{@html\s|\|\s*safe\b|mark_safe\(|"
                r"\{!!.*!!\}|bypassSecurityTrust\w+\(|document\.write\("), TEMPLATES + CODE),
    ("weak-crypto", "security-reviewer",
     "Weak hash/cipher or insecure randomness in a possibly security-relevant context",
     re.compile(r"createHash\(\s*['\"](md5|sha1)['\"]|MessageDigest\.getInstance\(\s*\"(MD5|SHA-?1)\"|"
                r"hashlib\.(md5|sha1)\(|\bmd5\(|\bsha1\(|DES/|/ECB/|createCipher\(|"
                r"(token|secret|password|otp|nonce|salt)\w*\s*=.*Math\.random\(", I), CODE),
    ("jwt-handling", "security-reviewer",
     "JWT verification bypass / weak config candidate",
     re.compile(r"jwt\.decode\(|algorithms\s*[:=]\s*\[\s*['\"]none|ignoreExpiration\s*:\s*true|"
                r"verify_signature['\"]?\s*:\s*False|\.parseUnsecuredClaims|setSigningKey\(\s*\"", I), CODE),
    ("tls-verification-disabled", "security-reviewer",
     "TLS certificate verification disabled",
     re.compile(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED|verify\s*=\s*False|"
                r"InsecureSkipVerify\s*:\s*true|TrustAllCerts|NoopHostnameVerifier|CURLOPT_SSL_VERIFYPEER,\s*false"),
     CODE + CONFIG),
    ("permissive-cors", "security-reviewer",
     "Wildcard / reflective CORS configuration",
     re.compile(r"origin\s*:\s*(['\"]\*['\"]|true)|Access-Control-Allow-Origin['\"]?\s*[,:]\s*['\"]\*|"
                r"@CrossOrigin\(\s*(origins\s*=\s*)?\"\*\"|allowedOrigins\(\s*\"\*\"|allow_origins\s*=\s*\[\s*['\"]\*|"
                r"CORS_ORIGIN_ALLOW_ALL\s*=\s*True|CORS_ALLOW_ALL_ORIGINS\s*=\s*True|enableCors\(\s*\)"),
     CODE + CONFIG),
    ("csrf-disabled", "security-reviewer",
     "CSRF protection disabled",
     re.compile(r"csrf\(\)\s*\.disable|csrf\(\s*\w+\s*->\s*\w+\.disable|AbstractHttpConfigurer::disable|"
                r"@csrf_exempt|csrf\s*:\s*false|VerifyCsrfToken.*except"), CODE + CONFIG),
    ("unsafe-deserialization", "security-reviewer",
     "Unsafe deserialization candidate",
     re.compile(r"pickle\.loads?\(|yaml\.load\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)|ObjectInputStream|"
                r"\bunserialize\s*\(|Marshal\.load|BinaryFormatter"), CODE),
    ("user-input-to-filesystem", "security-reviewer",
     "Request data flows into a filesystem/redirect call: check path traversal / open redirect",
     re.compile(r"(readFile|readFileSync|createReadStream|sendFile|res\.download|open|Files\.\w+|"
                r"new\s+File|redirect|res\.redirect)\s*\([^)]*(req\.|request\.|params\b|query\b|getParameter\()"),
     CODE),
    ("token-in-web-storage", "security-reviewer",
     "Auth token stored in localStorage/sessionStorage (XSS-readable)",
     re.compile(r"(localStorage|sessionStorage)\.setItem\(\s*['\"`][^'\"`]*(token|jwt|auth|session)", I), JS),
    ("debug-enabled", "security-reviewer",
     "Debug mode / verbose errors enabled in configuration",
     re.compile(r"^\s*DEBUG\s*=\s*True|APP_DEBUG\s*=\s*true|server\.error\.include-stacktrace\s*[=:]\s*always|"
                r"FLASK_DEBUG\s*=\s*1|app\.run\([^)]*debug\s*=\s*True"), CODE + CONFIG),
    ("broad-permit", "security-reviewer",
     "Broad unauthenticated access rule: confirm intended",
     re.compile(r"permitAll\(\)|AllowAny|@Public\(\)|SkipAuth|withoutMiddleware\(['\"]auth|"
                r"anyRequest\(\)\.permitAll"), CODE),
    # --- performance-reviewer ------------------------------------------------
    ("sync-io", "performance-reviewer",
     "Synchronous blocking I/O in a Node.js code path",
     re.compile(r"\b(readFileSync|writeFileSync|existsSync|readdirSync|execSync|statSync)\s*\("), JS),
    ("unbounded-fetch", "performance-reviewer",
     "Unbounded query (no pagination/limit): check collection size",
     re.compile(r"\.findAll\(\s*\)|\.objects\.all\(\)|\.find\(\s*\{\s*\}\s*\)|\.find\(\s*\)|"
                r"SELECT\s+\*\s+FROM\s+\w+\s*['\"`;]|::all\(\)|->get\(\)\s*;", I), CODE),
    # --- architecture-reviewer (code quality) --------------------------------
    ("swallowed-exception", "architecture-reviewer",
     "Exception caught and ignored",
     re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}|except(\s+\w+(\s+as\s+\w+)?)?\s*:\s*pass\b|"
                r"catch\s*\([^)]*\)\s*\{\s*//[^\n]*\}|\.catch\(\s*\(\s*\w*\s*\)\s*=>\s*\{\s*\}\s*\)"), CODE),
    ("debug-output", "architecture-reviewer",
     "Debug/console output instead of the project's logger",
     re.compile(r"\bconsole\.(log|debug|trace)\(|System\.(out|err)\.print|\.printStackTrace\(\)|"
                r"^\s*print\(|\bvar_dump\(|\bdd\(|fmt\.Print"), CODE),
    ("todo-marker", "architecture-reviewer",
     "TODO/FIXME/HACK marker",
     re.compile(r"(//|#|/\*|\*)\s*(TODO|FIXME|HACK|XXX)\b"), CODE),
    # --- database-reviewer ---------------------------------------------------
    ("schema-auto-sync", "database-reviewer",
     "ORM schema auto-sync / auto-DDL enabled (unsafe outside local dev)",
     re.compile(r"synchronize\s*:\s*true|ddl-auto\s*[:=]\s*(update|create|create-drop)|"
                r"hibernate\.hbm2ddl\.auto\s*[:=]\s*(update|create)|db\.AutoMigrate|sequelize\.sync\(\s*\{\s*(force|alter)"),
     CODE + CONFIG),
    ("destructive-migration", "database-reviewer",
     "Destructive or locking migration statement",
     re.compile(r"DROP\s+(TABLE|COLUMN|INDEX)|ALTER\s+TABLE\s+\S+\s+ALTER\s+COLUMN|"
                r"ADD\s+COLUMN\s+\S+\s+\S+[^;]*NOT\s+NULL(?![^;]*DEFAULT)|RENAME\s+(COLUMN|TO)|TRUNCATE\s|"
                r"dropColumn\(|dropTable\(|->dropColumn|remove_column|drop_table", I), _is_migration),
    # --- frontend-reviewer ---------------------------------------------------
    ("index-as-key", "frontend-reviewer",
     "Array index used as list key",
     re.compile(r"key=\{\s*(i|idx|index)\s*\}|:key=\"\s*(i|idx|index)\s*\""), JS),
    ("img-without-alt", "frontend-reviewer",
     "<img> without alt attribute",
     re.compile(r"<(img|Image)\b(?![^>]*\balt\s*=)[^>]*/?>"), TEMPLATES),
    ("click-on-non-interactive", "frontend-reviewer",
     "Click handler on a non-interactive element (keyboard accessibility)",
     re.compile(r"<(div|span|li|td)\b[^>]*\b(onClick|@click|v-on:click)\s*="), TEMPLATES),
    # --- devops-reviewer -----------------------------------------------------
    ("docker-unpinned-base", "devops-reviewer",
     "Base image is unpinned or uses :latest",
     re.compile(r"^\s*FROM\s+(?!scratch\b)([^\s:@]+)(:latest)?(\s+AS\s+\w+)?\s*$", I | re.M), _is_dockerfile),
    ("docker-root-or-secret", "devops-reviewer",
     "Container runs as root or bakes a secret into the image",
     re.compile(r"^\s*USER\s+root\b|^\s*(ENV|ARG)\s+\w*(PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)\w*[\s=]", I | re.M),
     _is_dockerfile),
    ("ci-risky-pattern", "devops-reviewer",
     "Risky CI pattern (unpinned action, pull_request_target, curl|sh, secrets echo)",
     re.compile(r"pull_request_target|uses:\s*[\w./-]+@(main|master|latest)\b|curl[^|\n]*\|\s*(ba)?sh|"
                r"echo\s+\$\{\{\s*secrets\."), _is_ci),
    ("iac-public-exposure", "devops-reviewer",
     "Publicly exposed / unencrypted infrastructure resource",
     re.compile(r"acl\s*=\s*\"public-read|cidr_blocks\s*=\s*\[\s*\"0\.0\.0\.0/0\"|publicly_accessible\s*=\s*true|"
                r"encrypted\s*=\s*false|storage_encrypted\s*=\s*false|block_public_acls\s*=\s*false|"
                r"0\.0\.0\.0/0"), (".tf", ".tfvars", ".yaml", ".yml", ".json")),
]

SECRET_KEY = re.compile(
    r"""(?ix)(?P<key>[A-Za-z0-9_.\-]*(?:password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|
    private[_-]?key|client[_-]?secret|credential)[A-Za-z0-9_.\-]*)\s*(?:=>|:=|=|:)\s*['"`](?P<val>[^'"`\s]{8,})['"`]""")
SECRET_FORMAT = re.compile(r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|"
                           r"sk_live_[A-Za-z0-9]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AIza[0-9A-Za-z_-]{35}|"
                           r"://[^:/\s'\"]+:[^@/\s'\"]{3,}@")
# Unquoted key=value / key: value secrets in config and env files.
CONFIG_SECRET = re.compile(
    r"""(?ix)^\s*(?:export\s+)?[\w.\-]*(?:password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|
    private[_-]?key|client[_-]?secret|credentials?)[\w.\-]*\s*[=:]\s*['"]?(?P<val>[^\s'"#]{6,})""")
PLACEHOLDER = re.compile(r"^(changeme|example|placeholder|your[-_]|xxx|\*+|<|\$\{|test|dummy|secret$|password$)", I)


def _applies(flt, rel):
    if callable(flt):
        return flt(rel)
    return rel.lower().endswith(flt)


def _in_ranges(line, ranges):
    return any(s <= line <= e for s, e in ranges)


def scan(root, scope=None, per_rule_limit=60):
    root = os.path.abspath(root)
    if scope:
        targets = {f["file"]: f["ranges"] for f in scope["files"] if f["status"] != "deleted"}
        files = [f for f in targets if os.path.isfile(os.path.join(root, f))]
    else:
        targets = None
        files = list(iter_repo_files(root))
    signals, counts, file_level = [], {}, []

    def add(rule, agent, hint, rel, line, text):
        counts[rule] = counts.get(rule, 0) + 1
        if counts[rule] > per_rule_limit:
            return
        sig = {"rule": rule, "agent": agent, "hint": hint, "file": rel, "line": line,
               "snippet": redact(text.strip())[:220]}
        if targets is not None:
            sig["in_changed_lines"] = _in_ranges(line, targets.get(rel, []))
        signals.append(sig)

    dockerfiles = []
    for rel in files:
        if not is_text_candidate(rel) and not _is_dockerfile(rel):
            continue
        if _is_env(rel):
            file_level.append({"rule": "committed-env-file", "agent": "security-reviewer", "file": rel,
                               "hint": "Environment file is part of the repository: check for real secrets"})
        text = read_text(root, rel)
        if not text:
            continue
        lines = text.splitlines()
        if _is_dockerfile(rel):
            dockerfiles.append(rel)
            if not re.search(r"^\s*USER\s+(?!root\b)\S+", text, re.M | re.I):
                file_level.append({"rule": "docker-no-user", "agent": "devops-reviewer", "file": rel,
                                   "hint": "No non-root USER instruction: container likely runs as root"})
        for rule, agent, hint, pat, flt in RULES:
            if not _applies(flt, rel):
                continue
            for i, line in enumerate(lines, 1):
                if len(line) > 2000:
                    continue
                if pat.search(line):
                    add(rule, agent, hint, rel, i, line)
        is_example = re.search(r"(example|sample|template|fixture|mock|\.test\.|\.spec\.|/tests?/)", rel, I)
        for i, line in enumerate(lines, 1):
            if len(line) > 2000:
                continue
            m = SECRET_KEY.search(line)
            if not m and (rel.lower().endswith(CONFIG) or _is_env(rel)):
                m = CONFIG_SECRET.search(line)
            hit = bool(SECRET_FORMAT.search(line)) or (m and not PLACEHOLDER.match(m.group("val"))
                                                       and not m.group("val").startswith(("process.env", "${")))
            if hit:
                add("hardcoded-secret", "security-reviewer",
                    "Possible hard-coded credential%s" % (" (in a test/example file)" if is_example else ""),
                    rel, i, line)
    for df in dockerfiles:
        ignore = os.path.join(os.path.dirname(df), ".dockerignore")
        if not os.path.isfile(os.path.join(root, ignore)) and not os.path.isfile(os.path.join(root, ".dockerignore")):
            file_level.append({"rule": "docker-no-dockerignore", "agent": "devops-reviewer", "file": df,
                               "hint": "No .dockerignore next to Dockerfile: build context may include .env/.git"})
    by_agent = {}
    for s in signals + file_level:
        by_agent[s["agent"]] = by_agent.get(s["agent"], 0) + 1
    return {
        "note": "Signals are unverified hints. Confirm each against the source before reporting a finding.",
        "files_scanned": len(files),
        "rule_hit_counts": counts,
        "truncated_rules": [r for r, c in counts.items() if c > per_rule_limit],
        "by_agent": by_agent,
        "signals": signals,
        "file_level": file_level,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("--scope", help="scope.json from diff-scope.py (limits scan to changed files)")
    ap.add_argument("-o", "--output", default="-")
    a = ap.parse_args()
    scope = load_json(a.scope) if a.scope else None
    dump_json(scan(a.root, scope), a.output)


if __name__ == "__main__":
    main()
