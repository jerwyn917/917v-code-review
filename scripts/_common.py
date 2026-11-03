"""Shared constants and helpers for the 917v-code-review scripts.

Standard library only (Python 3.8+). Every script in this folder is read-only
with respect to the reviewed repository: they read source files and write
only to the paths given on the command line (normally docs/code-review/).
"""

import json
import os
import re
import subprocess
import sys

SEVERITIES = ["Critical", "High", "Medium", "Low", "Informational"]
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
CONFIDENCES = ["High", "Medium", "Low"]
STATUSES = ["Confirmed", "Potential"]

# Category -> (finding-ID prefix, owning agent)
CATEGORIES = {
    "Architecture": ("ARC", "architecture-reviewer"),
    "Code Quality": ("CQ", "architecture-reviewer"),
    "Security": ("SEC", "security-reviewer"),
    "Performance": ("PERF", "performance-reviewer"),
    "API & Backend": ("API", "backend-reviewer"),
    "Frontend": ("FE", "frontend-reviewer"),
    "Database": ("DB", "database-reviewer"),
    "Testing": ("TEST", "testing-reviewer"),
    "DevOps & Infrastructure": ("OPS", "devops-reviewer"),
}

AGENTS = [
    "architecture-reviewer",
    "security-reviewer",
    "performance-reviewer",
    "backend-reviewer",
    "frontend-reviewer",
    "database-reviewer",
    "testing-reviewer",
    "devops-reviewer",
]

OUTPUT_DIR = os.path.join("docs", "code-review")

# Directories never worth reviewing (dependencies, build output, VCS).
IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor",
    "dist", "build", "out", ".next", ".nuxt", ".output", ".svelte-kit",
    "target", ".gradle", ".mvn", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage",
    ".terraform", ".idea", ".vscode", ".turbo", ".cache", ".parcel-cache",
    "storage", "bin", "obj", "Pods", ".dart_tool",
}

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".pdf",
    ".zip", ".gz", ".tgz", ".jar", ".war", ".class", ".so", ".dylib",
    ".dll", ".exe", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3",
    ".lock", ".min.js", ".map", ".pyc",
}

MAX_TEXT_BYTES = 1_000_000


def eprint(*args):
    print(*args, file=sys.stderr)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(data, path=None):
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path in (None, "-"):
        sys.stdout.write(text)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def is_git_repo(root):
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, check=False,
        )
        return out.returncode == 0 and out.stdout.strip() == "true"
    except FileNotFoundError:
        return False


def git(root, *args):
    """Run a read-only git command and return stdout (raises on failure)."""
    out = subprocess.run(
        ["git", "-C", root] + list(args), capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), out.stderr.strip()))
    return out.stdout


def iter_repo_files(root, exclude_prefixes=(OUTPUT_DIR,)):
    """Yield repo-relative POSIX paths of reviewable files.

    Uses `git ls-files` when available so .gitignore is honoured; otherwise
    walks the tree skipping IGNORE_DIRS. Paths under exclude_prefixes
    (the review's own output folder) are skipped.
    """
    root = os.path.abspath(root)
    exclude = tuple(p.replace(os.sep, "/").rstrip("/") + "/" for p in exclude_prefixes)
    if is_git_repo(root):
        try:
            listing = git(root, "ls-files", "-co", "--exclude-standard", "-z")
            paths = [p for p in listing.split("\0") if p]
        except RuntimeError:
            paths = None
    else:
        paths = None
    if paths is None:
        paths = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
            for name in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                paths.append(rel.replace(os.sep, "/"))
    for rel in sorted(set(paths)):
        parts = rel.split("/")
        if any(p in IGNORE_DIRS for p in parts[:-1]):
            continue
        if rel.startswith(exclude):
            continue
        if not os.path.isfile(os.path.join(root, rel)):
            continue  # deleted but still tracked
        yield rel


def is_text_candidate(rel):
    low = rel.lower()
    return not any(low.endswith(ext) for ext in BINARY_EXT)


def read_text(root, rel):
    """Return file text or None for binary/oversized/unreadable files."""
    path = os.path.join(root, rel)
    try:
        if os.path.getsize(path) > MAX_TEXT_BYTES:
            return None
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


# --- Secret redaction -------------------------------------------------------

REDACTED = "[REDACTED]"

_SECRET_PATTERNS = [
    # Provider-specific token formats.
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk-(?:live|test|proj|ant)?[-_]?[A-Za-z0-9_-]{16,}"),
    re.compile(r"rk_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    # Credentials embedded in connection URLs: scheme://user:password@host
    re.compile(r"(?<=://)([^:/\s'\"]+):([^@/\s'\"]{3,})(?=@)"),
]

# key = "value" / key: value / key => 'value' for secret-looking keys.
_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<key>[A-Za-z0-9_.\-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|
        access[_-]?key|private[_-]?key|client[_-]?secret|auth|credential)[A-Za-z0-9_.\-]*)
    (?P<sep>\s*(?:=>|:=|=|:)\s*)
    (?P<q>['"`]?)
    (?P<val>[^\s'"`,;)}{]{4,})
    """
)

_NOT_SECRET_VALUES = re.compile(
    r"^(?:process\.env|os\.environ|os\.getenv|env\(|System\.getenv|\$\{|\$|getenv|config\(|"
    r"true|false|null|none|undefined|required|optional|string|number|boolean|"
    r"\[REDACTED\]|<[^>]*>|\*+|x+|changeme|example|placeholder|your[-_])",
    re.IGNORECASE,
)


def _secret_spans(text):
    """Yield (start, end, keep_prefix) spans of secret values inside text."""
    for pat in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            if pat.groups == 2:  # scheme://user:password@ -> only the password
                yield m.start(2), m.end(2)
            else:
                yield m.start(), m.end()
    for m in _ASSIGNMENT.finditer(text):
        val = m.group("val")
        if _NOT_SECRET_VALUES.match(val) or REDACTED in val:
            continue
        if not m.group("q"):
            # Unquoted: code such as `token = getToken(req)` or `password: dto.password` is not a literal.
            if re.match(r"^[A-Za-z_$][\w.$]*\(", val):
                continue
            if re.match(r"^[A-Za-z_$][\w.$]*$", val) and not re.search(r"\d", val) and \
                    re.search(r"\s", m.group("sep")):
                continue
        yield m.start("val"), m.end("val")


def secret_values(text):
    """Return the distinct secret-looking substrings found in text."""
    if not text:
        return []
    return sorted({text[s:e] for s, e in _secret_spans(text) if e - s >= 4}, key=len, reverse=True)


def redact(text, extra=()):
    """Mask secret-looking values (keeps keys so evidence stays meaningful).

    `extra` are known secret strings (e.g. collected from the cited source
    lines) that are scrubbed wherever they appear, including free text.
    """
    if not text:
        return text
    spans = sorted(_secret_spans(text))
    out, pos = [], 0
    for s, e in spans:
        if s < pos:
            continue
        out.append(text[pos:s])
        out.append(REDACTED)
        pos = e
    out.append(text[pos:])
    text = "".join(out)
    for value in extra:
        if value and len(value) >= 4:
            text = text.replace(value, REDACTED)
    return text


def rel_inside(root, rel):
    """True when rel resolves to a path inside root (no ../ escapes)."""
    root = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root, rel))
    return full == root or full.startswith(root + os.sep)
