#!/usr/bin/env python3
"""Download a PUBLIC GitHub repository so it can be reviewed like a local folder.

  fetch-repo.py <github link> [--ref <branch|tag|commit>] [--depth N | --full]
  fetch-repo.py --list                       the downloaded copies
  fetch-repo.py --remove <github link>       delete one downloaded copy

Accepted links (https://, http://, no scheme, or git@github.com:owner/repo.git):
  github.com/<owner>/<repo>                           the default branch
  github.com/<owner>/<repo>/tree/<ref>[/<folder>]     a branch, tag or commit; a folder narrows the review to it
  github.com/<owner>/<repo>/blob/<ref>/<file>         that ref (the file is reported as "focus")
  github.com/<owner>/<repo>/commit/<sha>              one commit
  github.com/<owner>/<repo>/releases/tag/<tag>        a tag
  github.com/<owner>/<repo>/pull/<number>             a pull request: its head, plus the range to diff ("diff")

The copy goes to ~/.917v-code-review/repos/<owner>/<repo> ($CODE_REVIEW_REPOS_DIR to change the base
folder), never into the current project. Prints JSON: "root" is the folder to review.

What this script will and will not do:
- public repositories on github.com only. No credentials are ever used or asked for: credential
  helpers and askpass programs are switched off, and only the https transport is allowed. A private
  or missing repository is reported, never worked around;
- nothing from the repository is executed: no hooks, no submodules, no Git LFS download, no build,
  no install. Symbolic links are checked out as plain text files (core.symlinks=false), so a link
  that points outside the copy cannot make the review read another file on this machine;
- the copy cannot be pushed from (its push URL is disabled) and nothing is ever sent to GitHub
  except the requests that download it (git over https, plus the public REST API for the
  repository's size and a pull request's base branch; --no-api skips the API);
- an existing copy is replaced only when it carries this script's own marker.

History: by default the full history of the one branch is fetched, so security findings can be
traced to the commits that introduced them. Repositories above 300 MB, or a full fetch that does
not finish in time, fall back to a shallow copy (the latest commit only); the output says which
("history"). --depth N forces a shallow copy, --full forces full history.

Exit codes: 0 ok · 2 not a supported GitHub link · 5 could not download (not found, private,
network, timeout). Standard library only; needs the `git` command.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import SOURCE_MARKER, dump_json, eprint, load_json  # noqa: E402

GITHUB = "https://github.com"
API = "https://api.github.com"
REPOS_ENV = "CODE_REVIEW_REPOS_DIR"
BIG_REPO_KB = 300_000          # above this, fetch the latest commit only unless --full
DEFAULT_TIMEOUT = 540          # seconds for the whole download
FULL_ATTEMPT = 240             # seconds a full-history fetch may take before falling back to shallow
EXIT_BAD_LINK, EXIT_FETCH_FAILED = 2, 5

OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
REPO = r"[A-Za-z0-9._-]{1,100}"
SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")
RESERVED_OWNERS = {"orgs", "settings", "marketplace", "features", "topics", "sponsors", "about", "login", "apps",
                   "search", "notifications", "explore", "pulls", "issues", "collections", "trending"}


class FetchError(Exception):
    def __init__(self, reason, message, code=EXIT_FETCH_FAILED):
        super().__init__(message)
        self.reason, self.code = reason, code


# --- the link ---------------------------------------------------------------

def parse_url(url):
    """Split a GitHub link into owner, repo and what it points at. Raises FetchError for anything else."""
    text = (url or "").strip()
    bad = lambda why: FetchError("invalid_link", "%r is not a supported GitHub repository link: %s" % (url, why),
                                 EXIT_BAD_LINK)
    m = re.match(r"^(?:ssh://)?git@github\.com[:/](.+)$", text, re.I)
    if m:
        path = m.group(1)
    else:
        if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
            text = "https://" + text
        parts = urllib.parse.urlsplit(text)
        host = (parts.hostname or "").lower()
        if parts.scheme.lower() not in ("https", "http"):
            raise bad("only https links are supported")
        if parts.username or parts.password:
            raise bad("links that carry a user name or password are not accepted")
        if host not in ("github.com", "www.github.com"):
            raise bad("only repositories on github.com are supported (got %s)" % (host or "no host"))
        path = urllib.parse.unquote(parts.path)
    segs = [s for s in path.split("/") if s]
    if len(segs) < 2:
        raise bad("expected github.com/<owner>/<repository>")
    owner, repo = segs[0], segs[1]
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if not re.fullmatch(OWNER, owner) or owner.lower() in RESERVED_OWNERS:
        raise bad("%r is not a GitHub user or organization name" % owner)
    if not re.fullmatch(REPO, repo) or repo in (".", ".."):
        raise bad("%r is not a repository name" % repo)
    out = {"owner": owner, "repo": repo, "kind": "default", "rest": "", "number": None}
    rest = segs[2:]
    if not rest:
        return out
    kind, tail = rest[0], rest[1:]
    if any(s in (".", "..") or "\\" in s or "\0" in s for s in tail):
        raise bad("the path contains '.' or '..'")
    if kind in ("tree", "blob") and tail:
        out.update(kind=kind, rest="/".join(tail))
    elif kind in ("commit", "commits") and tail:
        if kind == "commit" and not SHA.match(tail[0]):
            raise bad("%r is not a commit hash" % tail[0])
        out.update(kind="commit" if kind == "commit" else "tree", rest="/".join(tail) if kind == "commits" else tail[0])
    elif kind == "pull" and tail and tail[0].isdigit():
        out.update(kind="pull", number=int(tail[0]))
    elif kind == "releases" and len(tail) >= 2 and tail[0] == "tag":
        out.update(kind="tag", rest="/".join(tail[1:]))
    elif kind in ("tree", "blob", "commit", "commits", "pull", "releases"):
        raise bad("the link is incomplete after /%s" % kind)
    # Any other page of the repository (issues, actions, wiki, …) means the repository itself.
    return out


# --- git, with nothing inherited that could prompt, authenticate or run code --------------------

def _env(protocols):
    env = dict(os.environ)
    for key in ("GIT_ASKPASS", "SSH_ASKPASS", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_SSH", "GIT_SSH_COMMAND"):
        env.pop(key, None)
    env.update(GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL=protocols, GIT_LFS_SKIP_SMUDGE="1",
               GCM_INTERACTIVE="never", GIT_OPTIONAL_LOCKS="0")
    return env


SAFE = ["-c", "credential.helper=", "-c", "core.askPass=", "-c", "core.hooksPath=" + os.devnull,
        "-c", "core.fsmonitor=false", "-c", "submodule.recurse=false", "-c", "fetch.recurseSubmodules=false"]


def _git(args, cwd=None, timeout=60, protocols="https"):
    cmd = ["git"] + (["-C", cwd] if cwd else []) + SAFE + list(args)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, errors="replace", env=_env(protocols),
                             timeout=max(1, timeout), stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise FetchError("git_missing", "the `git` command is not installed, so a GitHub repository cannot be downloaded")
    except subprocess.TimeoutExpired:
        raise FetchError("timeout", "git %s did not finish within %d seconds" % (args[0], timeout))
    if out.returncode != 0:
        raise _classify(args[0], out.stderr)
    return out.stdout


def _classify(what, stderr):
    msg = " ".join((stderr or "").split())[-400:]
    low = msg.lower()
    if any(k in low for k in ("repository not found", "could not read username", "authentication failed",
                              "terminal prompts disabled", "returned error: 404", "returned error: 403",
                              "returned error: 401")):
        return FetchError("not_found_or_private",
                          "GitHub did not serve this repository without signing in: it does not exist, or it is "
                          "private. Only public repositories can be reviewed from a link; for a private one, clone "
                          "it yourself and review the local folder.")
    if any(k in low for k in ("could not resolve host", "failed to connect", "unable to access", "timed out",
                              "connection refused", "network is unreachable", "ssl", "proxy")):
        return FetchError("network", "could not reach github.com from here (%s)" % msg)
    if "not allowed" in low and "transport" in low:
        return FetchError("transport", "Git is configured to rewrite GitHub links to another transport; only https "
                                       "is allowed here (%s)" % msg)
    return FetchError("git_failed", "git %s failed: %s" % (what, msg or "no error message"))


def ls_remote(remote, extra=(), protocols="https", timeout=60):
    """(default branch, {ref name: sha}) for HEAD, branches, tags and any extra ref patterns."""
    out = _git(["ls-remote", "--symref", remote, "HEAD", "refs/heads/*", "refs/tags/*"] + list(extra),
               timeout=timeout, protocols=protocols)
    default, refs = None, {}
    for line in out.splitlines():
        if line.startswith("ref: "):
            target, _, name = line[5:].partition("\t")
            if name.strip() == "HEAD" and target.startswith("refs/heads/"):
                default = target[len("refs/heads/"):]
            continue
        sha, _, name = line.partition("\t")
        if sha and name:
            refs[name.strip()] = sha.strip()
    return default, refs


def resolve(spec, default, refs, ref=None):
    """What to fetch: {"type": branch|tag|commit|pull, "name", "refspec"/"sha", "subdir", "focus"}."""
    def named(name):
        if "refs/heads/" + name in refs:
            return {"type": "branch", "name": name, "sha": refs["refs/heads/" + name]}
        if "refs/tags/" + name in refs:
            return {"type": "tag", "name": name, "sha": refs.get("refs/tags/" + name + "^{}") or refs["refs/tags/" + name]}
        if SHA.match(name):
            return {"type": "commit", "name": name.lower(), "sha": name.lower()}
        return None

    kind = spec["kind"]
    if ref:                                           # an explicit --ref wins over the link
        got = named(ref)
        if not got:
            raise FetchError("ref_not_found", "the repository has no branch or tag named %r" % ref)
        return dict(got, subdir="", focus="")         # the link's own ref and folder no longer apply
    if kind == "pull":
        name = "refs/pull/%d/head" % spec["number"]
        if name not in refs:
            raise FetchError("ref_not_found", "pull request #%d was not found in this repository" % spec["number"])
        return {"type": "pull", "name": "pull/%d" % spec["number"], "sha": refs[name], "subdir": "", "focus": ""}
    if kind == "default":
        if not default or "refs/heads/" + default not in refs:
            raise FetchError("empty", "the repository has no commits on a default branch yet")
        return {"type": "branch", "name": default, "sha": refs["refs/heads/" + default], "subdir": "", "focus": ""}
    if kind in ("commit", "tag"):
        got = named(spec["rest"]) if kind == "commit" else (
            {"type": "tag", "name": spec["rest"], "sha": refs.get("refs/tags/" + spec["rest"] + "^{}") or
             refs["refs/tags/" + spec["rest"]]} if "refs/tags/" + spec["rest"] in refs else None)
        if not got:
            raise FetchError("ref_not_found", "the repository has no %s %r" % (kind, spec["rest"]))
        return dict(got, subdir="", focus="")
    # tree/blob: branch and tag names may contain "/", so the longest name that exists wins.
    segs = spec["rest"].split("/")
    for n in range(len(segs), 0, -1):
        got = named("/".join(segs[:n]))
        if got and (got["type"] != "commit" or n == 1):
            sub = "/".join(segs[n:])
            return dict(got, subdir=sub if kind == "tree" else "", focus=sub if kind == "blob" else "")
    raise FetchError("ref_not_found", "the repository has no branch, tag or commit matching %r" % spec["rest"])


# --- the GitHub REST API: public, unauthenticated, optional -------------------------------------

def api_get(path, timeout=8):
    req = urllib.request.Request(API + path, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "917v-code-review"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError:
        return None                                   # rate limited or not found: the download does not need it
    except (urllib.error.URLError, OSError, ValueError):
        pass
    # Python without a CA bundle (common on macOS) cannot verify github.com; curl uses the system's.
    curl = shutil.which("curl")
    if not curl:
        return None
    try:
        out = subprocess.run([curl, "-sS", "-f", "--proto", "=https", "--max-redirs", "2", "--max-time", str(timeout),
                              "-H", "Accept: application/vnd.github+json", "-A", "917v-code-review", API + path],
                             capture_output=True, text=True, errors="replace", timeout=timeout + 2,
                             stdin=subprocess.DEVNULL, env=_env("https"))
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


# --- the local copy -----------------------------------------------------------------------------

def repos_dir():
    return os.path.abspath(os.environ.get(REPOS_ENV) or os.path.join(os.path.expanduser("~"), ".917v-code-review", "repos"))


def clone_path(owner, repo):
    return os.path.join(repos_dir(), owner.lower(), repo.lower())


def marker_path(clone):
    return os.path.join(clone, ".git", SOURCE_MARKER)


def read_marker(clone):
    try:
        data = load_json(marker_path(clone))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _rmtree(path):
    def retry(func, p, _exc):                         # read-only pack files on Windows
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=retry)


def remove(clone):
    """Delete a downloaded copy. Only folders carrying this script's marker are ever deleted."""
    if not os.path.exists(clone):
        return False
    if not read_marker(clone):
        raise FetchError("not_ours", "%s exists but was not created by this script, so it is left alone. Move it "
                                     "away or set %s to another folder." % (clone, REPOS_ENV))
    _rmtree(clone)
    return True


