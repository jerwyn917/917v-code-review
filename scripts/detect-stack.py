#!/usr/bin/env python3
"""Detect the technology stack of a repository (read-only).

Frameworks are reported only when a manifest declares them; each one is
then marked "confirmed" if real source files use it, or "manifest-only"
if no usage was found. Folder names alone never count as evidence.

Usage: detect-stack.py <repo-root> [-o stack.json]
"""

import argparse
import datetime
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import dump_json, iter_repo_files, read_text  # noqa: E402

LANG_BY_EXT = {
    ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".vue": "Vue SFC", ".svelte": "Svelte",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".groovy": "Groovy",
    ".py": "Python", ".php": "PHP", ".go": "Go", ".rb": "Ruby", ".rs": "Rust",
    ".cs": "C#", ".fs": "F#", ".swift": "Swift", ".m": "Objective-C", ".dart": "Dart",
    ".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang", ".clj": "Clojure",
    ".sql": "SQL", ".tf": "Terraform (HCL)", ".hcl": "HCL", ".sh": "Shell", ".bash": "Shell",
    ".ps1": "PowerShell", ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "Sass",
    ".less": "Less", ".graphql": "GraphQL", ".gql": "GraphQL", ".proto": "Protocol Buffers",
}

JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte")

# Each rule: ecosystem, the dependency names that declare it (exact or
# fnmatch pattern), the source-usage regex that confirms it, and its role.
RULES = [
    # --- JavaScript / TypeScript -------------------------------------------------
    dict(name="NestJS", eco="npm", deps=["@nestjs/core"], kind="backend",
         src=r"@Module\s*\(|NestFactory\.create", exts=JS_EXT),
    dict(name="Next.js", eco="npm", deps=["next"], kind="fullstack",
         src=r"""from\s+['"]next(/[\w/-]+)?['"]|require\(['"]next""", exts=JS_EXT,
         markers=["next.config.js", "next.config.mjs", "next.config.ts", "next.config.cjs"]),
    dict(name="Nuxt", eco="npm", deps=["nuxt", "nuxt3"], kind="fullstack",
         src=r"defineNuxtConfig|useAsyncData|useFetch\(", exts=JS_EXT,
         markers=["nuxt.config.ts", "nuxt.config.js"]),
    dict(name="React", eco="npm", deps=["react"], kind="frontend",
         src=r"""from\s+['"]react['"]|require\(['"]react['"]\)|<[A-Z]\w*[\s/>]""",
         exts=(".tsx", ".jsx", ".js", ".ts")),
    dict(name="React Native", eco="npm", deps=["react-native"], kind="mobile",
         src=r"""from\s+['"]react-native['"]""", exts=JS_EXT),
    dict(name="Vue", eco="npm", deps=["vue"], kind="frontend",
         src=r"<template[\s>]|createApp\(|defineComponent\(", exts=(".vue", ".ts", ".js")),
    dict(name="Angular", eco="npm", deps=["@angular/core"], kind="frontend",
         src=r"@Component\s*\(|@NgModule\s*\(", exts=(".ts",)),
    dict(name="Svelte", eco="npm", deps=["svelte"], kind="frontend",
         src=r"<script[\s>]", exts=(".svelte",)),
    dict(name="SvelteKit", eco="npm", deps=["@sveltejs/kit"], kind="fullstack",
         src=r"""from\s+['"]@sveltejs/kit""", exts=JS_EXT),
    dict(name="Express", eco="npm", deps=["express"], kind="backend",
         src=r"""express\(\)|from\s+['"]express['"]|require\(['"]express['"]\)""", exts=JS_EXT),
    dict(name="Fastify", eco="npm", deps=["fastify"], kind="backend",
         src=r"""fastify\(|from\s+['"]fastify['"]""", exts=JS_EXT),
    dict(name="Koa", eco="npm", deps=["koa"], kind="backend",
         src=r"new\s+Koa\(", exts=JS_EXT),
    dict(name="Hapi", eco="npm", deps=["@hapi/hapi"], kind="backend",
         src=r"Hapi\.server\(", exts=JS_EXT),
    dict(name="tRPC", eco="npm", deps=["@trpc/server"], kind="backend",
         src=r"initTRPC|createTRPCRouter", exts=JS_EXT),
    dict(name="GraphQL (Apollo)", eco="npm", deps=["@apollo/server", "apollo-server*"], kind="backend",
         src=r"ApolloServer|gql`", exts=JS_EXT),
    # --- Java / JVM --------------------------------------------------------------
    dict(name="Spring Boot", eco="jvm", deps=["*spring-boot*"], kind="backend",
         src=r"@SpringBootApplication", exts=(".java", ".kt")),
    dict(name="Spring Web MVC", eco="jvm", deps=["spring-boot-starter-web", "spring-webmvc"], kind="backend",
         src=r"@(Rest)?Controller\b|@RequestMapping|@GetMapping|@PostMapping", exts=(".java", ".kt")),
    dict(name="Spring WebFlux", eco="jvm", deps=["spring-boot-starter-webflux", "spring-webflux"], kind="backend",
         src=r"\bMono<|\bFlux<", exts=(".java", ".kt")),
    dict(name="Spring Security", eco="jvm", deps=["spring-boot-starter-security", "spring-security-*"],
         kind="backend", src=r"SecurityFilterChain|@EnableWebSecurity|WebSecurityConfigurerAdapter",
         exts=(".java", ".kt")),
    dict(name="Quarkus", eco="jvm", deps=["quarkus-*"], kind="backend",
         src=r"io\.quarkus", exts=(".java", ".kt")),
    dict(name="Micronaut", eco="jvm", deps=["micronaut-*"], kind="backend",
         src=r"io\.micronaut", exts=(".java", ".kt")),
    # --- Python ------------------------------------------------------------------
    dict(name="Django", eco="python", deps=["django"], kind="backend",
         src=r"INSTALLED_APPS|from\s+django|import\s+django", exts=(".py",), markers=["manage.py"]),
    dict(name="Django REST Framework", eco="python", deps=["djangorestframework"], kind="backend",
         src=r"from\s+rest_framework", exts=(".py",)),
    dict(name="FastAPI", eco="python", deps=["fastapi"], kind="backend",
         src=r"FastAPI\s*\(|APIRouter\s*\(", exts=(".py",)),
    dict(name="Flask", eco="python", deps=["flask"], kind="backend",
         src=r"Flask\s*\(\s*__name__", exts=(".py",)),
    # --- PHP ---------------------------------------------------------------------
    dict(name="Laravel", eco="php", deps=["laravel/framework"], kind="backend",
         src=r"Illuminate\\", exts=(".php",), markers=["artisan"]),
    dict(name="Symfony", eco="php", deps=["symfony/framework-bundle"], kind="backend",
         src=r"Symfony\\", exts=(".php",)),
    # --- Go ----------------------------------------------------------------------
    dict(name="Gin", eco="go", deps=["github.com/gin-gonic/gin"], kind="backend",
         src=r"gin\.(Default|New)\(", exts=(".go",)),
    dict(name="Echo", eco="go", deps=["github.com/labstack/echo*"], kind="backend",
         src=r"echo\.New\(", exts=(".go",)),
    dict(name="Fiber", eco="go", deps=["github.com/gofiber/fiber*"], kind="backend",
         src=r"fiber\.New\(", exts=(".go",)),
    dict(name="Chi", eco="go", deps=["github.com/go-chi/chi*"], kind="backend",
         src=r"chi\.NewRouter\(", exts=(".go",)),
    # --- Ruby / Rust / .NET ------------------------------------------------------
    dict(name="Ruby on Rails", eco="ruby", deps=["rails"], kind="backend",
         src=r"Rails\.application|ApplicationController", exts=(".rb",)),
    dict(name="Sinatra", eco="ruby", deps=["sinatra"], kind="backend",
         src=r"require\s+['\"]sinatra", exts=(".rb",)),
    dict(name="Actix Web", eco="rust", deps=["actix-web"], kind="backend",
         src=r"HttpServer::new", exts=(".rs",)),
    dict(name="Axum", eco="rust", deps=["axum"], kind="backend",
         src=r"Router::new\(\)", exts=(".rs",)),
    dict(name="ASP.NET Core", eco="dotnet", deps=["Microsoft.AspNetCore*"], kind="backend",
         src=r"WebApplication\.CreateBuilder|\[ApiController\]|ControllerBase", exts=(".cs",)),
]

