#!/usr/bin/env python3
"""Unit tests for the deterministic scripts. Standard library only.

Run: python3 -m unittest discover -s tests -v   (from the plugin root)
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)

import _common  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


detect = load("detect-stack")
diffscope = load("diff-scope")
signals = load("scan-signals")
graph = load("import-graph")
integrity = load("integrity")
validate = load("validate-findings")
render = load("render-reports")
serve = load("serve-reports")
history = load("git-history")
fetch = load("fetch-repo")


os.environ[_common.OUT_ENV] = tempfile.mkdtemp(prefix="cr-out-")   # never write to ~ during tests


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, "-c", "user.email=t@example.com", "-c", "user.name=t"] + list(args),
                   check=True, capture_output=True)


class TestDetectStack(unittest.TestCase):
    def fw(self, fixture):
        r = detect.detect(os.path.join(FIXTURES, fixture))
        return r, {f["name"]: f for f in r["frameworks"]}

    def test_nestjs(self):
        r, fw = self.fw("nestjs-orders-api")
        self.assertEqual(fw["NestJS"]["confidence"], "confirmed")
        self.assertIn("Node.js", r["runtimes"])
        self.assertIn("TypeORM", [d["name"] for d in r["databases"]])
        self.assertIn("Docker", [i["name"] for i in r["infrastructure"]])
        self.assertIn("GitHub Actions", [i["name"] for i in r["ci_cd"]])
        self.assertIn("src/main.ts", [e["file"] for e in r["entry_points"]])
        agents = [a["agent"] for a in r["recommended_agents"]]
        self.assertNotIn("frontend-reviewer", agents)
        self.assertIn("devops-reviewer", agents)

    def test_nextjs(self):
        r, fw = self.fw("nextjs-shop")
        self.assertEqual(fw["Next.js"]["confidence"], "confirmed")
        self.assertEqual(fw["Next.js"]["version"], "14.1.0")
        self.assertIn("React", fw)
        self.assertIn("Prisma", [d["name"] for d in r["databases"]])
        eps = [e["file"] for e in r["entry_points"]]
        self.assertIn("app/api/orders/route.ts", eps)
        self.assertIn("app/actions.ts", eps)
        agents = [a["agent"] for a in r["recommended_agents"]]
        self.assertIn("frontend-reviewer", agents)
        self.assertIn("backend-reviewer", agents)
        self.assertNotIn("devops-reviewer", agents)

    def test_spring(self):
        r, fw = self.fw("spring-bank-api")
        self.assertEqual(fw["Spring Boot"]["confidence"], "confirmed")
        self.assertEqual(fw["Spring Boot"]["version"], "3.2.1")
        self.assertIn("Maven", r["projects"][0]["package_managers"])
        self.assertIn("Flyway", [d["name"] for d in r["databases"]])

    def test_folder_name_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "nestjs", "next", "django"))
            open(os.path.join(d, "nestjs", "next", "django", "x.txt"), "w").write("hi")
            r = detect.detect(d)
            self.assertEqual(r["frameworks"], [])

    def test_manifest_only_framework(self):
        with tempfile.TemporaryDirectory() as d:
            json.dump({"dependencies": {"express": "^4.0.0"}}, open(os.path.join(d, "package.json"), "w"))
            open(os.path.join(d, "index.js"), "w").write("console.log('no server here')\n")
            r = detect.detect(d)
            self.assertEqual(r["frameworks"][0]["name"], "Express")
            self.assertEqual(r["frameworks"][0]["confidence"], "manifest-only")

    def test_python_go_php_terraform(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "requirements.txt"), "w").write("fastapi==0.110.0\nsqlalchemy>=2\npytest\n")
            open(os.path.join(d, "main.py"), "w").write("from fastapi import FastAPI\napp = FastAPI()\n")
            os.makedirs(os.path.join(d, "svc"))
            open(os.path.join(d, "svc", "go.mod"), "w").write(
                "module example.com/svc\n\ngo 1.22\n\nrequire github.com/gin-gonic/gin v1.9.1\n")
            open(os.path.join(d, "svc", "main.go"), "w").write(
                "package main\nimport \"github.com/gin-gonic/gin\"\nfunc main() { r := gin.Default(); r.Run() }\n")
            os.makedirs(os.path.join(d, "web"))
            json.dump({"require": {"laravel/framework": "^11.0"}}, open(os.path.join(d, "web", "composer.json"), "w"))
            open(os.path.join(d, "web", "artisan"), "w").write("#!/usr/bin/env php\n")
            open(os.path.join(d, "web", "app.php"), "w").write("<?php use Illuminate\\Support\\Facades\\Route;\n")
            open(os.path.join(d, "main.tf"), "w").write('provider "aws" {\n  region = "us-east-1"\n}\n')
            r = detect.detect(d)
            names = {f["name"]: f["confidence"] for f in r["frameworks"]}
            self.assertEqual(names.get("FastAPI"), "confirmed")
            self.assertEqual(names.get("Gin"), "confirmed")
            self.assertEqual(names.get("Laravel"), "confirmed")
            tf = [i for i in r["infrastructure"] if i["name"] == "Terraform"][0]
            self.assertIn("aws", tf["providers"])
            self.assertEqual(r["architecture_shape"], "monorepo / multi-project")


class TestDiffScope(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        git(self.d, "init", "-q", "-b", "main")
        open(os.path.join(self.d, "a.py"), "w").write("one\ntwo\nthree\nfour\n")
        git(self.d, "add", ".")
        git(self.d, "commit", "-qm", "init")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_uncommitted_staged_branch(self):
        open(os.path.join(self.d, "a.py"), "w").write("one\nTWO\nthree\nfour\nfive\n")
        open(os.path.join(self.d, "new.py"), "w").write("x = 1\ny = 2\n")
        s = diffscope.compute(self.d, "uncommitted")
        files = {f["file"]: f for f in s["files"]}
        self.assertEqual(files["a.py"]["ranges"], [[2, 2], [5, 5]])
        self.assertEqual(files["new.py"]["status"], "untracked")
        self.assertEqual(files["new.py"]["ranges"], [[1, 2]])
        self.assertEqual(diffscope.compute(self.d, "staged")["files"], [])
        git(self.d, "add", "a.py")
        self.assertEqual([f["file"] for f in diffscope.compute(self.d, "staged")["files"]], ["a.py"])
        git(self.d, "checkout", "-qb", "feature")
        git(self.d, "commit", "-qm", "change")
        b = diffscope.compute(self.d, "branch", base="main")
        self.assertEqual([f["file"] for f in b["files"]], ["a.py"])

    def test_ignores_review_output(self):
        os.makedirs(os.path.join(self.d, "docs", "code-review"))
        open(os.path.join(self.d, "docs", "code-review", "x.md"), "w").write("report\n")
        self.assertEqual(diffscope.compute(self.d, "uncommitted")["files"], [])


class TestSignalsAndGraph(unittest.TestCase):
    def test_signals_redact_secrets(self):
        out = signals.scan(os.path.join(FIXTURES, "nestjs-orders-api"))
        text = json.dumps(out)
        self.assertNotIn("Pr0d-Orders-DB-2024!", text)
        self.assertNotIn("orders-jwt-signing-key-9f8e7d6c", text)
        rules = {s["rule"] for s in out["signals"]}
        self.assertTrue({"sql-string-building", "hardcoded-secret", "jwt-handling", "schema-auto-sync"} <= rules)

    def test_quick_scan(self):
        fixture = os.path.join(FIXTURES, "nestjs-orders-api")
        with tempfile.TemporaryDirectory() as tmp:
            run = lambda *a: subprocess.run([sys.executable, *a], check=True, capture_output=True, text=True).stdout
            run(os.path.join(SCRIPTS, "detect-stack.py"), fixture, "-o", os.path.join(tmp, "stack.json"))
            run(os.path.join(SCRIPTS, "scan-signals.py"), fixture, "-o", os.path.join(tmp, "signals.json"))
            run(os.path.join(SCRIPTS, "import-graph.py"), fixture, "-o", os.path.join(tmp, "imports.json"))
            out = os.path.join(tmp, "out")
            summary = json.loads(run(os.path.join(SCRIPTS, "render-scan.py"), "--root", fixture,
                                     "--stack", os.path.join(tmp, "stack.json"),
                                     "--signals", os.path.join(tmp, "signals.json"),
                                     "--imports", os.path.join(tmp, "imports.json"), "-o", out))
            text = open(os.path.join(out, "scan.md"), encoding="utf-8").read()
            self.assertEqual(sorted(os.listdir(out)), [_common.MARKER, "scan.md"])
        self.assertGreater(summary["leads"], 5)
        self.assertEqual(summary["import_cycles"], 3)
        self.assertIn("Security", summary["leads_by_area"])
        self.assertIn("leads, not findings", text)
        base = os.path.relpath(fixture, out).replace(os.sep, "/")
        self.assertIn("[`src/users/users.service.ts:24`](%s/src/users/users.service.ts#L24)" % base, text)
        self.assertIn("`` return this.dataSource.query(`SELECT", text)   # backticks in snippets kept verbatim
        self.assertNotIn("Pr0d-Orders-DB-2024!", text)
        self.assertNotIn("orders-jwt-signing-key-9f8e7d6c", text)
        self.assertIn("/917v-code-review:review", text)

    def test_prepare_review_one_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            shutil.copytree(os.path.join(FIXTURES, "nestjs-orders-api"), repo)
            out = os.path.join(tmp, "out")
            p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "prepare-review.py"), repo, "--out", out],
                               check=True, capture_output=True, text=True)
            summary = json.loads(p.stdout[p.stdout.index("{"):])
            work = os.path.join(out, ".work")
            self.assertEqual(summary["out"], out)
            self.assertFalse(os.path.exists(os.path.join(repo, "docs")))          # nothing inside the repo
            for name in ("baseline.json", "stack.json", "files.txt", "signals.json", "import-graph.json"):
                self.assertTrue(os.path.isfile(os.path.join(work, name)), name)
            self.assertEqual(len(os.listdir(os.path.join(work, "agents"))), 8)
            sec = open(os.path.join(work, "agents", "security-reviewer.md"), encoding="utf-8").read()
            arc = open(os.path.join(work, "agents", "architecture-reviewer.md"), encoding="utf-8").read()
            self.assertIn("files: 22", p.stdout)                                  # stack digest printed
            self.assertEqual(summary["import_cycles"], 3)
            self.assertIn("NestJS", summary["checklist_sections"])
            self.assertNotIn("Java / Spring Boot", summary["checklist_sections"])
            self.assertIn("src/users/users.service.ts:24", sec)                     # its own signals
            self.assertNotIn("[docker-unpinned-base]", sec)                         # not devops' signals
            self.assertIn("## NestJS", sec)
            self.assertIn("## Import cycles", arc)
            self.assertNotIn("Pr0d-Orders-DB-2024!", sec)
            # Integrity check inside render-reports (--baseline): nothing changed yet.
            self.assertTrue(integrity.verify(repo, json.load(open(os.path.join(work, "baseline.json"))))["unchanged"])

    def test_prepare_review_empty_diff_and_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            shutil.copytree(os.path.join(FIXTURES, "nestjs-orders-api"), repo)
            git(repo, "init", "-q", "-b", "main")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "init")
            script = os.path.join(SCRIPTS, "prepare-review.py")
            out = os.path.join(tmp, "out")
            p = subprocess.run([sys.executable, script, repo, "--mode", "diff", "--out", out], capture_output=True, text=True)
            self.assertEqual(p.returncode, 3)
            self.assertIn('"nothing_to_review": true', p.stdout)
            p = subprocess.run([sys.executable, script, repo, "--mode", "scan", "--out", out],
                               check=True, capture_output=True, text=True)
            summary = json.loads(p.stdout[p.stdout.index("{"):])
            git(repo, "status")
            self.assertEqual(subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True,
                                            text=True).stdout, "")                 # repo untouched
            self.assertTrue(os.path.isfile(os.path.join(out, "scan.md")))
            self.assertFalse(os.path.exists(os.path.join(out, ".work", "baseline.json")))  # scan skips the baseline
            self.assertFalse(os.path.exists(os.path.join(out, ".work", "agents")))
            self.assertGreater(summary["leads"], 5)

    def test_read_only_guards(self):
        script = os.path.join(SCRIPTS, "prepare-review.py")
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            shutil.copytree(os.path.join(FIXTURES, "nestjs-orders-api"), repo)
            # 1. Default output is outside the repository, named after it.
            default = _common.default_output_dir(repo)
            self.assertFalse(_common._inside(default, repo))
            self.assertTrue(os.path.basename(default).startswith("repo-"))
            # 2. Any output inside the repository is refused, including the old docs/code-review/.
            for inside in (os.path.join(repo, "docs", "code-review"), os.path.join(repo, "src", "x.json")):
                with self.assertRaises(SystemExit):
                    _common.check_output_path(repo, inside)
            p = subprocess.run([sys.executable, script, repo, "--out", os.path.join(repo, "docs", "code-review")],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, _common.EXIT_OUTPUT_CONFLICT)
            self.assertFalse(os.path.exists(os.path.join(repo, "docs")))
            p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "scan-signals.py"), repo,
                                "-o", os.path.join(repo, "src", "signals.json")], capture_output=True, text=True)
            self.assertEqual(p.returncode, _common.EXIT_OUTPUT_CONFLICT)
            self.assertFalse(os.path.exists(os.path.join(repo, "src", "signals.json")))
            # 3. A folder the user owns is never written to.
            mine = os.path.join(tmp, "mine")
            os.makedirs(mine)
            with open(os.path.join(mine, "notes.md"), "w") as fh:
                fh.write("mine\n")
            p = subprocess.run([sys.executable, script, repo, "--out", mine], capture_output=True, text=True)
            self.assertEqual(p.returncode, _common.EXIT_OUTPUT_CONFLICT)
            self.assertEqual(os.listdir(mine), ["notes.md"])
            # 4. A fresh or previously claimed folder is used and marked.
            out = os.path.join(tmp, "out")
            subprocess.run([sys.executable, script, repo, "--mode", "scan", "--out", out], check=True, capture_output=True)
            self.assertTrue(os.path.isfile(os.path.join(out, _common.MARKER)))
            subprocess.run([sys.executable, script, repo, "--mode", "scan", "--out", out], check=True, capture_output=True)
            # 5. Only read-only git subcommands are allowed.
            with self.assertRaises(SystemExit):
                _common.git(repo, "checkout", "-b", "x")
            with self.assertRaises(SystemExit):
                _common.git(repo, "-c", "a=b", "stash")

    def test_git_index_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            shutil.copytree(os.path.join(FIXTURES, "nestjs-orders-api"), repo)
            git(repo, "init", "-q", "-b", "main")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "init")
            with open(os.path.join(repo, "src", "main.ts"), "a") as fh:
                fh.write("\n// change\n")
            index = os.path.join(repo, ".git", "index")
            os.utime(os.path.join(repo, "src", "main.ts"))      # a stale stat that git status would normally refresh
            before = (open(index, "rb").read(), os.stat(index).st_mtime_ns)
            subprocess.run([sys.executable, os.path.join(SCRIPTS, "prepare-review.py"), repo, "--mode", "diff",
                            "--out", os.path.join(tmp, "out")], check=True, capture_output=True)
            files, _ = render.render(repo, {"findings": [], "totals": {"findings": 0, "by_severity": {s: 0 for s in _common.SEVERITIES},
                                     "by_category": {c: 0 for c in _common.CATEGORIES}, "by_status": {"Confirmed": 0, "Potential": 0}}},
                                     None, {}, out_dir=None)
            self.assertIn("with uncommitted changes", files["executive-summary.md"])   # git status ran
            self.assertEqual((open(index, "rb").read(), os.stat(index).st_mtime_ns), before)

    def test_cycles(self):
        g = graph.Graph(os.path.join(FIXTURES, "nestjs-orders-api")).build()
        cycles = g.cycles()
        self.assertIn(["src/orders/orders.service.ts", "src/users/users.service.ts"], cycles)

    def test_ts_alias_resolution(self):
        g = graph.Graph(os.path.join(FIXTURES, "nextjs-shop")).build()
        self.assertIn("lib/db.ts", g.edges.get("app/page.tsx", set()))

    def test_jsonc(self):
        self.assertEqual(json.loads(graph.strip_jsonc('{"a": "**/*.ts", // c\n "b": [1,], /* x */}')),
                         {"a": "**/*.ts", "b": [1]})


class TestRedaction(unittest.TestCase):
    def test_patterns(self):
        cases = {
            "password: 'hunter2hunter2'": "hunter2hunter2",
            "spring.datasource.password=B4nk-Pr0d!": "B4nk-Pr0d!",
            "AWS_KEY=AKIAABCDEFGHIJKLMNOP": "AKIAABCDEFGHIJKLMNOP",
            "url = 'postgres://admin:s3cretpw@db:5432/x'": "s3cretpw",
            "const token = 'ghp_abcdefghijklmnopqrstuvwxyz0123456789'": "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        }
        for line, secret in cases.items():
            self.assertNotIn(secret, _common.redact(line), line)

    def test_keeps_code(self):
        for line in ["const token = getToken(req);", "password: process.env.DB_PASSWORD,",
                     "if (!secret) throw new Error()"]:
            self.assertEqual(_common.redact(line), line)


class TestValidateAndRender(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        shutil.copytree(os.path.join(FIXTURES, "nestjs-orders-api"), self.repo, dirs_exist_ok=True)
        self.work = tempfile.mkdtemp()
        self.tmp_out = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.repo)
        shutil.rmtree(self.work)
        shutil.rmtree(self.tmp_out)

    def base(self, **kw):
        f = dict(severity="High", category="Security", title="SQL injection in user search",
                 description="d", file="src/users/users.service.ts", line=24,
                 evidence="return this.dataSource.query(`SELECT * FROM \"user\" WHERE name ILIKE '%${q}%'`);",
                 impact="i", recommendation="Use parameters.", confidence="High", status="Confirmed")
        f.update(kw)
        return f

    def run_validate(self, *agent_outputs, scope=None):
        paths = []
        for i, out in enumerate(agent_outputs):
            p = os.path.join(self.work, "raw%d.json" % i)
            with open(p, "w") as fh:
                json.dump(out, fh)
            paths.append(p)
        return validate.run(self.repo, paths, scope)

    def test_accept_relocate_reject(self):
        res = self.run_validate({"agent": "security-reviewer", "files_reviewed": ["a"], "findings": [
            self.base(),
            self.base(line=3),                                             # wrong line, evidence elsewhere
            self.base(title="Invented file", file="src/nope.ts"),          # file does not exist
            self.base(title="Line out of range", line=999),                # line does not exist
            self.base(title="Invented evidence", category="Performance", evidence="totallyMadeUp(123);", line=5),
            self.base(title="Missing field", impact=""),
        ]})
        v = res["validation"]
        self.assertEqual(v["rejected"], 4)
        self.assertEqual(v["line_corrections"], 1)
        # The relocated copy lands on the same line as the original and is merged as a duplicate.
        self.assertEqual(res["totals"]["findings"], 1)
        self.assertEqual(res["findings"][0]["id"], "SEC-001")
        self.assertEqual(res["findings"][0]["line"], 24)

    def test_dedupe_auto_and_candidates(self):
        res = self.run_validate(
            {"agent": "security-reviewer", "findings": [self.base(cwe="CWE-89")]},
            {"agent": "database-reviewer", "findings": [
                # Same CWE at the same place: strong duplicate, auto-merged.
                self.base(category="Database", severity="Medium", title="Raw SQL with interpolated search term",
                          cwe="CWE-89")]},
            {"agent": "performance-reviewer", "findings": [
                # Same place, different issue: kept separate, reported as a merge candidate.
                self.base(category="Performance", severity="Low", title="Leading-wildcard ILIKE cannot use an index",
                          recommendation="Add a trigram index")]},
            {"agent": "architecture-reviewer", "findings": [
                self.base(category="Code Quality", severity="Low", title="console.log used instead of Logger",
                          file="src/main.ts", line=8, evidence="console.log('Orders API listening');",
                          recommendation="Use the Nest Logger instead of console.log"),
                self.base(category="Code Quality", severity="Low", title="console.log used instead of Logger",
                          file="src/orders/orders.controller.ts", line=29, evidence="} catch (e) {}",
                          recommendation="Use the Nest Logger instead of console.log")]},
        )
        self.assertEqual(res["validation"]["duplicates_merged"], 2)
        sec = [f for f in res["findings"] if f["category"] == "Security"][0]
        self.assertEqual(sec["severity"], "High")
        self.assertEqual(sec["reported_by"], ["database-reviewer", "security-reviewer"])
        self.assertIn("Database", sec["also_categorised_as"])
        self.assertTrue(any(f["title"].startswith("Leading-wildcard") for f in res["findings"]))
        self.assertEqual(len(res["merge_candidates"]), 1)
        cq = [f for f in res["findings"] if f["category"] == "Code Quality"][0]
        self.assertEqual(len(cq["related_locations"]), 1)

    def test_orchestrator_merges(self):
        outputs = (
            {"agent": "security-reviewer", "findings": [self.base(severity="High")]},
            {"agent": "backend-reviewer", "findings": [self.base(category="API & Backend", severity="Critical",
                                                                 title="Search term interpolated into query")]})
        before = self.run_validate(*outputs)
        self.assertEqual(before["totals"]["findings"], 2)
        self.assertEqual(len(before["merge_candidates"]), 1)
        p = os.path.join(self.work, "raw0.json")  # reuse the files written by run_validate
        merges = [{"keep": {"agent": "security-reviewer", "title": "SQL injection in user search"},
                   "merge": {"agent": "backend-reviewer", "title": "Search term interpolated into query"},
                   "reason": "same root cause"},
                  {"keep": {"title": "does not exist"}, "merge": {"title": "nope"}}]
        after = validate.run(self.repo, [p, os.path.join(self.work, "raw1.json")], None, merges)
        self.assertEqual(after["totals"]["findings"], 1)
        f = after["findings"][0]
        self.assertEqual(f["category"], "Security")
        self.assertEqual(f["severity"], "Critical")       # higher severity adopted (Confirmed)
        self.assertEqual(len(after["validation"]["orchestrator_merges_unresolved"]), 1)
        self.assertEqual(after["merge_candidates"], [])

    def test_severity_rules_and_redaction(self):
        res = self.run_validate({"agent": "security-reviewer", "findings": [
            self.base(severity="Critical", status="Potential"),
            self.base(title="Hard-coded DB password", severity="critical", file="src/app.module.ts", line=14,
                      evidence="password: 'Pr0d-Orders-DB-2024!',", confidence="low", status="Confirmed",
                      description="Password Pr0d-Orders-DB-2024! is committed"),
        ]})
        f1, f2 = sorted(res["findings"], key=lambda f: f["line"])
        self.assertEqual(f2["severity"], "High")          # Critical capped: not Confirmed
        self.assertEqual(f1["severity"], "Medium")        # Low confidence capped
        self.assertEqual(f1["status"], "Potential")
        self.assertNotIn("Pr0d-Orders-DB-2024!", json.dumps(res))

    def test_absence_and_scope(self):
        scope = {"files": [{"file": "src/users/users.service.ts", "ranges": [[20, 26]]}]}
        res = self.run_validate({"agent": "testing-reviewer", "findings": [
            self.base(category="Testing", severity="High", title="OrdersService has no tests",
                      file="src/orders/orders.service.ts", line=17, evidence_type="absence",
                      evidence="No spec file imports OrdersService (searched **/*.spec.ts)"),
            self.base()]}, scope=scope)
        by_cat = {f["category"]: f for f in res["findings"]}
        self.assertTrue(by_cat["Security"]["in_changed_lines"])
        self.assertFalse(by_cat["Testing"]["in_changed_file"])

    def test_render_all_reports(self):
        res = self.run_validate({"agent": "security-reviewer", "files_reviewed": ["x"],
                                 "findings": [self.base(owasp="A03:2021", cwe="CWE-89")],
                                 "no_issue_areas": ["CORS reviewed"]})
        out = os.path.join(self.tmp_out, "report")
        summary = {"overall_summary": "S", "health_assessment": "H", "strategic_recommendations": [
            {"title": "Parameterize SQL", "detail": "d", "related": ["SEC-001"]}], "limitations": ["static only"]}
        files, hl = render.render(self.repo, res, detect.detect(self.repo), summary, out_dir=out, html=True)
        for name in ["executive-summary.md", "detailed-findings.md", "security-review.md", "architecture-review.md",
                     "recommendations.md", "dashboard.html", "explore.html"]:
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        self.assertIn("SEC-001", files["detailed-findings.md"])
        self.assertIn("| A03 | Injection | SEC-001 |", files["security-review.md"])
        base = os.path.relpath(self.repo, out).replace(os.sep, "/")
        self.assertIn("%s/src/users/users.service.ts#L24" % base, files["detailed-findings.md"])
        self.assertFalse(os.path.exists(os.path.join(self.repo, "docs")))
        self.assertEqual(hl["score"], 93)
        self.assertNotIn("{{", "".join(files.values()))
        self.assertNotIn("</script><", files["dashboard.html"].split('type="application/json">')[1].split("</script>")[0])
        dash = files["dashboard.html"]
        self.assertIn("cdnjs.cloudflare.com/ajax/libs/amcharts5/5.21.5/index.js", dash)
        self.assertIn('src="data:image/png;base64,', dash)
        payload = json.loads(dash.split('type="application/json">')[1].split("</script>")[0])
        self.assertEqual(payload["findings"][0]["id"], "SEC-001")
        self.assertIn("validation", payload)
        self.assertIn('href="explore.html"', dash)                       # dashboard -> Explore
        self.assertIn('"explore.html#" + encodeURIComponent(f.id)', dash)

    def test_standard_sections_references_and_git_history(self):
        git_info = {"status": "traced", "lines": "24", "same": False, "changes": 2,
                    "introduced": {"commit": "a" * 40, "short": "a" * 8, "author": "Ana Cruz", "committer": "Ana Cruz",
                                   "date": "2025-03-02", "summary": "Add search"},
                    "last_changed": {"commit": "b" * 40, "short": "b" * 8, "author": "Ben Reyes",
                                     "committer": "GitHub", "date": "2026-01-11", "summary": "Tweak search"}}
        res = self.run_validate({"agent": "security-reviewer", "files_reviewed": ["x"], "findings": [
            self.base(owasp="A03:2021", cwe="CWE-89"),
            self.base(category="Testing", severity="Low", title="No tests for search", status="Potential")]})
        self.assertFalse(res["git_attribution"]["available"])          # the fixture copy is not a Git repository
        self.assertNotIn("git", res["findings"][0])
        res["findings"][0]["git"] = git_info
        files, _ = render.render(self.repo, res, detect.detect(self.repo), {}, out_dir=None, html=True)
        md = files["detailed-findings.md"]
        sec_block, test_block = md.split("### SEC-001")[1].split("### TEST-001")
        order = ["| Title | SQL injection in user search |", "**Description**", "**Evidence**", "**Potential Impact**",
                 "**Recommended Solution**", "**Reference**", "**Git History**"]
        positions = [sec_block.index(label) for label in order]
        self.assertEqual(positions, sorted(positions))                 # the same sections, in the same order
        self.assertIn("[CWE-89](https://cwe.mitre.org/data/definitions/89.html)", sec_block)
        self.assertIn("[OWASP A03:2021 Injection](https://owasp.org/Top10/A03_2021-Injection/)", sec_block)
        self.assertIn("**Original introducer:** Ana Cruz · `aaaaaaaa` · 2025-03-02", sec_block)
        self.assertIn("**Latest contributor:** Ben Reyes (committed by GitHub) · `bbbbbbbb` · 2026-01-11", sec_block)
        self.assertIn("No CWE or OWASP reference applies", test_block)
        self.assertNotIn("Git History", test_block)
        self.assertIn("| SEC-001 | `src/users/users.service.ts:24` | Ana Cruz |", files["security-review.md"])
        self.assertIn("Git history is not available", files["security-review.md"])
        for page in ("dashboard.html", "explore.html"):
            data = json.loads(files[page].split('type="application/json">')[1].split("</script>")[0])
            self.assertEqual(data["sections"], {"title": "Title", "description": "Description",
                                                "evidence": "Evidence", "impact": "Potential Impact",
                                                "recommendation": "Recommended Solution", "reference": "Reference",
                                                "git": "Git History"})
            self.assertEqual(data["findings"][0]["git"], git_info)
            self.assertEqual(data["reference_urls"]["owasp"]["A03"]["url"], "https://owasp.org/Top10/A03_2021-Injection/")
            for label in ('"Potential Impact"', '"Recommended Solution"', '"Original introducer"',
                          '"Latest contributor"'):
                self.assertIn(label, files[page], (page, label))

    def test_explore_shows_only_review_findings(self):
        res = self.run_validate({"agent": "security-reviewer", "files_reviewed": ["x"], "findings": [
            self.base(owasp="A03:2021", cwe="CWE-89", title="Injection via {{q}} </script><b>x"),
            self.base(category="Testing", severity="Low", title="No tests for search", status="Potential")]})
        out = os.path.join(self.tmp_out, "report")
        files, _ = render.render(self.repo, res, detect.detect(self.repo), {}, out_dir=out, html=True)
        page = files["explore.html"]
        raw = page.split('type="application/json">')[1].split("</script>")[0]
        self.assertNotIn("</script><", raw)
        data = json.loads(raw)
        # The page's data is exactly the validated findings: same objects, same order, nothing added.
        self.assertEqual(data["findings"], res["findings"])
        self.assertEqual(data["totals"], res["totals"])
        self.assertEqual(data["link_base"], os.path.relpath(self.repo, out).replace(os.sep, "/"))
        self.assertEqual(data["source_root"], os.path.abspath(self.repo).replace(os.sep, "/"))
        self.assertIn("cdnjs.cloudflare.com/ajax/libs/gsap/3.13.0/gsap.min.js", page)
        self.assertIn("cdn.jsdelivr.net/npm/motion@12.23.24/dist/motion.js", page)
        self.assertIn('href="dashboard.html"', page)                     # Explore -> dashboard
        # The template itself carries no findings: every ID and path on the page comes from the data.
        with open(os.path.join(ROOT, "templates", "explore.html"), encoding="utf-8") as fh:
            template = fh.read()
        self.assertEqual(re.findall(r"\b(?:SEC|ARC|CQ|PERF|API|FE|DB|TEST|OPS)-\d{3}\b", template), [])
        self.assertEqual(page.count('type="application/json"'), 1)
        # Without --html there is no Explore page.
        files, _ = render.render(self.repo, res, detect.detect(self.repo), {}, out_dir=None, html=False)
        self.assertNotIn("explore.html", files)

    def test_chat_widget(self):
        res = self.run_validate({"agent": "security-reviewer", "files_reviewed": ["x"],
                                 "findings": [self.base(owasp="A03:2021", cwe="CWE-89",
                                                        title="Injection via {{q}} </script><b>x")]})
        widget = os.path.join(self.tmp_out, "report", ".work", "chat-widget.html")
        render.render(self.repo, res, detect.detect(self.repo), {}, out_dir=None, widget_path=widget)
        text = open(widget, encoding="utf-8").read()
        # Host widget rules: fragment only, no comments, scripts last, guarded sendPrompt, prefixed ids.
        for banned in ("<!doctype", "<html", "<head", "<body", "<!--", "/*"):
            self.assertNotIn(banned, text.lower())
        self.assertLess(text.index("<style>"), text.index('<div class="v917cr">'))
        self.assertLess(text.index('<div class="v917cr">'), text.index("<script"))
        self.assertIn('typeof sendPrompt === "function"', text)
        self.assertEqual(re.findall(r'id="(?!v917cr-)[^"]+"', text), [])
        data = json.loads(text.split("const DATA = ")[1].split(";\n")[0].replace("<\\/", "</"))
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["findings"][0][0], "SEC-001")
        self.assertIn("{{q}}", data["findings"][0][3])          # placeholder-like text survives fill()
        self.assertIn('id="v917cr-explore"', text)
        self.assertIn('id="v917cr-dash"', text)                 # the dashboard button stays
        self.assertFalse(data["explore"])                       # no --html: no explore.html to open
        render.render(self.repo, res, detect.detect(self.repo), {}, out_dir=None, html=True, widget_path=widget)
        text = open(widget, encoding="utf-8").read()
        self.assertTrue(json.loads(text.split("const DATA = ")[1].split(";\n")[0].replace("<\\/", "</"))["explore"])
        self.assertNotIn("</script><b>", text)                  # cannot break out of the script element

    def test_integrity(self):
        snap = integrity.snapshot(self.repo)
        self.assertTrue(integrity.verify(self.repo, snap)["unchanged"])
        os.makedirs(os.path.join(self.repo, "docs", "code-review"), exist_ok=True)   # nothing is excluded any more
        open(os.path.join(self.repo, "docs", "code-review", "x.md"), "w").write("ok")
        self.assertEqual(integrity.verify(self.repo, snap)["added"], ["docs/code-review/x.md"])
        os.remove(os.path.join(self.repo, "docs", "code-review", "x.md"))
        open(os.path.join(self.repo, "src", "main.ts"), "a").write("\n// edit\n")
        r = integrity.verify(self.repo, snap)
        self.assertFalse(r["unchanged"])
        self.assertEqual(r["modified"], ["src/main.ts"])



class TestGitHistory(unittest.TestCase):
    """git-history.py: who introduced and who last changed the code a security finding cites."""

    def commit(self, author, committer, date, message):
        env = dict(os.environ, GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL="a@example.com", GIT_AUTHOR_DATE=date,
                   GIT_COMMITTER_NAME=committer, GIT_COMMITTER_EMAIL="c@example.com", GIT_COMMITTER_DATE=date)
        subprocess.run(["git", "-C", self.repo, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-q", "-m", message], check=True, capture_output=True,
                       env=env)

    def write(self, rel, text):
        with open(os.path.join(self.repo, rel), "w") as fh:
            fh.write(text)

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="cr-git-")
        subprocess.run(["git", "-C", self.repo, "init", "-q"], check=True, capture_output=True)
        self.write("users.ts", "export function search(q) {\n  const safe = escape(q);\n"
                               "  return db.query(SQL, [safe]);\n}\nexport const a = 1;\n")
        self.commit("Ana Cruz", "Ana Cruz", "2025-03-02T10:00:00+08:00", "Add user search")
        self.write("users.ts", "export function search(q) {\n  const sql = 'SELECT * FROM users WHERE n = ' + q;\n"
                               "  return db.query(sql);\n}\nexport const a = 1;\n")
        self.commit("Ben Reyes", "GitHub", "2026-01-11T09:00:00+08:00", "Support partial matches")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def finding(self, **kw):
        f = dict(id="SEC-001", severity="High", category="Security", title="SQL injection", file="users.ts", line=2,
                 end_line=3, evidence="x", cwe="CWE-89", owasp="A03:2021")
        f.update(kw)
        return f

    def test_introducer_and_latest_contributor(self):
        f, same, quality = self.finding(), self.finding(line=5, end_line=5), self.finding(category="Code Quality",
                                                                                         cwe=None, owasp=None)
        summary = history.attribute(self.repo, [f, same, quality])
        self.assertEqual((summary["available"], summary["security_findings"], summary["traced"]), (True, 2, 2))
        g = f["git"]
        self.assertEqual((g["status"], g["lines"], g["same"], g["changes"]), ("traced", "2-3", False, 2))
        self.assertEqual((g["introduced"]["author"], g["introduced"]["date"]), ("Ana Cruz", "2025-03-02"))
        self.assertEqual(g["introduced"]["summary"], "Add user search")
        self.assertEqual((g["last_changed"]["author"], g["last_changed"]["committer"]), ("Ben Reyes", "GitHub"))
        self.assertEqual(g["last_changed"]["date"], "2026-01-11")
        self.assertRegex(g["last_changed"]["commit"], r"^[0-9a-f]{40}$")
        self.assertTrue(same["git"]["same"])                          # untouched since the first commit
        self.assertEqual(same["git"]["introduced"]["author"], "Ana Cruz")
        self.assertNotIn("git", quality)                              # only security findings are traced

    def test_nothing_is_guessed(self):
        self.write("new.ts", "const key = 1;\n")                      # untracked file
        self.write("users.ts", open(os.path.join(self.repo, "users.ts")).read().replace("export const a = 1;",
                                                                                         "export const a = 2;"))
        untracked, dirty, missing = self.finding(file="new.ts", line=1, end_line=1), \
            self.finding(line=5, end_line=5), self.finding(evidence_type="absence", line=1, end_line=1)
        summary = history.attribute(self.repo, [untracked, dirty, missing])
        self.assertEqual(untracked["git"]["status"], "untraced")
        self.assertEqual(dirty["git"]["status"], "uncommitted")
        self.assertNotIn("introduced", dirty["git"])
        self.assertEqual(missing["git"]["status"], "untraced")
        self.assertEqual((summary["traced"], summary["uncommitted"], summary["untraced"]), (0, 1, 2))
        plain = tempfile.mkdtemp(prefix="cr-nogit-")                  # not a repository at all
        try:
            f = self.finding()
            summary = history.attribute(plain, [f])
            self.assertFalse(summary["available"])
            self.assertIn("not a Git repository", summary["reason"])
            self.assertNotIn("git", f)
        finally:
            shutil.rmtree(plain)

    def test_only_read_only_git_runs(self):
        def snapshot():                                   # every file under .git: path, size, mtime
            out = {}
            for folder, _, names in os.walk(os.path.join(self.repo, ".git")):
                for name in names:
                    st = os.stat(os.path.join(folder, name))
                    out[os.path.join(folder, name)] = (st.st_size, st.st_mtime_ns)
            return out
        head = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        before = snapshot()
        f = self.finding()
        history.attribute(self.repo, [f])
        self.assertEqual(f["git"]["status"], "traced")
        self.assertEqual(before, snapshot())              # blame and log wrote nothing, not even the index
        self.assertEqual(head, subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], capture_output=True,
                                              text=True).stdout)
        with self.assertRaises(SystemExit):
            _common.git(self.repo, "commit", "-m", "x")


class TestViewer(unittest.TestCase):
    """serve-reports.py: the loopback viewer behind the widget's Explore and dashboard buttons."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cr-viewer-")
        self.repo = os.path.join(self.tmp, "repo")
        self.out = os.path.join(self.tmp, "out")
        os.makedirs(os.path.join(self.repo, "src"))
        os.makedirs(self.out)
        with open(os.path.join(self.repo, "src", "app.ts"), "w") as fh:
            fh.write("const a = 1;\nconst password = 'hunter2-super-secret-value';\nexport default a;\n")
        with open(os.path.join(self.tmp, "outside.txt"), "w") as fh:
            fh.write("outside the repository")
        for name in ("dashboard.html", "explore.html"):
            with open(os.path.join(self.out, name), "w") as fh:
                fh.write("<!doctype html><title>%s</title>" % name)
        with open(os.path.join(self.out, "notes.txt"), "w") as fh:
            fh.write("not a report")
        self.viewer = serve.start(self.repo, self.out, idle_minutes=1)
        if not self.viewer:
            self.skipTest("cannot start a loopback server in this environment")

    def tearDown(self):
        serve.stop(self.out)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, url):
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, ""

    def test_serves_reports_and_source_only(self):
        v = self.viewer
        self.assertRegex(v["explore"], r"^http://127\.0\.0\.1:\d+/[\w-]{10,}/explore\.html$")
        self.assertEqual(self.get(v["explore"])[0], 200)
        self.assertIn("dashboard.html", self.get(v["dashboard"])[1])
        code, page = self.get(v["url"] + "/_src/src/app.ts?line=2")
        self.assertEqual(code, 200)
        self.assertIn('<li id="L2" class="hit">', page)
        self.assertEqual(page.count("<li id="), 3)
        self.assertNotIn("hunter2-super-secret-value", page)        # redacted like the reports
        base = v["url"].rsplit("/", 1)[0]
        for url in (base + "/explore.html",                         # no token
                    base + "/wrong-token/explore.html",
                    v["url"] + "/notes.txt",                        # not a report type
                    v["url"] + "/.work/viewer.json",                # scratch and state stay private
                    v["url"] + "/_src/../outside.txt",              # never leaves the repository
                    v["url"] + "/_src/%2e%2e/outside.txt",
                    v["url"] + "/_src/missing.ts"):
            self.assertEqual(self.get(url)[0], 404, url)
        again = serve.start(self.repo, self.out)                    # a second render reuses the same URLs
        self.assertTrue(again["reused"])
        self.assertEqual(again["explore"], v["explore"])

    def test_refuses_a_report_folder_inside_the_repository(self):
        with self.assertRaises(SystemExit):
            serve.start(self.repo, os.path.join(self.repo, "docs"))

    def test_widget_buttons_link_straight_to_the_viewer(self):
        fdata = {"findings": [], "totals": {"findings": 0, "by_severity": {s: 0 for s in _common.SEVERITIES},
                                             "by_category": {}, "by_status": {"Confirmed": 0, "Potential": 0}}}
        widget = os.path.join(self.out, ".work", "chat-widget.html")
        render.render(self.repo, fdata, {}, {}, out_dir=None, html=True, widget_path=widget, viewer=self.viewer)
        text = open(widget, encoding="utf-8").read()
        data = json.loads(text.split("const DATA = ")[1].split(";\n")[0].replace("<\\/", "</"))
        self.assertEqual(data["urls"], {"explore": self.viewer["explore"], "dashboard": self.viewer["dashboard"]})
        self.assertIn('<a class="go main" id="v917cr-explore"', text)
        self.assertIn('<a class="go" id="v917cr-dash"', text)
        render.render(self.repo, fdata, {}, {}, out_dir=None, html=True, widget_path=widget)
        text = open(widget, encoding="utf-8").read()
        self.assertIsNone(json.loads(text.split("const DATA = ")[1].split(";\n")[0].replace("<\\/", "</"))["urls"])


