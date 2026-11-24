#!/usr/bin/env python3
"""Loopback-only viewer for a finished review, so the dashboard and Explore open with one click.

The in-chat results widget cannot open file:// pages, so its "Explore" and "Open the full
dashboard" buttons need real URLs. This script serves one report folder on 127.0.0.1:

  http://127.0.0.1:<port>/<token>/dashboard.html
  http://127.0.0.1:<port>/<token>/explore.html
  http://127.0.0.1:<port>/<token>/_src/<path>?line=N   read-only view of one repository file

Guarantees:
- binds 127.0.0.1 only, on a free port; never reachable from another machine;
- every URL carries a random token, so other local users cannot guess it;
- GET/HEAD only, and nothing is ever written to the repository or to the reports;
- serves only the report files of that folder and, under _src/, files inside the repository,
  with secret values redacted exactly as in the reports;
- stops by itself after --idle-minutes without a request (default 120).

Usage:
  serve-reports.py --root <repo> -o <out>            start (or reuse) the viewer, print its URLs as JSON
  serve-reports.py --root <repo> -o <out> --stop     stop it
Standard library only.
"""

import argparse
import html
import http.server
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import check_output_path, dump_json, load_json, redact  # noqa: E402

PING = b"917v-code-review viewer"
STATE = os.path.join(".work", "viewer.json")
TYPES = {".html": "text/html; charset=utf-8", ".md": "text/plain; charset=utf-8",
         ".json": "application/json; charset=utf-8"}