DATA_RULES = [
    # name, ecosystem, dependency patterns, source regex
    ("Prisma", "npm", ["prisma", "@prisma/client"], r"PrismaClient|prisma\.\w+\.(find|create|update|delete)"),
    ("TypeORM", "npm", ["typeorm", "@nestjs/typeorm"], r"@Entity\s*\(|getRepository|DataSource\("),
    ("Sequelize", "npm", ["sequelize", "sequelize-typescript"], r"sequelize|DataTypes\."),
    ("Mongoose / MongoDB", "npm", ["mongoose", "@nestjs/mongoose", "mongodb"], r"mongoose|MongoClient|@Schema\("),
    ("Knex", "npm", ["knex"], r"knex\("),
    ("Drizzle ORM", "npm", ["drizzle-orm"], r"drizzle\("),
    ("PostgreSQL", "npm", ["pg", "postgres", "@vercel/postgres", "@neondatabase/serverless"], r"Pool\(|postgres\(|sql`"),
    ("MySQL", "npm", ["mysql", "mysql2"], r"createConnection|createPool"),
    ("SQLite", "npm", ["sqlite3", "better-sqlite3"], r"Database\("),
    ("Redis", "npm", ["redis", "ioredis", "@upstash/redis"], r"createClient|new Redis|Redis\("),
    ("JPA / Hibernate", "jvm", ["spring-boot-starter-data-jpa", "hibernate-*", "jakarta.persistence*"],
     r"@Entity\b|JpaRepository|EntityManager"),
    ("Spring Data MongoDB", "jvm", ["spring-boot-starter-data-mongodb"], r"MongoRepository|@Document"),
    ("Flyway", "jvm", ["flyway-*"], None),
    ("Liquibase", "jvm", ["liquibase-*"], None),
    ("PostgreSQL", "jvm", ["postgresql"], None),
    ("MySQL", "jvm", ["mysql-connector*"], None),
    ("H2", "jvm", ["h2"], None),
    ("Django ORM", "python", ["django"], r"models\.Model|objects\.(filter|get|all|raw)"),
    ("SQLAlchemy", "python", ["sqlalchemy", "flask-sqlalchemy", "sqlmodel"], r"declarative_base|Session\(|select\("),
    ("Alembic", "python", ["alembic"], None),
    ("PostgreSQL", "python", ["psycopg2", "psycopg2-binary", "psycopg", "asyncpg"], None),
    ("MongoDB", "python", ["pymongo", "motor", "mongoengine"], None),
    ("Redis", "python", ["redis"], None),
    ("Eloquent ORM", "php", ["laravel/framework"], r"extends\s+Model\b|Eloquent"),
    ("Doctrine ORM", "php", ["doctrine/orm"], r"Doctrine\\ORM"),
    ("GORM", "go", ["gorm.io/gorm"], r"gorm\.Open"),
    ("pgx (PostgreSQL)", "go", ["github.com/jackc/pgx*"], None),
    ("database/sql", "go", [], r"\"database/sql\""),
    ("Active Record", "ruby", ["rails", "activerecord"], r"ActiveRecord::"),
    ("Diesel", "rust", ["diesel"], None),
    ("SQLx", "rust", ["sqlx"], None),
    ("Entity Framework Core", "dotnet", ["Microsoft.EntityFrameworkCore*"], r"DbContext"),
]

