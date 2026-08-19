from pathlib import Path
import json, textwrap, zipfile, os

root = Path("/mnt/data/github-tech-stack-workflow")
(root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
(root / "scripts").mkdir(parents=True, exist_ok=True)
(root / "data").mkdir(parents=True, exist_ok=True)

workflow = """name: Update GitHub Tech Stack

on:
  schedule:
    # Daily at 00:30 UTC (06:00 IST)
    - cron: "30 0 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Generate GitHub analytics
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_ANALYTICS_TOKEN }}
          GITHUB_USERNAME: yuvrajkarna2717
        run: python scripts/github_analyzer.py

      - name: Commit updated analytics
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add data/github-stats.json

          if git diff --cached --quiet; then
            echo "No analytics changes to commit."
          else
            git commit -m "chore: update github analytics"
            git push
          fi
"""

analyzer = r'''#!/usr/bin/env python3
"""
GitHub Tech Stack Analyzer
==========================

Designed to run inside GitHub Actions.

What it does:
- Uses an authenticated GitHub token.
- Reads public + private repositories accessible to that token.
- Finds repositories where the requested user authored commits in the last 12 months.
- Detects languages using GitHub's language API.
- Detects technologies from package.json, requirements.txt and pyproject.toml.
- Detects Docker, GitHub Actions, TypeScript, Vite, Next.js, etc. from files.
- Stores the latest snapshot plus daily history in data/github-stats.json.

Environment:
    GITHUB_TOKEN      Required
    GITHUB_USERNAME   Optional; defaults to yuvrajkarna2717

Run locally:
    GITHUB_TOKEN=... GITHUB_USERNAME=yuvrajkarna2717 python scripts/github_analyzer.py

No third-party Python packages are required.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.github.com"
USERNAME = os.getenv("GITHUB_USERNAME", "yuvrajkarna2717")
TOKEN = os.getenv("GITHUB_TOKEN")
OUTPUT = os.getenv("GITHUB_STATS_OUTPUT", "data/github-stats.json")
MONTHS = int(os.getenv("GITHUB_ANALYSIS_MONTHS", "12"))

if not TOKEN:
    raise SystemExit("GITHUB_TOKEN is missing.")

PACKAGE_SIGNALS = {
    # JS / TS
    "react": "React",
    "react-dom": "React",
    "next": "Next.js",
    "vite": "Vite",
    "express": "Express",
    "fastify": "Fastify",
    "@nestjs/core": "NestJS",
    "mongoose": "Mongoose",
    "mongodb": "MongoDB",
    "pg": "PostgreSQL",
    "prisma": "Prisma",
    "@prisma/client": "Prisma",
    "sequelize": "Sequelize",
    "@reduxjs/toolkit": "Redux Toolkit",
    "redux": "Redux",
    "react-redux": "Redux",
    "@tanstack/react-query": "TanStack Query",
    "axios": "Axios",
    "zod": "Zod",
    "typescript": "TypeScript",
    "tailwindcss": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    "react-bootstrap": "React Bootstrap",
    "framer-motion": "Framer Motion",
    "socket.io": "Socket.IO",
    "jsonwebtoken": "JWT",
    "passport": "Passport.js",
    "passport-google-oauth20": "Google OAuth",
    "openai": "OpenAI API",
    "@anthropic-ai/sdk": "Anthropic API",
    "@google/generative-ai": "Google Gemini API",
    "langchain": "LangChain",
    "@langchain/core": "LangChain",
    "@langchain/langgraph": "LangGraph",
    "langgraph": "LangGraph",

    # Python
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "pydantic": "Pydantic",
    "uvicorn": "Uvicorn",
    "sqlalchemy": "SQLAlchemy",
    "alembic": "Alembic",
    "requests": "Requests",
    "httpx": "HTTPX",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "scipy": "SciPy",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "transformers": "Hugging Face Transformers",
    "opencv-python": "OpenCV",
    "cv2": "OpenCV",
    "langchain-community": "LangChain",
    "langchain-openai": "LangChain",
    "openai": "OpenAI API",
    "anthropic": "Anthropic API",
    "google-generativeai": "Google Gemini API",
    "redis": "Redis",
    "celery": "Celery",

    # Tooling
    "eslint": "ESLint",
    "prettier": "Prettier",
    "jest": "Jest",
    "vitest": "Vitest",
    "playwright": "Playwright",
    "cypress": "Cypress",
}

LANGUAGE_ALIASES = {
    "Jupyter Notebook": "Jupyter",
}


class GitHub:
    def __init__(self, token: str):
        self.token = token
        self.cache: dict[str, object] = {}

    def get(self, path: str, params: dict | None = None):
        url = path if path.startswith("http") else API + path
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)

        if url in self.cache:
            return self.cache[url]

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "yuvrajkarna-github-tech-stack",
        }

        for attempt in range(4):
            try:
                req = Request(url, headers=headers)
                with urlopen(req, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    self.cache[url] = data
                    return data
            except HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if e.code in (403, 429) and attempt < 3:
                    retry = e.headers.get("Retry-After")
                    wait = int(retry) if retry else min(2 ** attempt, 30)
                    print(f"Rate limited; waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"GitHub API {e.code}: {body[:500]}") from e
            except URLError as e:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Network error: {e}") from e

        raise RuntimeError(f"Request failed: {url}")

    def pages(self, path: str, params: dict | None = None):
        params = dict(params or {})
        params["per_page"] = 100
        result = []
        page = 1

        while True:
            params["page"] = page
            data = self.get(path, params)
            if not isinstance(data, list):
                return data
            result.extend(data)
            if len(data) < 100:
                return result
            page += 1


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_package_json(text: str):
    found = Counter()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return found

    for section in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        deps = data.get(section, {})
        if not isinstance(deps, dict):
            continue
        for name in deps:
            tech = PACKAGE_SIGNALS.get(name.lower())
            if tech:
                found[tech] += 1

    scripts = data.get("scripts", {})
    if isinstance(scripts, dict):
        scripts_text = " ".join(map(str, scripts.values())).lower()
        for needle, tech in {
            "vite": "Vite",
            "webpack": "Webpack",
            "rollup": "Rollup",
            "eslint": "ESLint",
            "prettier": "Prettier",
            "jest": "Jest",
            "vitest": "Vitest",
            "playwright": "Playwright",
            "cypress": "Cypress",
            "tsc": "TypeScript",
        }.items():
            if needle in scripts_text:
                found[tech] += 1

    return found


def detect_requirements(text: str):
    found = Counter()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)", line)
        if not match:
            continue
        name = match.group(1).lower()
        tech = PACKAGE_SIGNALS.get(name)
        if tech:
            found[tech] += 1
    return found


def detect_pyproject(text: str):
    found = Counter()
    lower = text.lower()
    for package, tech in PACKAGE_SIGNALS.items():
        if re.search(
            rf'(?m)["\']?{re.escape(package.lower())}(?:\[[^\]]+\])?\s*(?:=|>|<|!|~|:)',
            lower,
        ):
            found[tech] += 1
    return found


def decode_file(obj):
    if not isinstance(obj, dict) or obj.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(obj["content"]).decode("utf-8", errors="replace")
    except Exception:
        return None


def file_signals(files: list[str]):
    found = Counter()
    lower = {f.lower() for f in files}

    if any(PurePosixPath(f).name.lower().startswith("dockerfile") for f in files):
        found["Docker"] += 1
    if any(f.startswith(".github/workflows/") for f in lower):
        found["GitHub Actions"] += 1

    direct = {
        "package.json": "Node.js",
        "requirements.txt": "Python",
        "pyproject.toml": "Python",
        "tsconfig.json": "TypeScript",
        "vite.config.js": "Vite",
        "vite.config.ts": "Vite",
        "vite.config.mjs": "Vite",
        "vite.config.cjs": "Vite",
        "next.config.js": "Next.js",
        "next.config.mjs": "Next.js",
        "next.config.ts": "Next.js",
        "tailwind.config.js": "Tailwind CSS",
        "tailwind.config.ts": "Tailwind CSS",
    }
    for name, tech in direct.items():
        if name in lower:
            found[tech] += 1
    return found


def repo_files(api: GitHub, full_name: str, branch: str):
    try:
        data = api.get(
            f"/repos/{full_name}/git/trees/{branch}",
            {"recursive": "1"},
        )
        return [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob"
        ]
    except Exception as e:
        print(f"  Could not inspect tree: {e}", file=sys.stderr)
        return []


def read_file(api: GitHub, full_name: str, path: str, branch: str):
    try:
        obj = api.get(
            f"/repos/{full_name}/contents/{path}",
            {"ref": branch},
        )
        return decode_file(obj)
    except Exception:
        return None


def repo_languages(api: GitHub, full_name: str):
    try:
        return api.get(f"/repos/{full_name}/languages")
    except Exception:
        return {}


def repo_commits(api: GitHub, full_name: str, since: datetime, until: datetime):
    # The authenticated user is used by GitHub when author is omitted.
    # We still pass author=USERNAME to make the intent explicit.
    try:
        return api.pages(
            f"/repos/{full_name}/commits",
            {
                "author": USERNAME,
                "since": iso(since),
                "until": iso(until),
            },
        )
    except Exception:
        return []


def pct(counter: Counter):
    total = sum(counter.values())
    if total == 0:
        return {}
    return {
        key: round(value / total * 100, 2)
        for key, value in counter.most_common()
    }


def load_existing():
    if not os.path.exists(OUTPUT):
        return {
            "schema_version": 1,
            "username": USERNAME,
            "updated_at": None,
            "current": None,
            "history": [],
        }

    try:
        with open(OUTPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("schema_version", 1)
        data.setdefault("history", [])
        return data
    except Exception:
        return {
            "schema_version": 1,
            "username": USERNAME,
            "updated_at": None,
            "current": None,
            "history": [],
        }


def main():
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=MONTHS * 30.4375)

    print(f"GitHub Tech Stack Analyzer: @{USERNAME}")
    print(f"Period: {since.date()} -> {now.date()}")

    api = GitHub(TOKEN)

    # /user/repos is important here:
    # unlike /users/{username}/repos, it can return private repositories
    # accessible to the authenticated token.
    repos = api.pages(
        "/user/repos",
        {
            "visibility": "all",
            "affiliation": "owner,collaborator,organization_member",
            "sort": "updated",
            "direction": "desc",
        },
    )

    if not isinstance(repos, list):
        raise RuntimeError("Unexpected response from /user/repos")

    print(f"Accessible repositories: {len(repos)}")

    languages = Counter()
    technologies = Counter()
    technology_repos = defaultdict(set)
    commit_days = Counter()
    active_repos = []
    total_commits = 0

    for index, repo in enumerate(repos, 1):
        full_name = repo["full_name"]
        print(f"[{index}/{len(repos)}] {full_name}")

        commits = repo_commits(api, full_name, since, now)
        if not commits:
            continue

        total_commits += len(commits)

        for commit in commits:
            date = parse_date(
                (commit.get("commit") or {}).get("author", {}).get("date")
            )
            if date:
                commit_days[date.date().isoformat()] += 1

        raw_languages = repo_languages(api, full_name)
        repo_languages_counter = Counter(
            LANGUAGE_ALIASES.get(lang, lang)
            for lang in raw_languages
        )
        languages.update(
            {
                LANGUAGE_ALIASES.get(lang, lang): amount
                for lang, amount in raw_languages.items()
            }
        )

        tech = Counter()
        tech.update(file_signals(
            repo_files(api, full_name, repo.get("default_branch") or "main")
        ))

        files = repo_files(
            api,
            full_name,
            repo.get("default_branch") or "main",
        )

        # Read only the common root-level manifests.
        branch = repo.get("default_branch") or "main"
        for manifest, detector in (
            ("package.json", detect_package_json),
            ("requirements.txt", detect_requirements),
            ("pyproject.toml", detect_pyproject),
        ):
            if manifest in {f.lower() for f in files}:
                # Find the exact path, preferring root.
                path = next(
                    (f for f in files if f.lower() == manifest),
                    None,
                )
                if path:
                    content = read_file(api, full_name, path, branch)
                    if content:
                        tech.update(detector(content))

        # Languages are also included as technologies.
        tech.update({lang: 1 for lang in repo_languages_counter})

        for name in tech:
            technologies[name] += 1
            technology_repos[name].add(full_name)

        active_repos.append({
            "name": repo.get("name"),
            "full_name": full_name,
            "url": repo.get("html_url"),
            "private": bool(repo.get("private")),
            "fork": bool(repo.get("fork")),
            "commits_by_you": len(commits),
            "languages": dict(repo_languages_counter),
            "technologies": sorted(tech),
        })

    active_repos.sort(key=lambda r: r["commits_by_you"], reverse=True)

    technology_summary = [
        {
            "technology": name,
            "repository_count": count,
            "repositories": sorted(technology_repos[name]),
        }
        for name, count in technologies.most_common()
    ]

    snapshot = {
        "date": now.date().isoformat(),
        "period": {
            "from": since.date().isoformat(),
            "to": now.date().isoformat(),
        },
        "summary": {
            "accessible_repositories": len(repos),
            "active_repositories": len(active_repos),
            "private_active_repositories": sum(
                1 for r in active_repos if r["private"]
            ),
            "public_active_repositories": sum(
                1 for r in active_repos if not r["private"]
            ),
            "commits_by_you": total_commits,
            "active_days": len(commit_days),
        },
        "languages": {
            "bytes": dict(languages.most_common()),
            "percentage": pct(languages),
        },
        "technologies": technology_summary,
        "repositories": active_repos,
        "commit_activity": dict(sorted(commit_days.items())),
    }

    data = load_existing()
    data["username"] = USERNAME
    data["updated_at"] = iso(now)
    data["current"] = snapshot

    # Keep one snapshot per calendar day.
    history = [
        item for item in data.get("history", [])
        if item.get("date") != snapshot["date"]
    ]
    history.append(snapshot)
    history.sort(key=lambda item: item.get("date", ""))
    data["history"] = history

    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\nDone.")
    print(f"Active repositories: {len(active_repos)}")
    print(f"Private active repositories: {snapshot['summary']['private_active_repositories']}")
    print(f"Commits: {total_commits}")
    print(f"Active days: {len(commit_days)}")
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
'''

initial_json = {
    "schema_version": 1,
    "username": "yuvrajkarna2717",
    "updated_at": None,
    "current": None,
    "history": []
}

files = {
    root / ".github" / "workflows" / "github-stats.yml": workflow,
    root / "scripts" / "github_analyzer.py": analyzer,
    root / "data" / "github-stats.json": json.dumps(initial_json, indent=2) + "\n",
}

for path, content in files.items():
    path.write_text(content, encoding="utf-8")

zip_path = Path("/mnt/data/github-tech-stack-workflow.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for path in files:
        z.write(path, path.relative_to(root))

print("Created:")
for p in files:
    print(p)
print(f"ZIP: {zip_path}")