MAX_SOURCE_BYTES = 2_000_000
SOURCE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
:root { --bg:#FAFBFF; --fg:#040815; --muted:#606471; --border:#D0D5DD; --hit:#FFF4E0; --hit-b:#B45309; }
@media (prefers-color-scheme: dark) { :root { --bg:#0B1220; --fg:#F5F7FB; --muted:#A4A6BA; --border:#2A3B57; --hit:#3D2A0A; --hit-b:#F5B553; color-scheme:dark; } }
body { margin:0; background:var(--bg); color:var(--fg); font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
header { position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--border); padding:10px 16px; font-family:system-ui,sans-serif; }
header b { font-size:14px; } header span { color:var(--muted); font-size:12px; margin-left:8px; }
ol { margin:0; padding:8px 0 40px 0; list-style:none; counter-reset:n; }
li { counter-increment:n; white-space:pre; padding:0 16px 0 0; scroll-margin-top:80px; }
li::before { content:counter(n); display:inline-block; width:56px; padding-right:14px; text-align:right; color:var(--muted); user-select:none; }
li.hit { background:var(--hit); box-shadow:inset 3px 0 0 var(--hit-b); }
</style></head><body>
<header><b>%(title)s</b><span>read-only view from the code review · secret values are redacted</span></header>
<ol>%(rows)s</ol>
<script>var h = document.querySelector("li.hit"); if (h) h.scrollIntoView({ block: "center" });</script>
</body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "917v-code-review"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.route(True)

    def do_HEAD(self):
        self.route(False)

    def reply(self, code, ctype, data, body=True):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if body:
            self.wfile.write(data)

    def route(self, body):
        srv = self.server
        srv.last_request = time.time()
        host = (self.headers.get("Host") or "").split(":")[0]
        parts = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parts.path)
        prefix = "/" + srv.token + "/"
        if host not in ("127.0.0.1", "localhost") or not path.startswith(prefix):
            return self.reply(404, "text/plain; charset=utf-8", b"Not found", body)
        rel = path[len(prefix):]
        if rel == "_ping":
            return self.reply(200, "text/plain; charset=utf-8", PING, body)
        if rel.startswith("_src/"):
            return self.source(rel[5:], urllib.parse.parse_qs(parts.query), body)
        return self.report(rel or "dashboard.html", body)

    def report(self, rel, body):
        """Report files sit directly in the report folder; no subfolders, no dotfiles (so not .work/)."""
        ext = os.path.splitext(rel)[1].lower()
        full = os.path.join(self.server.out, rel)
        if "/" in rel or "\\" in rel or rel.startswith(".") or ext not in TYPES or not os.path.isfile(full):
            return self.reply(404, "text/plain; charset=utf-8", b"Not found", body)
        with open(full, "rb") as fh:
            self.reply(200, TYPES[ext], fh.read(), body)

    def source(self, rel, query, body):
        """One repository file as a read-only, line-numbered page. Never leaves the repository root."""
        root = os.path.realpath(self.server.root)
        full = os.path.realpath(os.path.join(root, rel))
        if not rel or not full.startswith(root + os.sep) or not os.path.isfile(full):
            return self.reply(404, "text/plain; charset=utf-8", b"Not found", body)
        if os.path.getsize(full) > MAX_SOURCE_BYTES:
            return self.reply(413, "text/plain; charset=utf-8", b"File is too large to show here.", body)
        with open(full, "rb") as fh:
            raw = fh.read()
        if b"\0" in raw:
            return self.reply(415, "text/plain; charset=utf-8", b"Binary file.", body)

        def num(key):
            try:
                return int((query.get(key) or ["0"])[0])
            except ValueError:
                return 0
        lo = num("line")
        hi = max(lo, num("end"))
        lines = raw.decode("utf-8", "replace").splitlines()
        shown = redact("\n".join(lines)).split("\n")
        if len(shown) != len(lines):                 # never let redaction shift the line numbers
            shown = [redact(line) for line in lines]
        rows = "".join('<li id="L%d"%s>%s</li>' % (i, ' class="hit"' if lo and lo <= i <= hi else "", html.escape(line))
                       for i, line in enumerate(shown, 1))
        title = html.escape(rel + (":%d" % lo if lo else ""))
        self.reply(200, TYPES[".html"], (SOURCE_PAGE % {"title": title, "rows": rows}).encode("utf-8"), body)


def state_path(out):
    return os.path.join(out, STATE)


def read_state(out):
    try:
        return load_json(state_path(out))
    except (OSError, ValueError):
        return None


def alive(state):
    try:
        with urllib.request.urlopen(state["url"] + "/_ping", timeout=1.5) as r:
            return r.read() == PING
    except Exception:
        return False


def urls(state, reused):
    return {"url": state["url"], "dashboard": state["url"] + "/dashboard.html",
            "explore": state["url"] + "/explore.html", "port": state["port"], "pid": state["pid"],
            "reused": reused, "idle_minutes": state.get("idle_minutes")}


def run(root, out, token, idle_minutes):
    """The server process itself: serve until idle, then exit and remove the state file."""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    srv.root, srv.out, srv.token, srv.last_request = root, out, token, time.time()
    port = srv.server_address[1]
    state = {"pid": os.getpid(), "port": port, "token": token, "url": "http://127.0.0.1:%d/%s" % (port, token),
             "root": root, "out": out, "idle_minutes": idle_minutes, "started": int(time.time())}
    os.makedirs(os.path.dirname(state_path(out)), exist_ok=True)
    dump_json(state, state_path(out))

    def watchdog():
        while time.time() - srv.last_request < idle_minutes * 60:
            time.sleep(min(30, max(1, idle_minutes * 60 / 4)))
        srv.shutdown()
    threading.Thread(target=watchdog, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *a: threading.Thread(target=srv.shutdown, daemon=True).start())
    try:
        srv.serve_forever()
    finally:
        srv.server_close()
        current = read_state(out)
        if current and current.get("token") == token:
            try:
                os.remove(state_path(out))
            except OSError:
                pass


def start(root, out, idle_minutes=120, wait=5.0):
    """Start the viewer for this report folder, or reuse the one already running. Returns its URLs, or None."""
    root, out = os.path.abspath(root), os.path.abspath(out)
    check_output_path(root, out)
    state = read_state(out)
    if state and state.get("root") == root and alive(state):
        return urls(state, True)
    token = secrets.token_urlsafe(9)
    cmd = [sys.executable, os.path.abspath(__file__), "--run", "--root", root, "-o", out, "--token", token,
           "--idle-minutes", str(idle_minutes)]
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "close_fds": True, "cwd": out}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kwargs)
    except OSError:
        return None
    deadline = time.time() + wait
    while time.time() < deadline:
        state = read_state(out)
        if state and state.get("token") == token and alive(state):
            return urls(state, False)
        time.sleep(0.1)
    return None


def stop(out):
    state = read_state(os.path.abspath(out))
    if not state:
        return False
    try:
        os.kill(int(state["pid"]), signal.SIGTERM)
    except (OSError, ValueError, KeyError):
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, help="the reviewed repository (read-only source for _src/)")
    ap.add_argument("-o", "--out", required=True, help="the report folder to serve")
    ap.add_argument("--idle-minutes", type=float, default=120)
    ap.add_argument("--stop", action="store_true", help="stop the viewer of this report folder")
    ap.add_argument("--run", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--token", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.run:
        return run(os.path.abspath(a.root), os.path.abspath(a.out), a.token or secrets.token_urlsafe(9),
                   a.idle_minutes)
    if a.stop:
        return dump_json({"stopped": stop(a.out)})
    viewer = start(a.root, a.out, a.idle_minutes)
    dump_json({"viewer": viewer})
    if not viewer:
        sys.exit(1)


if __name__ == "__main__":
    main()