TEST_RULES = [
    ("Jest", "npm", ["jest", "ts-jest", "@jest/*"]),
    ("Vitest", "npm", ["vitest"]),
    ("Mocha", "npm", ["mocha"]),
    ("Jasmine / Karma", "npm", ["jasmine*", "karma"]),
    ("Playwright", "npm", ["@playwright/test", "playwright"]),
    ("Cypress", "npm", ["cypress"]),
    ("Testing Library", "npm", ["@testing-library/*"]),
    ("Supertest", "npm", ["supertest"]),
    ("JUnit", "jvm", ["junit*", "spring-boot-starter-test"]),
    ("Mockito", "jvm", ["mockito*", "spring-boot-starter-test"]),
    ("Testcontainers", "jvm", ["testcontainers*", "*testcontainers*"]),
    ("pytest", "python", ["pytest", "pytest-*"]),
    ("PHPUnit", "php", ["phpunit/phpunit"]),
    ("Pest", "php", ["pestphp/pest"]),
    ("testify", "go", ["github.com/stretchr/testify"]),
    ("RSpec", "ruby", ["rspec*"]),
    ("xUnit / NUnit", "dotnet", ["xunit*", "NUnit*"]),
]

TEST_FILE_PATTERNS = [
    "*.test.*", "*.spec.*", "*_test.go", "test_*.py", "*_test.py", "*Test.java", "*Tests.java",
    "*IT.java", "*Test.kt", "*Test.php", "*_spec.rb", "*Tests.cs",
]

CRITICAL_PATTERNS = {
    "security_sensitive": re.compile(
        r"(auth|login|logout|session|jwt|oauth|saml|sso|passw|crypto|encrypt|secret|token|"
        r"permission|role|acl|rbac|guard|policy|admin|upload|webhook|csrf|cors|security)", re.I),
    "money_or_business_critical": re.compile(
        r"(payment|billing|checkout|invoice|wallet|transfer|ledger|refund|charge|order|subscription|"
        r"price|pricing|loan|account|transaction)", re.I),
    "request_handlers": re.compile(
        r"(controller|route|router|handler|resolver|endpoint|/api/|views?\.py|urls\.py|middleware|"
        r"interceptor|filter)", re.I),
    "data_access": re.compile(
        r"(repository|repo\.|dao|model|entity|schema|migration|migrate|prisma|query|queries|\.sql$|db/|(^|/)db\.|database)",
        re.I),
}

DOC_PATTERNS = [
    "README*", "CONTRIBUTING*", "CLAUDE.md", "AGENTS.md", "ARCHITECTURE*", "SECURITY*",
    "CODING_STANDARDS*", "STYLEGUIDE*", "docs/*.md", "docs/adr/*", "doc/*.md", ".editorconfig",
    ".eslintrc*", "eslint.config.*", ".prettierrc*", "biome.json", "tsconfig.json", "checkstyle*.xml",
    "pmd*.xml", ".golangci.y*ml", "ruff.toml", ".flake8", "setup.cfg", "phpcs.xml*", "phpstan.neon*",
    ".rubocop.yml", "sonar-project.properties", ".pre-commit-config.yaml", "CODEOWNERS", ".github/CODEOWNERS",
]


