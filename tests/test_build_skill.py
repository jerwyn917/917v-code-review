"""Tests for tools/build-skill.py (standalone skill packaging)."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("build_skill", os.path.join(REPO, "tools", "build-skill.py"))
build_skill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_skill)


class BuildSkillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dst, cls.zip_path, cls.version, cls.names = build_skill.build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_layout(self):
        for rel in ["SKILL.md", "VERSION", "scripts/render-reports.py", "scripts/_common.py",
                    "templates/dashboard.html", "templates/chat-widget.html", "templates/assets/917v-logo.datauri",
                    "references/finding-schema.md",
                    "references/reviewer-protocol.md", "references/reviewers/security-reviewer.md"]:
            self.assertTrue(os.path.isfile(os.path.join(self.dst, rel)), rel)
        self.assertEqual(len(self.names), 8)

    def test_no_plugin_paths_left(self):
        for dirpath, _, files in os.walk(self.dst):
            for fn in files:
                if fn.endswith(".md"):
                    with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                        self.assertNotIn("CLAUDE_PLUGIN_ROOT", f.read(), fn)

    def test_zip_has_single_top_folder(self):
        with zipfile.ZipFile(self.zip_path) as z:
            tops = {n.split("/")[0] for n in z.namelist()}
        self.assertEqual(tops, {"917v-code-review"})

    def test_render_reads_version_file(self):
        out = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util,sys;"
             "s=importlib.util.spec_from_file_location('r',sys.argv[1]);m=importlib.util.module_from_spec(s);"
             "s.loader.exec_module(m);print(m.plugin_version())",
             os.path.join(self.dst, "scripts", "render-reports.py")],
            capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), self.version)


if __name__ == "__main__":
    unittest.main()
