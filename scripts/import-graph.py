#!/usr/bin/env python3
"""Build a file-level import graph and report circular dependencies (read-only).

Resolves imports that point at files inside the repository for
JavaScript/TypeScript (relative imports + tsconfig "@/" style aliases),
Python (relative and package-absolute), Java/Kotlin (package imports) and
Go (module-local packages). Third-party imports are ignored.

Usage: import-graph.py <repo-root> [-o graph.json]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import dump_json, iter_repo_files, read_text  # noqa: E402

JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte")
JS_IMPORT = re.compile(
    r"""(?:import\s+(?!type\b)(?:[\w*{}\s,]+\s+from\s+)?|export\s+(?!type\b)[\w*{}\s,]*\s+from\s+|"""
    r"""require\(\s*|import\(\s*)['"]([^'"]+)['"]""")
PY_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import\s+([\w*, ()]+)|import\s+([\w., ]+))", re.M)
JVM_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)", re.M)
GO_IMPORT_BLOCK = re.compile(r"import\s*\(([\s\S]*?)\)|import\s+(?:\w+\s+)?\"([^\"]+)\"")


def strip_jsonc(text):
    """Remove // and /* */ comments outside strings, and trailing commas (tsconfig is JSONC)."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


class Graph:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.files = [f for f in iter_repo_files(self.root)]
        self.fileset = set(self.files)
        self.edges = {}
        self.aliases = self._ts_aliases()

    def _ts_aliases(self):
        """Read compilerOptions.paths from tsconfig/jsconfig files (best effort, comments stripped)."""
        aliases = []
        for rel in self.files:
            if os.path.basename(rel) not in ("tsconfig.json", "jsconfig.json"):
                continue
            text = strip_jsonc(read_text(self.root, rel) or "")
            try:
                opts = json.loads(text).get("compilerOptions", {})
            except ValueError:
                continue
            base = os.path.normpath(os.path.join(os.path.dirname(rel), opts.get("baseUrl", ".")))
            for key, targets in (opts.get("paths") or {}).items():
                if not targets:
                    continue
                prefix = key.rstrip("*")
                target = os.path.normpath(os.path.join(base, targets[0].rstrip("*"))).replace(os.sep, "/")
                aliases.append((prefix, "" if target == "." else target + ("/" if key.endswith("*") else "")))
        return aliases

    def _add(self, src, dst):
        if dst and dst != src:
            self.edges.setdefault(src, set()).add(dst)

    def _resolve_js(self, src, spec):
        if spec.startswith("."):
            base = os.path.normpath(os.path.join(os.path.dirname(src), spec)).replace(os.sep, "/")
        else:
            base = None
            for prefix, target in self.aliases:
                if prefix and spec.startswith(prefix):
                    base = os.path.normpath(target + spec[len(prefix):]).replace(os.sep, "/")
                    break
            if base is None:
                return None
        stem = re.sub(r"\.(js|jsx|mjs|cjs)$", "", base)
        for cand in [base, stem] + [stem + e for e in JS_EXT] + [stem + "/index" + e for e in JS_EXT]:
            if cand in self.fileset and cand.endswith(JS_EXT):
                return cand
        return None

    def build(self):
        py_modules = {}
        jvm_packages = {}
        go_module = None
        for rel in self.files:
            if rel.endswith(".py"):
                mod = rel[:-3].replace("/", ".")
                if mod.endswith(".__init__"):
                    mod = mod[: -len(".__init__")]
                py_modules[mod] = rel
                # Also index under src-layout roots (src/pkg/x.py -> pkg.x).
                for root_dir in ("src.", "app.", "lib."):
                    if mod.startswith(root_dir):
                        py_modules.setdefault(mod[len(root_dir):], rel)
            elif rel.endswith((".java", ".kt")):
                m = JVM_PACKAGE.search(read_text(self.root, rel) or "")
                if m:
                    jvm_packages.setdefault(m.group(1), []).append(rel)
            elif os.path.basename(rel) == "go.mod" and go_module is None:
                m = re.search(r"^module\s+(\S+)", read_text(self.root, rel) or "", re.M)
                if m:
                    go_module = (m.group(1), os.path.dirname(rel))
        for rel in self.files:
            text = None
            if rel.endswith(JS_EXT):
                text = read_text(self.root, rel) or ""
                for m in JS_IMPORT.finditer(text):
                    self._add(rel, self._resolve_js(rel, m.group(1)))
            elif rel.endswith(".py"):
                text = read_text(self.root, rel) or ""
                pkg = rel[:-3].replace("/", ".").rsplit(".", 1)[0] if "/" in rel else ""
                for m in PY_IMPORT.finditer(text):
                    if m.group(1) is not None:
                        mod = m.group(1)
                        if mod.startswith("."):
                            dots = len(mod) - len(mod.lstrip("."))
                            parts = pkg.split(".") if pkg else []
                            parts = parts[: len(parts) - (dots - 1)] if dots > 1 else parts
                            mod = ".".join(p for p in parts + [mod.lstrip(".")] if p)
                        names = [n.strip(" ()") for n in m.group(2).split(",")]
                        hit = False
                        for n in names:
                            if mod + "." + n in py_modules:
                                self._add(rel, py_modules[mod + "." + n])
                                hit = True
                        if not hit and mod in py_modules:
                            self._add(rel, py_modules[mod])
                    else:
                        for mod in (x.strip().split(" ")[0] for x in m.group(3).split(",")):
                            if mod in py_modules:
                                self._add(rel, py_modules[mod])
            elif rel.endswith((".java", ".kt")):
                text = read_text(self.root, rel) or ""
                for m in re.finditer(r"^\s*import\s+(?:static\s+)?([\w.]+)", text, re.M):
                    full = m.group(1)
                    parts = full.split(".")
                    # Find the longest package prefix, then the class file inside it.
                    for i in range(len(parts) - 1, 0, -1):
                        pkg, cls = ".".join(parts[:i]), parts[i]
                        if pkg in jvm_packages:
                            for f in jvm_packages[pkg]:
                                if os.path.splitext(os.path.basename(f))[0] == cls:
                                    self._add(rel, f)
                            break
            elif rel.endswith(".go") and go_module:
                text = read_text(self.root, rel) or ""
                mod, mod_dir = go_module
                specs = []
                for m in GO_IMPORT_BLOCK.finditer(text):
                    if m.group(1):
                        specs += re.findall(r"\"([^\"]+)\"", m.group(1))
                    elif m.group(2):
                        specs.append(m.group(2))
                for spec in specs:
                    if spec.startswith(mod + "/"):
                        pdir = os.path.normpath(os.path.join(mod_dir, spec[len(mod) + 1:])).replace(os.sep, "/")
                        for f in self.files:
                            if os.path.dirname(f) == pdir and f.endswith(".go") and not f.endswith("_test.go"):
                                self._add(rel, f)
        return self

    def cycles(self):
        """Tarjan's strongly connected components; each SCC of size > 1 is a cycle group."""
        index, low, on_stack, stack, out = {}, {}, set(), [], []
        counter = [0]
        nodes = sorted(set(self.edges) | {d for ds in self.edges.values() for d in ds})
        sys.setrecursionlimit(max(10000, len(nodes) * 4))

        def strong(v):
            index[v] = low[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on_stack.add(v)
            for w in sorted(self.edges.get(v, ())):
                if w not in index:
                    strong(w)
                    low[v] = min(low[v], low[w])
                elif w in on_stack:
                    low[v] = min(low[v], index[w])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp))

        for n in nodes:
            if n not in index:
                strong(n)
        return sorted(out, key=lambda c: (-len(c), c))

    def example_cycle(self, comp):
        """Return one concrete path a -> ... -> a inside a component, for evidence."""
        comp_set = set(comp)
        start = comp[0]
        prev = {start: None}
        queue = [start]
        while queue:
            v = queue.pop(0)
            for w in sorted(self.edges.get(v, ())):
                if w not in comp_set:
                    continue
                if w == start:
                    path = [v]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    return list(reversed(path)) + [start]
                if w not in prev:
                    prev[w] = v
                    queue.append(w)
        return comp + [start]


def analyze(root):
    """Import-graph summary: edges, cycles, fan-in and fan-out leaders."""
    g = Graph(root).build()
    cycles = g.cycles()
    fan_in = {}
    for src, dsts in g.edges.items():
        for d in dsts:
            fan_in[d] = fan_in.get(d, 0) + 1
    return {
        "files_with_imports": len(g.edges),
        "internal_edges": sum(len(v) for v in g.edges.values()),
        "cycles": [{"files": c, "example_path": g.example_cycle(c)} for c in cycles],
        "most_depended_on": [{"file": f, "imported_by": n}
                             for f, n in sorted(fan_in.items(), key=lambda kv: (-kv[1], kv[0]))[:15]],
        "highest_fan_out": [{"file": f, "imports": len(d)}
                            for f, d in sorted(g.edges.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:15]],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("-o", "--output", default="-")
    a = ap.parse_args()
    dump_json(analyze(a.root), a.output)


if __name__ == "__main__":
    main()