def _match_any(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _dep_hits(deps, patterns):
    hits = []
    for dep, ver in deps.items():
        if _match_any(dep, patterns):
            hits.append((dep, ver))
    return hits


# --- Manifest parsers -----------------------------------------------------------

def parse_package_json(text):
    try:
        data = json.loads(text)
    except ValueError:
        return {}, {}
    deps = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps.update(data.get(key) or {})
    return deps, data


def parse_maven(text):
    deps = {}
    for m in re.finditer(r"<artifactId>\s*([^<\s]+)\s*</artifactId>(?:\s*<version>\s*([^<\s]+)\s*</version>)?", text):
        deps.setdefault(m.group(1), m.group(2) or "")
    return deps


def parse_gradle(text):
    deps = {}
    for m in re.finditer(r"""['"]([\w.\-]+):([\w.\-]+)(?::([\w.\-]+))?['"]""", text):
        deps.setdefault(m.group(2), m.group(3) or "")
    for m in re.finditer(r"""id\s*\(?\s*['"]([\w.\-]+)['"]\s*\)?\s*(?:version\s*['"]([\w.\-]+)['"])?""", text):
        plugin = m.group(1)
        if plugin == "org.springframework.boot":
            deps.setdefault("spring-boot", m.group(2) or "")
        else:
            deps.setdefault(plugin, m.group(2) or "")
    return deps


def parse_python_reqs(text):
    deps = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "[")):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*([<>=!~]=?\s*[\w.*]+)?", line)
        if m:
            deps[m.group(1).lower()] = (m.group(2) or "").replace(" ", "")
    return deps


def parse_pyproject(text):
    deps = {}
    # PEP 621 dependency arrays and Poetry tables, without a TOML parser for 3.8 compat.
    for m in re.finditer(r"""['"]([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*([<>=!~^]=?[^'"]*)?['"]""", text):
        deps.setdefault(m.group(1).lower(), (m.group(2) or "").strip())
    for m in re.finditer(r"""^\s*([A-Za-z0-9_.\-]+)\s*=\s*['"{]""", text, re.M):
        deps.setdefault(m.group(1).lower(), "")
    return deps


def parse_composer(text):
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    deps = {}
    deps.update(data.get("require") or {})
    deps.update(data.get("require-dev") or {})
    return deps


def parse_go_mod(text):
    deps = {}
    for m in re.finditer(r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-/]+)\s+(v[\w.\-+]+)", text, re.M):
        deps[m.group(1)] = m.group(2)
    return deps


def parse_gemfile(text):
    return {m.group(1): m.group(2) or "" for m in
            re.finditer(r"""^\s*gem\s+['"]([\w\-]+)['"](?:\s*,\s*['"]([^'"]+)['"])?""", text, re.M)}


def parse_cargo(text):
    deps = {}
    section = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            section = s
            continue
        if section and "dependencies" in section:
            m = re.match(r"^([\w\-]+)\s*=", s)
            if m:
                deps[m.group(1)] = ""
    return deps


def parse_csproj(text):
    return {m.group(1): m.group(2) or "" for m in
            re.finditer(r'<PackageReference\s+Include="([^"]+)"(?:\s+Version="([^"]+)")?', text)}


MANIFESTS = [
    # filename glob, ecosystem, parser, package manager
    ("package.json", "npm", None, "npm"),
    ("pom.xml", "jvm", parse_maven, "Maven"),
    ("build.gradle", "jvm", parse_gradle, "Gradle"),
    ("build.gradle.kts", "jvm", parse_gradle, "Gradle"),
    ("requirements*.txt", "python", parse_python_reqs, "pip"),
    ("pyproject.toml", "python", parse_pyproject, "pip/pyproject"),
    ("Pipfile", "python", parse_pyproject, "pipenv"),
    ("setup.py", "python", parse_pyproject, "setuptools"),
    ("composer.json", "php", parse_composer, "Composer"),
    ("go.mod", "go", parse_go_mod, "Go modules"),
    ("Gemfile", "ruby", parse_gemfile, "Bundler"),
    ("Cargo.toml", "rust", parse_cargo, "Cargo"),
    ("*.csproj", "dotnet", parse_csproj, "NuGet"),
]

LOCKFILES = {
    "package-lock.json": "npm", "yarn.lock": "Yarn", "pnpm-lock.yaml": "pnpm", "bun.lockb": "Bun",
    "bun.lock": "Bun", "poetry.lock": "Poetry", "uv.lock": "uv", "Pipfile.lock": "pipenv",
    "pdm.lock": "PDM", "composer.lock": "Composer", "go.sum": "Go modules", "Gemfile.lock": "Bundler",
    "Cargo.lock": "Cargo", "gradle.lockfile": "Gradle",
}


