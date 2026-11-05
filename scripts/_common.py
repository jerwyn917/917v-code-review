"""Shared constants and helpers for the 917v-code-review scripts.

Standard library only (Python 3.8+). Every script in this folder is read-only
with respect to the reviewed repository:
- source files are only read; no script edits, formats, moves, or deletes them;
- Git is called only with read-only subcommands, and with GIT_OPTIONAL_LOCKS=0 so
  `git status`/`git diff` do not rewrite .git/index;
- output never goes inside the repository: reports live in a folder OUTSIDE it,
  by default ~/.917v-code-review/reviews/<repo>-<id>/ (`default_output_dir`),
  claimed with an ownership marker so a folder the user owns is never overwritten
  (`claim_output_dir`), and every write path is checked (`check_output_path`).
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

# Where earlier versions wrote reports inside the repository. Only used to skip such
# leftovers when reading the code; nothing is ever written there any more.
OUTPUT_DIR = os.path.join("docs", "code-review")
OUT_ENV = "CODE_REVIEW_OUT_DIR"   # base folder for reports (default ~/.917v-code-review/reviews)
MARKER = ".917v-code-review"   # ownership marker inside the output folder
OWN_OUTPUTS = {MARKER, ".work", "executive-summary.md", "detailed-findings.md", "security-review.md",
               "architecture-review.md", "recommendations.md", "dashboard.html", "findings.json", "scan.md"}
READ_ONLY_GIT = {"rev-parse", "ls-files", "diff", "merge-base", "status", "log", "show", "cat-file"}
EXIT_OUTPUT_CONFLICT = 4


class ReadOnlyViolation(SystemExit):
    """Raised when a write would land outside the review's own output folder."""

    def __init__(self, message):
        eprint("read-only guard: " + message)
        super().__init__(EXIT_OUTPUT_CONFLICT)

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


def _git_env():
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"   # never refresh/rewrite .git/index during the review
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def is_git_repo(root):
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, check=False, env=_git_env(),
        )
        return out.returncode == 0 and out.stdout.strip() == "true"
    except FileNotFoundError:
        return False


def git(root, *args):
    """Run a read-only git command and return stdout (raises on failure)."""
    i = 0
    while i < len(args) and args[i] == "-c":   # skip leading `-c key=value` config options
        i += 2
    if i >= len(args) or args[i] not in READ_ONLY_GIT:
        raise ReadOnlyViolation("refusing non-read-only git command: git %s" % " ".join(args))
    out = subprocess.run(
        ["git", "-C", root] + list(args), capture_output=True, text=True, check=False, env=_git_env()
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


def _inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def default_output_dir(root):
    """Report folder for <root>, outside the repository: <base>/<repo-name>-<8-hex id of the path>."""
    import hashlib
    root = os.path.realpath(root)
    base = os.environ.get(OUT_ENV) or os.path.join(os.path.expanduser("~"), ".917v-code-review", "reviews")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(root) or "repo")
    return os.path.join(os.path.abspath(base), "%s-%s" % (name, hashlib.sha1(root.encode("utf-8")).hexdigest()[:8]))


def check_output_path(root, path):
    """Refuse any write inside the reviewed repository. Output lives outside it."""
    if path in (None, "-"):
        return path
    if _inside(path, root):
        raise ReadOnlyViolation("%s is inside the reviewed repository; the review never writes there. Reports go "
                                "to a folder outside it (default %s, or --out / %s)."
                                % (path, default_output_dir(root), OUT_ENV))
    return path


def claim_output_dir(root, out=None):
    """Create (or reuse) the report folder outside the repository and mark it as ours.

    The folder may be new, already carry our marker, or hold only file names this tool
    produces. Anything else belongs to the user and is never overwritten.
    """
    out = os.path.abspath(out or default_output_dir(root))
    check_output_path(root, out)
    if os.path.isdir(out) and not os.path.exists(os.path.join(out, MARKER)):
        foreign = sorted(set(os.listdir(out)) - OWN_OUTPUTS)
        if foreign:
            raise ReadOnlyViolation(
                "%s already exists and contains files this review did not create (%s). Nothing was written. "
                "Choose another --out folder." % (out, ", ".join(foreign[:5])))
    elif os.path.exists(out) and not os.path.isdir(out):
        raise ReadOnlyViolation("%s exists and is not a folder; nothing was written" % out)
    os.makedirs(out, exist_ok=True)
    marker = os.path.join(out, MARKER)
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("Created by 917v-code-review for %s. Everything in this folder is review output; the "
                     "review never writes inside the repository.\n" % os.path.realpath(root))
    return out
