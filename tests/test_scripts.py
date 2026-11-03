#!/usr/bin/env python3
"""Unit tests for the deterministic scripts. Standard library only.

Run: python3 -m unittest discover -s tests -v   (from the plugin root)
"""

import importlib.util
import json
import os
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

    def tearDown(self):
        shutil.rmtree(self.repo)
        shutil.rmtree(self.work)

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
        out = os.path.join(self.repo, "docs", "code-review")
        summary = {"overall_summary": "S", "health_assessment": "H", "strategic_recommendations": [
            {"title": "Parameterize SQL", "detail": "d", "related": ["SEC-001"]}], "limitations": ["static only"]}
        files, hl = render.render(self.repo, res, detect.detect(self.repo), summary, out_dir=out, html=True)
        for name in ["executive-summary.md", "detailed-findings.md", "security-review.md", "architecture-review.md",
                     "recommendations.md", "dashboard.html"]:
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        self.assertIn("SEC-001", files["detailed-findings.md"])
        self.assertIn("| A03 | Injection | SEC-001 |", files["security-review.md"])
        self.assertIn("../../src/users/users.service.ts#L24", files["detailed-findings.md"])
        self.assertEqual(hl["score"], 93)
        self.assertNotIn("{{", "".join(files.values()))
        self.assertNotIn("</script><", files["dashboard.html"].split('type="application/json">')[1].split("</script>")[0])

    def test_integrity(self):
        snap = integrity.snapshot(self.repo)
        os.makedirs(os.path.join(self.repo, "docs", "code-review"), exist_ok=True)
        open(os.path.join(self.repo, "docs", "code-review", "x.md"), "w").write("ok")
        self.assertTrue(integrity.verify(self.repo, snap)["unchanged"])
        open(os.path.join(self.repo, "src", "main.ts"), "a").write("\n// edit\n")
        r = integrity.verify(self.repo, snap)
        self.assertFalse(r["unchanged"])
        self.assertEqual(r["modified"], ["src/main.ts"])


if __name__ == "__main__":
    unittest.main()