class TestWelcomeHook(unittest.TestCase):
    def run_hook(self, folder):
        env = dict(os.environ, CODE_REVIEW_WELCOME_DIR=folder)
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "welcome.py")], input='{"source":"startup"}',
                              capture_output=True, text=True, env=env, check=True)

    def test_offers_once(self):
        folder = os.path.join(tempfile.mkdtemp(prefix="cr-welcome-"), "data")
        out = json.loads(self.run_hook(folder).stdout)
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "SessionStart")
        self.assertIn("AskUserQuestion", hso["additionalContext"])
        for cmd in ("scan", "review-diff", "review", "security", "architecture"):
            self.assertIn("917v-code-review:" + cmd, hso["additionalContext"])
        self.assertTrue(os.path.exists(os.path.join(folder, ".welcomed")))
        self.assertEqual(self.run_hook(folder).stdout, "")                # second start: silent

    def test_hook_registered(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            hooks = json.load(f)["hooks"]["SessionStart"]
        self.assertIn("scripts/welcome.py", hooks[0]["hooks"][0]["command"])


class TestFetchRepo(unittest.TestCase):
    """fetch-repo.py: review a public GitHub repository from a link. A local bare repository stands in for
    github.com, so the tests need no network."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cr-gh-")
        self.work = os.path.join(self.tmp, "work")
        self.remote = os.path.join(self.tmp, "remote")
        os.makedirs(os.path.join(self.work, "src"))
        os.makedirs(os.path.join(self.remote, "acme"))
        self.bare = os.path.join(self.remote, "acme", "widgets.git")
        self.base = "file://" + self.remote
        self.old_env = os.environ.get(fetch.REPOS_ENV)
        os.environ[fetch.REPOS_ENV] = os.path.join(self.tmp, "repos")
        subprocess.run(["git", "-C", self.work, "init", "-q", "-b", "main"], check=True, capture_output=True)
        self.write("src/app.js", "const sql = 'SELECT * FROM t WHERE id=' + req.query.id;\n")
        self.write("README.md", "# widgets\n")
        os.symlink("/etc/hosts", os.path.join(self.work, "outside"))
        self.commit("Ana Cruz", "first")
        git(self.work, "tag", "v1.0")
        git(self.work, "checkout", "-q", "-b", "feature/login")
        self.write("src/app.js", "const sql = 'SELECT * FROM t WHERE id=' + req.query.id;\neval(req.body.code);\n")
        self.commit("Ben Reyes", "add eval")
        git(self.work, "checkout", "-q", "main")
        self.write("README.md", "# widgets\nmore\n")
        self.commit("Ana Cruz", "docs")
        subprocess.run(["git", "clone", "-q", "--bare", self.work, self.bare], check=True, capture_output=True)
        git(self.bare, "update-ref", "refs/pull/7/head", "refs/heads/feature/login")

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop(fetch.REPOS_ENV, None)
        else:
            os.environ[fetch.REPOS_ENV] = self.old_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        with open(os.path.join(self.work, rel), "w") as fh:
            fh.write(text)

    def commit(self, author, message):
        env = dict(os.environ, GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL="a@example.com", GIT_COMMITTER_NAME=author,
                   GIT_COMMITTER_EMAIL="a@example.com")
        subprocess.run(["git", "-C", self.work, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.work, "commit", "-q", "-m", message], check=True, capture_output=True, env=env)

    def rev(self, repo, name):
        return subprocess.run(["git", "-C", repo, "rev-parse", name], check=True, capture_output=True,
                              text=True).stdout.strip()

    def get(self, link, **kw):
        return fetch.fetch(link, remote_base=self.base, **kw)

    def test_links(self):
        ok = {
            "https://github.com/acme/widgets": ("default", ""),
            "github.com/acme/widgets.git": ("default", ""),
            "git@github.com:acme/widgets.git": ("default", ""),
            "https://www.github.com/acme/widgets/issues/3?x=1#y": ("default", ""),
            "https://github.com/acme/widgets/tree/feature/login/src": ("tree", "feature/login/src"),
            "https://github.com/acme/widgets/blob/main/src/app.js": ("blob", "main/src/app.js"),
            "https://github.com/acme/widgets/commit/0123abc": ("commit", "0123abc"),
            "https://github.com/acme/widgets/releases/tag/v1.0": ("tag", "v1.0"),
            "https://github.com/acme/widgets/pull/7/files": ("pull", ""),
        }
        for link, (kind, rest) in ok.items():
            spec = fetch.parse_url(link)
            self.assertEqual((spec["owner"], spec["repo"], spec["kind"], spec["rest"]), ("acme", "widgets", kind, rest), link)
        self.assertEqual(fetch.parse_url("https://github.com/acme/widgets/pull/7")["number"], 7)
        for link in ("https://gitlab.com/acme/widgets", "https://gist.github.com/acme/abc", "https://github.com/acme",
                     "https://user:secret@github.com/acme/widgets", "ftp://github.com/acme/widgets",
                     "https://github.com/acme/widgets/tree/../../etc", "https://github.com/-bad/widgets",
                     "https://github.com/acme/wid gets", "https://github.com/acme/widgets/commit/not-a-hash",
                     "/some/local/path", ""):
            with self.assertRaises(fetch.FetchError, msg=link) as cm:
                fetch.parse_url(link)
            self.assertEqual(cm.exception.code, fetch.EXIT_BAD_LINK)
        out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "fetch-repo.py"), "https://gitlab.com/acme/widgets"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(json.loads(out.stdout)["reason"], "invalid_link")

    def test_download_reuse_and_update(self):
        r = self.get("https://github.com/acme/widgets")
        clone = os.path.join(self.tmp, "repos", "acme", "widgets")
        self.assertEqual((r["root"], r["clone"], r["reused"], r["history"]), (clone, clone, False, "full"))
        self.assertEqual(r["source"]["commit"], self.rev(self.bare, "refs/heads/main"))
        self.assertEqual((r["source"]["name"], r["source"]["ref"], r["source"]["ref_type"]), ("acme/widgets", "main", "branch"))
        self.assertTrue(os.path.isfile(os.path.join(clone, "src", "app.js")))
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, "repos", "acme"))), ["widgets"])   # no temp folder left
        self.assertTrue(self.get("https://github.com/acme/widgets")["reused"])
        self.write("README.md", "# widgets\nnewer\n")
        self.commit("Ana Cruz", "newer")
        git(self.work, "push", "-q", self.bare, "main")
        again = self.get("https://github.com/acme/widgets")
        self.assertFalse(again["reused"])
        self.assertEqual(again["source"]["commit"], self.rev(self.work, "main"))
        self.assertEqual(len(fetch.listing()), 1)
        self.assertTrue(fetch.remove(clone))
        self.assertFalse(os.path.exists(clone))
        with self.assertRaises(fetch.FetchError) as cm:
            self.get("https://github.com/acme/missing")
        self.assertEqual(cm.exception.code, fetch.EXIT_FETCH_FAILED)

    def test_refs_folders_tags_and_pull_requests(self):
        r = self.get("github.com/acme/widgets/tree/feature/login/src")          # a branch name with a slash, then a folder
        self.assertEqual((r["source"]["ref"], r["source"]["subdir"]), ("feature/login", "src"))
        self.assertTrue(r["root"].endswith(os.path.join("widgets", "src")))
        self.assertEqual(_common.review_source(r["root"])["blob_base"],
                         "https://github.com/acme/widgets/blob/%s/src" % r["source"]["commit"])
        r = self.get("https://github.com/acme/widgets/blob/main/src/app.js")
        self.assertEqual((r["source"]["ref"], r["focus"], r["root"]), ("main", "src/app.js", r["clone"]))
        r = self.get("https://github.com/acme/widgets/releases/tag/v1.0", depth=1)
        self.assertEqual((r["source"]["ref_type"], r["history"], r["depth"]), ("tag", "shallow", 1))
        self.assertEqual(r["source"]["commit"], self.rev(self.work, "v1.0^{commit}"))
        self.assertTrue(history.attribute(r["root"], [])["shallow"])
        r = self.get("https://github.com/acme/widgets", ref="feature/login")
        self.assertEqual(r["source"]["commit"], self.rev(self.work, "feature/login"))
        r = self.get("https://github.com/acme/widgets/commit/" + self.rev(self.work, "v1.0^{commit}")[:10])
        self.assertEqual((r["source"]["ref_type"], r["source"]["commit"]), ("commit", self.rev(self.work, "v1.0^{commit}")))
        with self.assertRaises(fetch.FetchError) as cm:
            self.get("https://github.com/acme/widgets/tree/no-such-branch")
        self.assertEqual(cm.exception.reason, "ref_not_found")
        # A pull request: its head is checked out, and "diff" is what it changes against its base.
        r = self.get("https://github.com/acme/widgets/pull/7")
        self.assertEqual((r["source"]["pull"], r["source"]["commit"]), (7, self.rev(self.work, "feature/login")))
        self.assertEqual(r["diff"], {"range": self.rev(self.work, "v1.0^{commit}") + "..HEAD", "base": "main", "pull": 7})
        scope = diffscope.compute(r["root"], "range", rng=r["diff"]["range"])
        self.assertEqual([(f["file"], f["ranges"]) for f in scope["files"]], [("src/app.js", [[2, 2]])])

    def test_downloaded_code_is_contained(self):
        r = self.get("https://github.com/acme/widgets")
        clone = r["clone"]
        link = os.path.join(clone, "outside")                 # a symlink in the repository pointing outside it
        self.assertFalse(os.path.islink(link))
        with open(link) as fh:
            self.assertEqual(fh.read(), "/etc/hosts")
        cfg = lambda key: subprocess.run(["git", "-C", clone, "config", "--get", key], capture_output=True,
                                         text=True).stdout.strip()
        self.assertEqual(cfg("core.symlinks"), "false")
        self.assertEqual(cfg("core.hooksPath"), os.devnull)
        self.assertTrue(cfg("remote.origin.pushurl").startswith("no-push://"))
        self.assertFalse(os.path.isdir(os.path.join(clone, ".git", "hooks")))
        self.assertEqual(subprocess.run(["git", "-C", clone, "status", "--porcelain"], capture_output=True,
                                        text=True).stdout, "")
        env = fetch._env("https")
        self.assertEqual((env["GIT_TERMINAL_PROMPT"], env["GIT_ALLOW_PROTOCOL"], env["GIT_LFS_SKIP_SMUDGE"]), ("0", "https", "1"))
        self.assertNotIn("GIT_ASKPASS", env)
        self.assertIn("credential.helper=", fetch.SAFE)
        # A folder this script did not create is never replaced or deleted.
        mine = fetch.clone_path("acme", "other")
        os.makedirs(mine)
        with open(os.path.join(mine, "keep.txt"), "w") as fh:
            fh.write("mine")
        subprocess.run(["git", "clone", "-q", "--bare", self.work, os.path.join(self.remote, "acme", "other.git")],
                       check=True, capture_output=True)
        for call in (lambda: self.get("https://github.com/acme/other"), lambda: fetch.remove(mine)):
            with self.assertRaises(fetch.FetchError) as cm:
                call()
            self.assertEqual(cm.exception.reason, "not_ours")
        self.assertTrue(os.path.isfile(os.path.join(mine, "keep.txt")))

    def test_reports_link_to_github(self):
        r = self.get("https://github.com/acme/widgets/tree/feature/login")
        sha = r["source"]["commit"]
        raw = os.path.join(self.tmp, "raw.json")
        with open(raw, "w") as fh:
            json.dump({"agent": "security-reviewer", "files_reviewed": ["src/app.js"], "findings": [dict(
                severity="High", category="Security", title="SQL injection in the query", description="d",
                file="src/app.js", line=1, evidence="const sql = 'SELECT * FROM t WHERE id=' + req.query.id;",
                impact="i", recommendation="Use parameters.", confidence="High", status="Confirmed", cwe="CWE-89",
                owasp="A03:2021")]}, fh)
        fdata = validate.run(r["root"], [raw])
        self.assertEqual((fdata["source"]["name"], fdata["source"]["commit"]), ("acme/widgets", sha))
        g = fdata["findings"][0]["git"]
        self.assertEqual((g["status"], g["introduced"]["author"]), ("traced", "Ana Cruz"))
        out = os.path.join(self.tmp, "out")
        files, _ = render.render(r["root"], fdata, None, {}, out_dir=out, html=True)
        blob = "https://github.com/acme/widgets/blob/%s/src/app.js#L1" % sha
        self.assertIn("[`src/app.js:1`](%s)" % blob, files["detailed-findings.md"])
        self.assertIn("(https://github.com/acme/widgets/commit/%s)" % g["introduced"]["commit"], files["security-review.md"])
        self.assertIn("fetched from GitHub: [acme/widgets](https://github.com/acme/widgets), branch `feature/login`",
                      files["executive-summary.md"])
        self.assertIn("**Repository:** acme/widgets", files["detailed-findings.md"])
        for page in ("dashboard.html", "explore.html"):
            data = json.loads(re.search(r'<script id="review-data" type="application/json">(.*?)</script>',
                                        files[page], re.S).group(1))
            self.assertEqual(data["source"]["blob_base"], "https://github.com/acme/widgets/blob/" + sha)
            self.assertIn("ghFile(", files[page])
        # A local repository has no source, so its reports keep their local links.
        self.assertIsNone(_common.review_source(self.work))
        # Reviewing one folder of the repository still traces history (paths are relative to that folder).
        sub = self.get("https://github.com/acme/widgets/tree/feature/login/src")
        f = dict(id="SEC-001", category="Security", file="app.js", line=2, evidence="x")
        self.assertEqual(history.attribute(sub["root"], [f])["traced"], 1)
        self.assertEqual(f["git"]["introduced"]["author"], "Ben Reyes")


if __name__ == "__main__":
    unittest.main()
