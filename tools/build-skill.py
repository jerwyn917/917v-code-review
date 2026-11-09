#!/usr/bin/env python3
"""Package this plugin as a standalone Agent Skill (Claude Code, claude.ai, API).

The plugin stays the source of truth. This script assembles:

  dist/917v-code-review/
    SKILL.md                 from skill-src/SKILL.md (standalone orchestrator)
    VERSION                  from .claude-plugin/plugin.json
    scripts/*.py             deterministic helpers (unchanged)
    templates/*              report templates, dashboard, chat widget, logo asset (unchanged)
    references/*.md          schema, rubric, ownership, checklists, protocol
    references/reviewers/    the eight specialist agents, rewritten as briefs
  dist/917v-code-review.zip  the same folder, zipped for upload to claude.ai

Usage: python3 tools/build-skill.py [-o dist]
Install for Claude Code: copy dist/917v-code-review to ~/.claude/skills/ (personal)
or to <project>/.claude/skills/ (one project).
"""

import argparse
import json
import os
import re
import shutil
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "917v-code-review"
PLUGIN_REF = "`${CLAUDE_PLUGIN_ROOT}/skills/comprehensive-review/references/reviewer-protocol.md`"
SKILL_REF = "`../reviewer-protocol.md` (the `references/` folder of this skill, one level above this file)"
PLUGIN_PATH_NOTE = "If the orchestrator gave a different PLUGIN REFERENCES path, use that path."
SKILL_PATH_NOTE = "If the orchestrator gave a SKILL REFERENCES path, use that path."


def frontmatter_split(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("missing frontmatter")
    return m.group(1), text[m.end():]


def reviewer_brief(path):
    """Turn a plugin agent file into a reviewer brief the orchestrator hands to a subagent."""
    with open(path, encoding="utf-8") as f:
        meta, body = frontmatter_split(f.read())
    name = re.search(r"^name:\s*(.+)$", meta, re.M).group(1).strip()
    desc = re.search(r"^description:\s*(.+)$", meta, re.M).group(1).strip()
    if PLUGIN_REF not in body:
        raise ValueError(f"{path}: expected reference to the plugin's reviewer protocol")
    body = body.replace(PLUGIN_REF, SKILL_REF).replace(PLUGIN_PATH_NOTE, SKILL_PATH_NOTE)
    if "CLAUDE_PLUGIN_ROOT" in body:
        raise ValueError(f"{path}: unresolved CLAUDE_PLUGIN_ROOT reference")
    return name, f"# Reviewer brief: {name}\n\n> {desc}\n>\n> Tools: read and search only.\n{body}"


def validate_skill_md(path):
    with open(path, encoding="utf-8") as f:
        meta, body = frontmatter_split(f.read())
    name = re.search(r"^name:\s*(.+)$", meta, re.M).group(1).strip()
    desc = re.search(r"^description:\s*(.+)$", meta, re.M).group(1).strip()
    if name != NAME or not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        raise ValueError(f"bad skill name: {name!r}")
    if not desc or len(desc) > 1024:
        raise ValueError(f"description must be 1-1024 characters (is {len(desc)})")
    if "<" in desc or ">" in desc:
        raise ValueError("description must not contain angle brackets")
    if "CLAUDE_PLUGIN_ROOT" in body:
        raise ValueError("SKILL.md must not reference CLAUDE_PLUGIN_ROOT")


def copy_files(src_dir, dst_dir, pattern):
    os.makedirs(dst_dir, exist_ok=True)
    for fn in sorted(os.listdir(src_dir)):
        if re.fullmatch(pattern, fn):
            shutil.copy2(os.path.join(src_dir, fn), os.path.join(dst_dir, fn))


def build(out_root):
    with open(os.path.join(REPO, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        version = json.load(f)["version"]

    dst = os.path.join(out_root, NAME)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)

    validate_skill_md(os.path.join(REPO, "skill-src", "SKILL.md"))
    shutil.copy2(os.path.join(REPO, "skill-src", "SKILL.md"), os.path.join(dst, "SKILL.md"))
    with open(os.path.join(dst, "VERSION"), "w", encoding="utf-8") as f:
        f.write(version + "\n")

    copy_files(os.path.join(REPO, "scripts"), os.path.join(dst, "scripts"), r"(?!welcome\.py$)[\w-]+\.py")   # welcome.py is the plugin's install hook
    copy_files(os.path.join(REPO, "templates"), os.path.join(dst, "templates"), r"[\w-]+\.(md|html)")
    copy_files(os.path.join(REPO, "templates", "assets"), os.path.join(dst, "templates", "assets"), r"[\w-]+\.datauri")
    copy_files(os.path.join(REPO, "skills", "comprehensive-review", "references"),
               os.path.join(dst, "references"), r"[\w-]+\.md")

    rev_dir = os.path.join(dst, "references", "reviewers")
    os.makedirs(rev_dir)
    agents_dir = os.path.join(REPO, "agents")
    names = []
    for fn in sorted(os.listdir(agents_dir)):
        if fn.endswith(".md"):
            name, text = reviewer_brief(os.path.join(agents_dir, fn))
            with open(os.path.join(rev_dir, name + ".md"), "w", encoding="utf-8") as f:
                f.write(text)
            names.append(name)

    zip_path = os.path.join(out_root, NAME + ".zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(dst):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for fn in sorted(filenames):
                if fn == ".DS_Store" or fn.endswith(".pyc"):
                    continue
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, out_root))
    return dst, zip_path, version, names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=os.path.join(REPO, "dist"), help="output directory (default: dist/)")
    args = ap.parse_args()
    try:
        dst, zip_path, version, names = build(os.path.abspath(args.out))
    except (ValueError, OSError, KeyError) as e:
        print(f"build-skill: {e}", file=sys.stderr)
        return 1
    print(f"Built {NAME} v{version}")
    print(f"  folder: {dst}")
    print(f"  zip:    {zip_path}")
    print(f"  reviewers: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