def _download(remote, tmp, target, depth, extra_refspecs, protocols, timeout):
    """Fetch one commit (and its history, or `depth` commits of it) into a new repository and check it out."""
    os.makedirs(tmp)
    _git(["init", "-q", "--template=", tmp], timeout=30)
    for key, value in (("core.symlinks", "false"), ("core.hooksPath", os.devnull), ("core.fsmonitor", "false"),
                       ("core.autocrlf", "false"), ("gc.auto", "0"), ("advice.detachedHead", "false"),
                       ("remote.origin.url", remote),
                       ("remote.origin.pushurl", "no-push://this-copy-is-for-reading-only")):
        _git(["config", key, value], cwd=tmp, timeout=30)
    via = target.get("via")                           # an abbreviated commit hash: found in this branch's history
    if target["type"] == "branch" or via:
        name = via or target["name"]
        spec = "+refs/heads/%s:refs/remotes/origin/%s" % (name, name)
    elif target["type"] == "tag":
        spec = "+refs/tags/%s:refs/tags/%s" % (target["name"], target["name"])
    elif target["type"] == "pull":
        spec = "+refs/%s/head:refs/remotes/origin/%s" % (target["name"], target["name"].replace("/", "-"))
    else:
        spec = target["sha"]
    args = ["fetch", "-q", "--no-tags", "--no-recurse-submodules"] + (["--depth", str(depth)] if depth else [])
    _git(args + ["origin", spec] + list(extra_refspecs), cwd=tmp, timeout=timeout, protocols=protocols)
    if via:
        try:
            commit = _git(["rev-parse", "--verify", target["sha"] + "^{commit}"], cwd=tmp).strip()
        except FetchError:
            raise FetchError("ref_not_found", "commit %s was not found in the history of %s; give the full "
                                              "40-character commit hash" % (target["sha"], via))
    elif target["type"] == "commit":
        commit = _git(["rev-parse", "--verify", "FETCH_HEAD^{commit}"], cwd=tmp).strip()
    else:
        commit = _git(["rev-parse", "--verify", spec.split(":", 1)[1] + "^{commit}"], cwd=tmp).strip()
    _git(["checkout", "-q", "--detach", commit], cwd=tmp, timeout=max(60, timeout), protocols=protocols)
    return commit