class Detector:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.files = list(iter_repo_files(self.root))
        self._text_cache = {}

    def text(self, rel):
        if rel not in self._text_cache:
            self._text_cache[rel] = read_text(self.root, rel)
        return self._text_cache[rel]

    def files_under(self, prefix, exts=None):
        pre = "" if prefix in ("", ".") else prefix.rstrip("/") + "/"
        out = []
        for f in self.files:
            if pre and not f.startswith(pre):
                continue
            if exts and not f.endswith(tuple(exts)):
                continue
            out.append(f)
        return out

    def find_usage(self, prefix, regex, exts, limit=2500):
        """Return the first file:line whose content matches regex, or None."""
        pat = re.compile(regex)
        for rel in self.files_under(prefix, exts)[:limit]:
            text = self.text(rel)
            if not text:
                continue
            m = pat.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                return "%s:%d" % (rel, line)
        return None

    # -------------------------------------------------------------------------
    def languages(self):
        counts = {}
        for f in self.files:
            ext = os.path.splitext(f)[1].lower()
            lang = LANG_BY_EXT.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
        return [{"name": k, "files": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]

    def manifests(self):
        found = []
        for rel in self.files:
            base = os.path.basename(rel)
            for pattern, eco, parser, pm in MANIFESTS:
                if fnmatch.fnmatch(base, pattern):
                    found.append((rel, eco, parser, pm))
                    break
        return found

    def projects(self):
        projects = {}
        for rel, eco, parser, pm in self.manifests():
            text = self.text(rel) or ""
            pdir = os.path.dirname(rel) or "."
            proj = projects.setdefault(pdir, {
                "path": pdir, "manifests": [], "package_managers": [], "ecosystems": [], "deps": {},
                "workspace_root": False,
            })
            proj["manifests"].append(rel)
            if eco not in proj["ecosystems"]:
                proj["ecosystems"].append(eco)
            if parser is None:  # package.json
                deps, data = parse_package_json(text)
                if data.get("workspaces"):
                    proj["workspace_root"] = True
                proj["deps"].setdefault(eco, {}).update(deps)
                proj["scripts"] = data.get("scripts") or {}
                proj["node_main"] = data.get("main")
            else:
                proj["deps"].setdefault(eco, {}).update(parser(text))
            if pm not in proj["package_managers"]:
                proj["package_managers"].append(pm)
        for pdir, proj in projects.items():
            for lock, pm in LOCKFILES.items():
                lock_rel = lock if pdir == "." else pdir + "/" + lock
                if lock_rel in self.files:
                    if pm not in proj["package_managers"]:
                        proj["package_managers"].append(pm)
                    proj.setdefault("lockfiles", []).append(lock_rel)
                    # A lockfile is more specific than the generic "npm" manifest guess.
                    if pm in ("Yarn", "pnpm", "Bun") and "npm" in proj["package_managers"]:
                        proj["package_managers"].remove("npm")
            for marker in ("pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json"):
                if (marker if pdir == "." else pdir + "/" + marker) in self.files:
                    proj["workspace_root"] = True
        return projects

    def detect_project(self, proj):
        pdir = proj["path"]
        frameworks, data, testing = [], [], []
        for rule in RULES:
            deps = proj["deps"].get(rule["eco"], {})
            hits = _dep_hits(deps, rule["deps"])
            if not hits:
                continue
            evidence = ["%s declares %s%s" % (proj["manifests"][0] if len(proj["manifests"]) == 1 else pdir,
                                               hits[0][0], ("@" + hits[0][1]) if hits[0][1] else "")]
            for marker in rule.get("markers", []):
                mrel = marker if pdir == "." else pdir + "/" + marker
                if mrel in self.files:
                    evidence.append("config file " + mrel)
            usage = self.find_usage(pdir, rule["src"], rule["exts"])
            if usage:
                evidence.append("used in " + usage)
            frameworks.append({
                "name": rule["name"], "version": hits[0][1] or None, "kind": rule["kind"],
                "confidence": "confirmed" if usage else "manifest-only", "evidence": evidence,
            })
        for name, eco, deps_pat, src in DATA_RULES:
            deps = proj["deps"].get(eco, {})
            hits = _dep_hits(deps, deps_pat) if deps_pat else []
            usage = None
            if src and (hits or not deps_pat):
                exts = {"npm": JS_EXT, "jvm": (".java", ".kt"), "python": (".py",), "php": (".php",),
                        "go": (".go",), "ruby": (".rb",), "rust": (".rs",), "dotnet": (".cs",)}[eco]
                if eco in proj["ecosystems"]:
                    usage = self.find_usage(pdir, src, exts)
            if not hits and not usage:
                continue
            if any(d["name"] == name for d in data):
                continue
            ev = []
            if hits:
                ev.append("declares " + hits[0][0])
            if usage:
                ev.append("used in " + usage)
            data.append({"name": name, "confidence": "confirmed" if usage or not src else "manifest-only",
                         "evidence": ev})
        if any(f.endswith("schema.prisma") for f in self.files_under(pdir)):
            if not any(d["name"] == "Prisma" for d in data):
                data.append({"name": "Prisma", "confidence": "confirmed", "evidence": ["schema.prisma present"]})
        for name, eco, deps_pat in TEST_RULES:
            hits = _dep_hits(proj["deps"].get(eco, {}), deps_pat)
            if hits:
                testing.append({"name": name, "evidence": ["declares " + hits[0][0]]})
        return frameworks, data, testing

    def infrastructure(self):
        infra, ci = {}, {}

        def add(bucket, name, ev):
            entry = bucket.setdefault(name, {"name": name, "evidence": []})
            if len(entry["evidence"]) < 8:
                entry["evidence"].append(ev)

        for rel in self.files:
            base = os.path.basename(rel)
            low = base.lower()
            if low.startswith("dockerfile") or low.endswith(".dockerfile"):
                add(infra, "Docker", rel)
            elif re.match(r"^(docker-)?compose(\.[\w-]+)?\.ya?ml$", low):
                add(infra, "Docker Compose", rel)
            elif low.endswith(".tf") or low.endswith(".tfvars"):
                add(infra, "Terraform", rel)
            elif low == "chart.yaml":
                add(infra, "Helm", rel)
            elif low in ("kustomization.yaml", "kustomization.yml"):
                add(infra, "Kustomize", rel)
            elif low in ("serverless.yml", "serverless.yaml"):
                add(infra, "Serverless Framework", rel)
            elif low == "pulumi.yaml":
                add(infra, "Pulumi", rel)
            elif low in ("vercel.json", "netlify.toml", "fly.toml", "app.yaml", "procfile", "railway.json",
                         "render.yaml", "amplify.yml"):
                add(infra, "PaaS config", rel)
            elif low == ".env" or low.startswith(".env."):
                add(infra, "Environment files", rel)
            elif low in ("nginx.conf",) or rel.endswith(".nginx.conf"):
                add(infra, "Nginx", rel)
            if rel.startswith(".github/workflows/") and low.endswith((".yml", ".yaml")):
                add(ci, "GitHub Actions", rel)
            elif low == ".gitlab-ci.yml":
                add(ci, "GitLab CI", rel)
            elif low == "jenkinsfile":
                add(ci, "Jenkins", rel)
            elif rel.startswith(".circleci/"):
                add(ci, "CircleCI", rel)
            elif low in ("azure-pipelines.yml", "bitbucket-pipelines.yml", ".travis.yml", "cloudbuild.yaml"):
                add(ci, os.path.splitext(base)[0], rel)
            elif rel.startswith(".github/") and low == "dependabot.yml":
                add(ci, "Dependabot", rel)
            elif low in ("renovate.json", ".renovaterc", ".renovaterc.json"):
                add(ci, "Renovate", rel)
        # Kubernetes manifests: YAML that declares apiVersion + a workload kind.
        k8s = re.compile(r"^apiVersion:\s*\S+[\s\S]*?^kind:\s*(Deployment|StatefulSet|DaemonSet|Service|Ingress|"
                         r"CronJob|Job|Pod|ConfigMap|Secret)\b", re.M)
        for rel in self.files:
            if rel.endswith((".yaml", ".yml")) and "Helm" not in rel:
                text = self.text(rel)
                if text and k8s.search(text):
                    add(infra, "Kubernetes", rel)
        if "Terraform" in infra:
            providers = set()
            for rel in [f for f in self.files if f.endswith(".tf")]:
                for m in re.finditer(r'(?:provider\s+"([\w-]+)"|source\s*=\s*"[\w.-]+/([\w-]+)")', self.text(rel) or ""):
                    providers.add(m.group(1) or m.group(2))
            infra["Terraform"]["providers"] = sorted(providers)
        return list(infra.values()), list(ci.values())

    def entry_points(self, projects):
        eps = []

        def add(rel, why):
            if rel in self.files and not any(e["file"] == rel for e in eps):
                eps.append({"file": rel, "reason": why})

        for pdir, proj in projects.items():
            pre = "" if pdir == "." else pdir + "/"
            if proj.get("node_main"):
                add(pre + proj["node_main"].lstrip("./"), "package.json main")
            for cand in ("src/main.ts", "src/main.js", "src/index.ts", "src/index.js", "src/server.ts",
                         "server.js", "server.ts", "app.js", "index.js", "src/app.ts", "main.py", "app.py",
                         "manage.py", "app/main.py", "main.go", "cmd/main.go", "public/index.php",
                         "routes/api.php", "routes/web.php", "app/layout.tsx", "app/layout.jsx",
                         "src/app/layout.tsx", "pages/_app.tsx", "pages/_app.js", "src/pages/_app.tsx",
                         "middleware.ts", "src/middleware.ts", "Program.cs", "config/routes.rb"):
                add(pre + cand, "conventional entry point (file exists)")
        for rel in self.files:
            if re.search(r"(^|/)app/(.+/)?route\.(t|j)sx?$", rel):
                add(rel, "Next.js route handler")
            elif re.search(r"(^|/)pages/api/", rel) and rel.endswith((".ts", ".js", ".tsx", ".jsx")):
                add(rel, "Next.js API route")
        for rel in self.files_under(".", (".ts", ".tsx", ".js", ".jsx"))[:4000]:
            text = self.text(rel)
            if text and re.match(r"\s*['\"]use server['\"]", text):
                add(rel, "Next.js server actions")
        patterns = [
            (r"@SpringBootApplication", (".java", ".kt"), "Spring Boot application class"),
            (r"NestFactory\.create", (".ts", ".js"), "NestJS bootstrap"),
            (r"^func\s+main\s*\(", (".go",), "Go main()"),
            (r"FastAPI\s*\(", (".py",), "FastAPI app"),
            (r"Flask\s*\(\s*__name__", (".py",), "Flask app"),
            (r"if\s+__name__\s*==\s*['\"]__main__['\"]", (".py",), "Python __main__"),
        ]
        for regex, exts, why in patterns:
            pat = re.compile(regex, re.M)
            for rel in self.files_under(".", exts)[:4000]:
                if len(eps) >= 40:
                    break
                text = self.text(rel)
                if text and pat.search(text):
                    add(rel, why)
        return eps[:40]

    def critical_paths(self):
        out = {}
        code_ext = tuple(k for k in LANG_BY_EXT if k not in (".css", ".scss", ".sass", ".less", ".html")) + (".prisma",)
        for key, pat in CRITICAL_PATTERNS.items():
            hits = [f for f in self.files if f.endswith(code_ext) and pat.search(f)]
            out[key] = {"count": len(hits), "files": hits[:60]}
        return out

    def tests(self):
        tests = [f for f in self.files if _match_any(os.path.basename(f), TEST_FILE_PATTERNS)
                 or "/__tests__/" in "/" + f or f.startswith(("test/", "tests/")) or "/src/test/" in "/" + f]
        return tests

    def docs(self):
        return [f for f in self.files if _match_any(f, DOC_PATTERNS)][:40]


def recommend_agents(frameworks, data, infra, ci, languages, files, test_files):
    kinds = {f["kind"] for f in frameworks}
    names = {f["name"] for f in frameworks}
    lang_names = {l["name"] for l in languages}
    rec, skip = [], []

    def decide(agent, cond, why_yes, why_no):
        (rec if cond else skip).append({"agent": agent, "reason": why_yes if cond else why_no})

    rec.append({"agent": "architecture-reviewer", "reason": "always run: architecture and code quality"})
    rec.append({"agent": "security-reviewer", "reason": "always run: security"})
    rec.append({"agent": "performance-reviewer", "reason": "always run: performance"})
    has_backend = bool(kinds & {"backend", "fullstack"})
    next_server = "Next.js" in names and any(
        re.search(r"(^|/)(app/.*/route\.(t|j)sx?|pages/api/|.*actions?\.(t|j)sx?$)", f) for f in files)
    decide("backend-reviewer", has_backend or next_server,
           "server-side framework detected: " + ", ".join(sorted(n for n in names if n in {
               f["name"] for f in frameworks if f["kind"] in ("backend", "fullstack")})),
           "no server-side framework or API handlers detected")
    has_frontend = bool(kinds & {"frontend", "fullstack", "mobile"}) or bool(
        lang_names & {"Vue SFC", "Svelte"}) or any(f.endswith((".jsx", ".tsx")) for f in files)
    decide("frontend-reviewer", has_frontend, "frontend framework or UI components detected",
           "no frontend framework or UI component files detected")
    has_db = bool(data) or "SQL" in lang_names or any(
        re.search(r"(^|/)(migrations?|db/migrate|db/migration)/", f) for f in files)
    decide("database-reviewer", has_db, "database/ORM/migrations detected: " + ", ".join(d["name"] for d in data[:6]),
           "no database technology, ORM, SQL or migrations detected")
    rec.append({"agent": "testing-reviewer",
                "reason": "always run: %d test files found" % len(test_files) if test_files
                else "always run: no test files found (coverage gap)"})
    decide("devops-reviewer", bool(infra or ci),
           "infrastructure/CI detected: " + ", ".join(sorted({i["name"] for i in infra + ci})),
           "no Docker, IaC, CI/CD or deployment configuration detected")
    order = {"architecture-reviewer": 0, "security-reviewer": 1, "performance-reviewer": 2,
             "backend-reviewer": 3, "frontend-reviewer": 4, "database-reviewer": 5,
             "testing-reviewer": 6, "devops-reviewer": 7}
    rec.sort(key=lambda r: order[r["agent"]])
    return rec, skip


def detect(root):
    d = Detector(root)
    projects = d.projects()
    all_fw, all_data, all_test, proj_out = [], [], [], []
    for pdir in sorted(projects):
        proj = projects[pdir]
        fw, data, testing = d.detect_project(proj)
        proj_out.append({
            "path": pdir, "manifests": proj["manifests"], "package_managers": proj["package_managers"],
            "lockfiles": proj.get("lockfiles", []), "workspace_root": proj["workspace_root"],
            "frameworks": fw, "databases": data, "testing": testing,
            "dependency_count": sum(len(v) for v in proj["deps"].values()),
        })
        for src, dst in ((fw, all_fw), (data, all_data), (testing, all_test)):
            for item in src:
                existing = next((x for x in dst if x["name"] == item["name"]), None)
                if existing is None:
                    dst.append(dict(item, projects=[pdir]))
                else:
                    existing["projects"].append(pdir)
                    if item.get("confidence") == "confirmed":
                        existing["confidence"] = "confirmed"
    languages = d.languages()
    infra, ci = d.infrastructure()
    test_files = d.tests()
    runtimes = []
    eco_seen = {e for p in projects.values() for e in p["ecosystems"]}
    lang_names = {l["name"] for l in languages}
    if "npm" in eco_seen and lang_names & {"JavaScript", "TypeScript"}:
        runtimes.append("Node.js")
    for eco, rt in (("jvm", "JVM"), ("python", "Python"), ("php", "PHP"), ("go", "Go"), ("ruby", "Ruby"),
                    ("rust", "Rust"), ("dotnet", ".NET")):
        if eco in eco_seen:
            runtimes.append(rt)
    rec, skip = recommend_agents(all_fw, all_data, infra, ci, languages, d.files, test_files)
    monorepo = sum(1 for p in proj_out if p["manifests"]) > 1 or any(p["workspace_root"] for p in proj_out)
    return {
        "root": d.root,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "file_count": len(d.files),
        "languages": languages,
        "runtimes": runtimes,
        "architecture_shape": "monorepo / multi-project" if monorepo else "single project",
        "projects": proj_out,
        "frameworks": all_fw,
        "databases": all_data,
        "testing": {"frameworks": all_test, "test_file_count": len(test_files), "test_files_sample": test_files[:40]},
        "infrastructure": infra,
        "ci_cd": ci,
        "entry_points": d.entry_points(projects),
        "critical_paths": d.critical_paths(),
        "documentation": d.docs(),
        "recommended_agents": rec,
        "skipped_agents": skip,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("-o", "--output", default="-")
    ap.add_argument("--brief", action="store_true", help="also print a compact text summary to stderr")
    ap.add_argument("--files-out", help="write the reviewable file inventory (one path per line) here")
    args = ap.parse_args()
    result = detect(args.root)
    dump_json(result, args.output)
    if args.files_out:
        with open(args.files_out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(iter_repo_files(os.path.abspath(args.root))) + "\n")
    if args.brief:
        print(brief(result), file=sys.stderr)


def brief(r):
    """Compact human-readable digest of a detect() result."""
    def names(items):
        return ", ".join("%s%s%s" % (i["name"], " " + i["version"] if i.get("version") else "",
                                     "" if i.get("confidence", "confirmed") == "confirmed" else " [manifest-only]")
                         for i in items) or "none"
    lines = [
        "files: %d | shape: %s" % (r["file_count"], r["architecture_shape"]),
        "languages: " + (", ".join("%s(%d)" % (l["name"], l["files"]) for l in r["languages"][:8]) or "none"),
        "runtimes: " + (", ".join(r["runtimes"]) or "none"),
        "frameworks: " + names(r["frameworks"]),
        "databases: " + names(r["databases"]),
        "testing: %s | test files: %d" % (", ".join(t["name"] for t in r["testing"]["frameworks"]) or "none",
                                         r["testing"]["test_file_count"]),
        "infrastructure: " + (", ".join(i["name"] for i in r["infrastructure"]) or "none"),
        "ci/cd: " + (", ".join(i["name"] for i in r["ci_cd"]) or "none"),
        "projects: " + "; ".join("%s [%s]" % (p["path"], ", ".join(p["package_managers"])) for p in r["projects"]),
        "entry points: " + (", ".join(e["file"] for e in r["entry_points"][:12]) or "none found"),
        "critical paths: " + ", ".join("%s=%d" % (k, v["count"]) for k, v in r["critical_paths"].items()),
        "docs/standards: " + (", ".join(r["documentation"][:15]) or "none"),
        "agents: " + ", ".join(a["agent"] for a in r["recommended_agents"]),
        "skipped: " + ("; ".join("%s (%s)" % (a["agent"], a["reason"]) for a in r["skipped_agents"]) or "none"),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