def fetch(url, ref=None, depth=None, full=False, use_api=True, timeout=DEFAULT_TIMEOUT, refresh=False,
          remote_base=GITHUB):
    """Download (or reuse) the repository behind a GitHub link. Returns the result dict printed by the CLI.

    remote_base exists for the offline tests, which serve a local bare repository in place of github.com.
    """
    started = time.time()
    left = lambda: int(timeout - (time.time() - started))
    spec = parse_url(url)
    online = remote_base == GITHUB
    protocols = "https" if online else "file"
    owner, repo = spec["owner"], spec["repo"]
    remote = "%s/%s/%s.git" % (remote_base.rstrip("/"), owner, repo)
    notes = []

    info = api_get("/repos/%s/%s" % (owner, repo)) if online and use_api else None
    if isinstance(info, dict) and info.get("full_name") and "/" in str(info["full_name"]):
        o, r = str(info["full_name"]).split("/", 1)
        if re.fullmatch(OWNER, o) and re.fullmatch(REPO, r) and (o.lower(), r.lower()) == (owner.lower(), repo.lower()):
            owner, repo = o, r                         # GitHub's own spelling of the name
    size_kb = info.get("size") if isinstance(info, dict) and isinstance(info.get("size"), int) else None

    extra = ["refs/pull/%d/head" % spec["number"]] if spec["kind"] == "pull" else []
    default, refs = ls_remote(remote, extra, protocols, timeout=min(60, max(5, left())))
    target = resolve(spec, default, refs, ref)

    # A pull request is reviewed as a diff against its base branch, which needs both histories in full.
    base, extra_refspecs = None, []
    if target["type"] == "pull":
        pr = api_get("/repos/%s/%s/pulls/%d" % (owner, repo, spec["number"])) if online and use_api else None
        base = ((pr or {}).get("base") or {}).get("ref") if isinstance(pr, dict) else None
        if not base or "refs/heads/" + base not in refs:
            base = default
            notes.append("the pull request's base branch could not be read from GitHub, so the default branch "
                         "(%s) is used as the base" % default)
        if not base:
            raise FetchError("ref_not_found", "the repository has no default branch to compare the pull request with")
        extra_refspecs = ["+refs/heads/%s:refs/remotes/origin/%s" % (base, base)]
        if depth:
            notes.append("--depth is ignored for a pull request: comparing it with its base needs the full history")
        depth, full = None, True
    if target["type"] == "commit" and len(target["sha"]) < 40:
        if not default:
            raise FetchError("ref_not_found", "give the full 40-character commit hash for this repository")
        target["via"] = default
        if depth:
            notes.append("--depth is ignored for an abbreviated commit hash: finding it needs the branch history")
        depth, full = None, True
    if isinstance(info, dict):
        if info.get("archived"):
            notes.append("the repository is archived (read-only on GitHub)")
        if info.get("fork"):
            notes.append("the repository is a fork")

    if depth:
        plan = [depth]
    elif full:
        plan = [None]
    elif size_kb is not None and size_kb > BIG_REPO_KB:
        plan = [1]
        notes.append("the repository is large (about %d MB), so only the latest commit was fetched; pass --full "
                     "for the whole history" % (size_kb // 1000))
    else:
        plan = [None, 1]                               # full history, then shallow if that takes too long

    dest = clone_path(owner, repo)
    old = read_marker(dest) if os.path.isdir(dest) else None
    if os.path.exists(dest) and not old:
        raise FetchError("not_ours", "%s exists but was not created by this script, so it is left alone. Move it "
                                     "away or set %s to another folder." % (dest, REPOS_ENV))
    reused = False
    if old and not refresh and str(old.get("commit") or "").startswith(target["sha"]) and old.get("ref") == target["name"] and \
            (old.get("history") == "full" or (plan[0] and old.get("depth") == plan[0])) and \
            (target["type"] != "pull" or old.get("base") == base):
        try:
            clean = not _git(["status", "--porcelain"], cwd=dest).strip()
            reused = clean and _git(["rev-parse", "HEAD"], cwd=dest).strip() == old["commit"]
        except FetchError:
            reused = False
    if reused:
        commit, used_depth = old["commit"], old.get("depth")
    else:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = "%s.tmp-%d" % (dest, os.getpid())
        commit = used_depth = None
        for i, d in enumerate(plan):
            if os.path.exists(tmp):
                _rmtree(tmp)
            last = i == len(plan) - 1
            budget = max(10, left() if last else min(FULL_ATTEMPT, left() - 60))
            try:
                commit, used_depth = _download(remote, tmp, target, d, extra_refspecs, protocols, budget), d
                break
            except FetchError as e:
                if os.path.exists(tmp):
                    _rmtree(tmp)
                if last or e.reason != "timeout":
                    raise
                notes.append("fetching the full history took too long, so only the latest commit was fetched")
        if old:
            _rmtree(dest)
        os.replace(tmp, dest)

    subdir = target.get("subdir") or ""
    root = dest
    if subdir:
        candidate = os.path.realpath(os.path.join(dest, subdir))
        if candidate.startswith(os.path.realpath(dest) + os.sep) and os.path.isdir(candidate):
            root = os.path.join(dest, *subdir.split("/"))
        else:
            notes.append("%r is not a folder at this ref, so the whole repository is reviewed" % subdir)
            subdir = ""

    diff = None
    if target["type"] == "pull":
        try:
            mb = _git(["merge-base", "refs/remotes/origin/" + base, "HEAD"], cwd=dest).strip()
            diff = {"range": "%s..HEAD" % mb, "base": base, "pull": spec["number"]}
        except FetchError:
            notes.append("the pull request shares no history with %s, so it cannot be reviewed as a diff" % base)

    web = "%s/%s/%s" % (GITHUB, owner, repo)
    marker = {"provider": "github", "owner": owner, "repo": repo, "url": web, "ref": target["name"],
              "ref_type": target["type"], "commit": commit, "history": "shallow" if used_depth else "full",
              "depth": used_depth, "base": base, "pull": spec["number"],
              "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if not reused:
        dump_json(marker, marker_path(dest))
    result = {
        "root": root, "clone": dest, "reused": reused,
        "source": {"provider": "github", "name": "%s/%s" % (owner, repo), "url": web, "ref": target["name"],
                   "ref_type": target["type"], "commit": commit, "short": commit[:8], "subdir": subdir,
                   "pull": spec["number"]},
        "history": marker["history"] if not reused else old.get("history"), "depth": used_depth,
        "diff": diff, "focus": target.get("focus") or None, "size_kb": size_kb, "notes": notes,
    }
    return result


def listing():
    base, out = repos_dir(), []
    if os.path.isdir(base):
        for owner in sorted(os.listdir(base)):
            folder = os.path.join(base, owner)
            for repo in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
                m = read_marker(os.path.join(folder, repo))
                if m:
                    out.append({"clone": os.path.join(folder, repo), "url": m.get("url"), "ref": m.get("ref"),
                                "commit": (m.get("commit") or "")[:8], "history": m.get("history"),
                                "fetched_at": m.get("fetched_at")})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url", nargs="?", help="a public GitHub repository link")
    ap.add_argument("--ref", help="branch, tag or commit to review (overrides the one in the link)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--depth", type=int, metavar="N", help="fetch only the latest N commits (shallow)")
    g.add_argument("--full", action="store_true", help="always fetch the full history of the branch")
    ap.add_argument("--no-api", action="store_true", help="do not call api.github.com (size and pull-request base)")
    ap.add_argument("--refresh", action="store_true", help="download again even when the copy is up to date")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds for the whole download")
    ap.add_argument("--list", action="store_true", help="list the downloaded copies")
    ap.add_argument("--remove", action="store_true", help="delete the downloaded copy of this link")
    a = ap.parse_args()
    try:
        if a.list:
            return dump_json({"repos_dir": repos_dir(), "repositories": listing()})
        if not a.url:
            ap.error("a GitHub repository link is required")
        if a.depth is not None and a.depth < 1:
            ap.error("--depth must be 1 or more")
        if a.remove:
            spec = parse_url(a.url)
            path = clone_path(spec["owner"], spec["repo"])
            return dump_json({"removed": remove(path), "clone": path})
        dump_json(fetch(a.url, ref=a.ref, depth=a.depth, full=a.full, use_api=not a.no_api, timeout=a.timeout,
                        refresh=a.refresh))
    except FetchError as e:
        eprint("fetch-repo: " + str(e))
        dump_json({"error": str(e), "reason": e.reason})
        sys.exit(e.code)


if __name__ == "__main__":
    main()
