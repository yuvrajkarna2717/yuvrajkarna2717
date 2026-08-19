#!/usr/bin/env python3

"""
GitHub Tech Stack Analyzer
==========================

Collects GitHub activity and technology information for a user.

Features:
- Public + private repositories accessible to the token
- Last 365 days of activity
- Daily commit activity
- Repository-level statistics
- Language detection
- Technology/framework detection
- Historical daily snapshots
- UI-friendly JSON output

Required environment variables:
    GITHUB_TOKEN
    GITHUB_USERNAME

Output:
    data/github-stats.json
"""

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


# ============================================================
# CONFIGURATION
# ============================================================

GITHUB_API = "https://api.github.com"

GITHUB_USERNAME = os.getenv(
    "GITHUB_USERNAME",
    "yuvrajkarna2717",
)

GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN"
)

OUTPUT_FILE = "data/github-stats.json"

ANALYSIS_DAYS = 365


# ============================================================
# TECHNOLOGY MAPPINGS
# ============================================================

PACKAGE_TO_TECHNOLOGY = {
    # --------------------------------------------------------
    # JavaScript / TypeScript
    # --------------------------------------------------------

    "react": "React",
    "react-dom": "React",
    "next": "Next.js",
    "vite": "Vite",

    "express": "Express",
    "fastify": "Fastify",
    "@nestjs/core": "NestJS",

    # Database
    "mongoose": "Mongoose",
    "mongodb": "MongoDB",
    "pg": "PostgreSQL",
    "prisma": "Prisma",
    "@prisma/client": "Prisma",
    "sequelize": "Sequelize",

    # State / API
    "redux": "Redux",
    "@reduxjs/toolkit": "Redux Toolkit",
    "react-redux": "Redux",
    "@tanstack/react-query": "TanStack Query",

    "axios": "Axios",
    "zod": "Zod",

    # UI
    "bootstrap": "Bootstrap",
    "react-bootstrap": "React Bootstrap",
    "tailwindcss": "Tailwind CSS",
    "framer-motion": "Framer Motion",

    # Authentication / realtime
    "jsonwebtoken": "JWT",
    "passport": "Passport.js",
    "passport-google-oauth20": "Google OAuth",
    "socket.io": "Socket.IO",

    # AI
    "openai": "OpenAI API",
    "@anthropic-ai/sdk": "Anthropic API",
    "@google/generative-ai": "Google Gemini API",

    "langchain": "LangChain",
    "@langchain/core": "LangChain",
    "@langchain/langgraph": "LangGraph",
    "langgraph": "LangGraph",

    # --------------------------------------------------------
    # Python
    # --------------------------------------------------------

    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",

    "pydantic": "Pydantic",
    "uvicorn": "Uvicorn",

    "sqlalchemy": "SQLAlchemy",
    "alembic": "Alembic",

    "requests": "Requests",
    "httpx": "HTTPX",

    # Data / ML
    "numpy": "NumPy",
    "pandas": "Pandas",
    "scipy": "SciPy",

    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",

    "torch": "PyTorch",
    "tensorflow": "TensorFlow",

    "transformers": "Hugging Face Transformers",

    # Computer Vision
    "opencv-python": "OpenCV",

    # Infrastructure
    "redis": "Redis",
    "celery": "Celery",

    # Python AI
    "langchain-community": "LangChain",
    "langchain-openai": "LangChain",

    "google-generativeai": "Google Gemini API",

    # --------------------------------------------------------
    # Development Tools
    # --------------------------------------------------------

    "typescript": "TypeScript",
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


# ============================================================
# GITHUB API CLIENT
# ============================================================

class GitHubClient:
    """
    Small GitHub REST API client.

    Handles:
    - Authentication
    - Requests
    - Pagination
    - Rate limiting
    - Response caching
    """

    def __init__(self, token):
        self.token = token
        self.cache = {}

    def request(self, path, params=None):
        """
        Make a GET request to GitHub API.
        """

        url = (
            path
            if path.startswith("http")
            else GITHUB_API + path
        )

        if params:
            query = urlencode(params)

            separator = (
                "&"
                if "?" in url
                else "?"
            )

            url += separator + query

        if url in self.cache:
            return self.cache[url]

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-tech-stack-analyzer",
        }

        for attempt in range(4):

            try:

                request = Request(
                    url,
                    headers=headers,
                )

                with urlopen(
                    request,
                    timeout=30,
                ) as response:

                    data = json.loads(
                        response
                        .read()
                        .decode("utf-8")
                    )

                    self.cache[url] = data

                    return data

            except HTTPError as error:

                body = error.read().decode(
                    "utf-8",
                    errors="replace",
                )

                if (
                    error.code in (403, 429)
                    and attempt < 3
                ):

                    wait_seconds = 2 ** attempt

                    print(
                        f"Rate limited. "
                        f"Retrying in "
                        f"{wait_seconds}s..."
                    )

                    time.sleep(
                        wait_seconds
                    )

                    continue

                raise RuntimeError(
                    f"GitHub API error "
                    f"{error.code}: "
                    f"{body[:500]}"
                )

            except URLError as error:

                if attempt < 3:

                    time.sleep(
                        2 ** attempt
                    )

                    continue

                raise RuntimeError(
                    f"Network error: {error}"
                )

        raise RuntimeError(
            f"Failed request: {url}"
        )

    def paginate(
        self,
        path,
        params=None,
    ):
        """
        Fetch all pages from a GitHub endpoint.
        """

        params = dict(
            params or {}
        )

        params["per_page"] = 100

        results = []

        page = 1

        while True:

            params["page"] = page

            data = self.request(
                path,
                params,
            )

            if not isinstance(
                data,
                list,
            ):
                return data

            results.extend(data)

            if len(data) < 100:
                break

            page += 1

        return results


# ============================================================
# DATE HELPERS
# ============================================================

def get_analysis_period():
    """
    Return the start and end dates
    for the rolling analysis period.
    """

    end = datetime.now(
        timezone.utc
    )

    start = end - timedelta(
        days=ANALYSIS_DAYS
    )

    return start, end


def parse_github_date(value):
    """
    Convert GitHub ISO timestamp to datetime.
    """

    if not value:
        return None

    try:

        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:

        return None


def to_iso_datetime(value):
    """
    Convert datetime to GitHub-style ISO format.
    """

    return (
        value
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ============================================================
# JSON HELPERS
# ============================================================

def load_existing_data():
    """
    Load previously generated analytics data.

    Returns an empty structure if the file
    does not exist or is invalid.
    """

    if not os.path.exists(
        OUTPUT_FILE
    ):

        return {
            "schema_version": 2,
            "username": GITHUB_USERNAME,
            "updated_at": None,
            "current": None,
            "history": [],
        }

    try:

        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    except Exception:

        print(
            "Existing JSON could not be read. "
            "Starting fresh."
        )

        return {
            "schema_version": 2,
            "username": GITHUB_USERNAME,
            "updated_at": None,
            "current": None,
            "history": [],
        }


def save_data(data):
    """
    Save analytics data to JSON.
    """

    directory = os.path.dirname(
        OUTPUT_FILE
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True,
        )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# REPOSITORY DISCOVERY
# ============================================================

def get_user_repositories(
    github,
):
    """
    Get repositories accessible to
    the authenticated GitHub user.

    Includes:
    - Public repositories
    - Private repositories
    - Organization repositories
    - Collaborator repositories
    """

    print(
        "\nFetching repositories..."
    )

    repositories = github.paginate(
        "/user/repos",
        {
            "visibility": "all",
            "affiliation":
                "owner,collaborator,organization_member",
            "sort": "updated",
            "direction": "desc",
        },
    )

    print(
        f"Accessible repositories: "
        f"{len(repositories)}"
    )

    return repositories


# ============================================================
# COMMIT ANALYSIS
# ============================================================

def get_repository_commits(
    github,
    repository,
    start,
    end,
):
    """
    Get commits authored by the
    target user within the analysis period.
    """

    try:

        return github.paginate(
            f"/repos/{repository}/commits",
            {
                "author":
                    GITHUB_USERNAME,

                "since":
                    to_iso_datetime(start),

                "until":
                    to_iso_datetime(end),
            },
        )

    except Exception:

        return []


def get_commit_date(commit):
    """
    Extract the author's commit date.
    """

    value = (
        commit
        .get("commit", {})
        .get("author", {})
        .get("date")
    )

    return parse_github_date(
        value
    )


def build_daily_commit_activity(
    commits,
    repository,
):
    """
    Convert commits into daily activity.

    Example:

    {
        "2026-08-19": {
            "commits": 5,
            "repositories": ["repo-a"]
        }
    }
    """

    activity = defaultdict(
        lambda: {
            "commits": 0,
            "repositories": set(),
        }
    )

    for commit in commits:

        date = get_commit_date(
            commit
        )

        if not date:
            continue

        date_key = (
            date.date()
            .isoformat()
        )

        activity[
            date_key
        ]["commits"] += 1

        activity[
            date_key
        ]["repositories"].add(
            repository
        )

    return activity


# ============================================================
# LANGUAGE ANALYSIS
# ============================================================

def get_repository_languages(
    github,
    repository,
):
    """
    Get GitHub's language byte statistics.
    """

    try:

        languages = github.request(
            f"/repos/{repository}/languages"
        )

    except Exception:

        return Counter()

    result = Counter()

    for language, byte_count in (
        languages.items()
    ):

        normalized = (
            LANGUAGE_ALIASES.get(
                language,
                language,
            )
        )

        result[
            normalized
        ] += byte_count

    return result


# ============================================================
# REPOSITORY FILE ANALYSIS
# ============================================================

def get_repository_files(
    github,
    repository,
    branch,
):
    """
    Get all files in the repository tree.
    """

    try:

        data = github.request(
            f"/repos/{repository}/git/trees/{branch}",
            {
                "recursive": "1",
            },
        )

        return [
            item["path"]

            for item in data.get(
                "tree",
                [],
            )

            if item.get(
                "type"
            ) == "blob"
        ]

    except Exception as error:

        print(
            f"Could not inspect "
            f"{repository}: {error}"
        )

        return []


def read_repository_file(
    github,
    repository,
    path,
    branch,
):
    """
    Read a file from a repository.
    """

    try:

        data = github.request(
            f"/repos/{repository}/contents/{path}",
            {
                "ref": branch,
            },
        )

        return decode_github_file(
            data
        )

    except Exception:

        return None


def decode_github_file(data):
    """
    Decode GitHub's base64 file response.
    """

    if not isinstance(
        data,
        dict,
    ):

        return None

    if data.get(
        "encoding"
    ) != "base64":

        return None

    try:

        return base64.b64decode(
            data["content"]
        ).decode(
            "utf-8",
            errors="replace",
        )

    except Exception:

        return None


# ============================================================
# TECHNOLOGY DETECTION
# ============================================================

def detect_special_files(
    files,
):
    """
    Detect technologies based on
    repository configuration files.
    """

    technologies = Counter()

    normalized_files = {
        file.lower()
        for file in files
    }

    # Docker
    if any(
        PurePosixPath(file)
        .name
        .lower()
        .startswith("dockerfile")

        for file in files
    ):

        technologies[
            "Docker"
        ] += 1

    # GitHub Actions
    if any(
        file.startswith(
            ".github/workflows/"
        )

        for file in normalized_files
    ):

        technologies[
            "GitHub Actions"
        ] += 1

    special_files = {
        "tsconfig.json":
            "TypeScript",

        "vite.config.js":
            "Vite",

        "vite.config.ts":
            "Vite",

        "vite.config.mjs":
            "Vite",

        "next.config.js":
            "Next.js",

        "next.config.mjs":
            "Next.js",

        "next.config.ts":
            "Next.js",

        "tailwind.config.js":
            "Tailwind CSS",

        "tailwind.config.ts":
            "Tailwind CSS",
    }

    for filename, technology in (
        special_files.items()
    ):

        if filename in normalized_files:

            technologies[
                technology
            ] += 1

    return technologies


def detect_package_json(
    content,
):
    """
    Detect JavaScript/TypeScript
    technologies from package.json.
    """

    technologies = Counter()

    try:

        package = json.loads(
            content
        )

    except Exception:

        return technologies

    dependency_sections = [
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ]

    for section in dependency_sections:

        dependencies = package.get(
            section,
            {},
        )

        if not isinstance(
            dependencies,
            dict,
        ):

            continue

        for dependency in (
            dependencies
        ):

            technology = (
                PACKAGE_TO_TECHNOLOGY.get(
                    dependency.lower()
                )
            )

            if technology:

                technologies[
                    technology
                ] += 1

    detect_package_scripts(
        package,
        technologies,
    )

    return technologies


def detect_package_scripts(
    package,
    technologies,
):
    """
    Detect tooling from npm scripts.
    """

    scripts = package.get(
        "scripts",
        {},
    )

    if not isinstance(
        scripts,
        dict,
    ):

        return

    script_text = " ".join(
        str(value)
        for value in scripts.values()
    ).lower()

    script_tools = {
        "vite":
            "Vite",

        "webpack":
            "Webpack",

        "rollup":
            "Rollup",

        "eslint":
            "ESLint",

        "prettier":
            "Prettier",

        "jest":
            "Jest",

        "vitest":
            "Vitest",

        "playwright":
            "Playwright",

        "cypress":
            "Cypress",

        "tsc":
            "TypeScript",
    }

    for keyword, technology in (
        script_tools.items()
    ):

        if keyword in script_text:

            technologies[
                technology
            ] += 1


def detect_requirements(
    content,
):
    """
    Detect Python packages from
    requirements.txt.
    """

    technologies = Counter()

    for line in content.splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if line.startswith("-"):
            continue

        match = re.match(
            r"^([A-Za-z0-9_.-]+)",
            line,
        )

        if not match:
            continue

        package = (
            match.group(1)
            .lower()
        )

        technology = (
            PACKAGE_TO_TECHNOLOGY.get(
                package
            )
        )

        if technology:

            technologies[
                technology
            ] += 1

    return technologies


def detect_pyproject(
    content,
):
    """
    Detect Python packages from
    pyproject.toml.
    """

    technologies = Counter()

    lower_content = (
        content.lower()
    )

    for package, technology in (
        PACKAGE_TO_TECHNOLOGY.items()
    ):

        pattern = (
            rf'(?m)["\']?'
            rf'{re.escape(package.lower())}'
            rf'(?:\[[^\]]+\])?'
            rf'\s*(?:=|>|<|!|~|:)'
        )

        if re.search(
            pattern,
            lower_content,
        ):

            technologies[
                technology
            ] += 1

    return technologies


def detect_repository_technologies(
    github,
    repository,
    files,
    branch,
    languages,
):
    """
    Combine all technology detection
    strategies for a repository.
    """

    technologies = Counter()

    # Configuration files
    technologies.update(
        detect_special_files(
            files
        )
    )

    normalized_files = {
        file.lower()
        for file in files
    }

    # --------------------------------------------------------
    # package.json
    # --------------------------------------------------------

    package_path = next(
        (
            file
            for file in files

            if file.lower()
            == "package.json"
        ),
        None,
    )

    if package_path:

        content = read_repository_file(
            github,
            repository,
            package_path,
            branch,
        )

        if content:

            technologies.update(
                detect_package_json(
                    content
                )
            )

    # --------------------------------------------------------
    # requirements.txt
    # --------------------------------------------------------

    requirements_path = next(
        (
            file
            for file in files

            if file.lower()
            == "requirements.txt"
        ),
        None,
    )

    if requirements_path:

        content = read_repository_file(
            github,
            repository,
            requirements_path,
            branch,
        )

        if content:

            technologies.update(
                detect_requirements(
                    content
                )
            )

    # --------------------------------------------------------
    # pyproject.toml
    # --------------------------------------------------------

    pyproject_path = next(
        (
            file
            for file in files

            if file.lower()
            == "pyproject.toml"
        ),
        None,
    )

    if pyproject_path:

        content = read_repository_file(
            github,
            repository,
            pyproject_path,
            branch,
        )

        if content:

            technologies.update(
                detect_pyproject(
                    content
                )
            )

    # --------------------------------------------------------
    # Languages
    # --------------------------------------------------------

    for language in languages:

        technologies[
            language
        ] += 1

    return technologies


# ============================================================
# REPOSITORY ANALYSIS
# ============================================================

def analyze_repository(
    github,
    repository,
    start,
    end,
):
    """
    Analyze one repository.

    Returns None if the user
    has no commits during the period.
    """

    full_name = repository[
        "full_name"
    ]

    print(
        f"  Analyzing {full_name}"
    )

    # --------------------------------------------------------
    # Commits
    # --------------------------------------------------------

    commits = get_repository_commits(
        github,
        full_name,
        start,
        end,
    )

    if not commits:

        return None

    # --------------------------------------------------------
    # Languages
    # --------------------------------------------------------

    languages = get_repository_languages(
        github,
        full_name,
    )

    # --------------------------------------------------------
    # Files
    # --------------------------------------------------------

    branch = (
        repository.get(
            "default_branch"
        )
        or "main"
    )

    files = get_repository_files(
        github,
        full_name,
        branch,
    )

    # --------------------------------------------------------
    # Technologies
    # --------------------------------------------------------

    technologies = (
        detect_repository_technologies(
            github,
            full_name,
            files,
            branch,
            languages,
        )
    )

    # --------------------------------------------------------
    # Daily activity
    # --------------------------------------------------------

    daily_activity = (
        build_daily_commit_activity(
            commits,
            full_name,
        )
    )

    return {
        "name":
            repository.get(
                "name"
            ),

        "full_name":
            full_name,

        "url":
            repository.get(
                "html_url"
            ),

        "private":
            repository.get(
                "private",
                False,
            ),

        "fork":
            repository.get(
                "fork",
                False,
            ),

        "commits":
            len(commits),

        "languages":
            dict(
                languages.most_common()
            ),

        "technologies":
            sorted(
                technologies
            ),

        "daily_activity":
            convert_daily_activity(
                daily_activity
            ),
    }


# ============================================================
# DAILY ACTIVITY AGGREGATION
# ============================================================

def convert_daily_activity(
    activity,
):
    """
    Convert sets to JSON-compatible lists.
    """

    result = {}

    for date, stats in (
        activity.items()
    ):

        result[date] = {

            "commits":
                stats["commits"],

            "repositories":
                sorted(
                    stats[
                        "repositories"
                    ]
                ),
        }

    return result


def aggregate_daily_activity(
    repository_results,
):
    """
    Combine daily activity from all repositories.
    """

    daily = defaultdict(
        lambda: {
            "commits": 0,
            "repositories": set(),
            "private_repositories": set(),
            "public_repositories": set(),
        }
    )

    for repository in (
        repository_results
    ):

        repository_name = (
            repository[
                "full_name"
            ]
        )

        is_private = (
            repository[
                "private"
            ]
        )

        for date, activity in (
            repository[
                "daily_activity"
            ].items()
        ):

            daily[date][
                "commits"
            ] += activity[
                "commits"
            ]

            daily[date][
                "repositories"
            ].add(
                repository_name
            )

            if is_private:

                daily[date][
                    "private_repositories"
                ].add(
                    repository_name
                )

            else:

                daily[date][
                    "public_repositories"
                ].add(
                    repository_name
                )

    result = {}

    for date in sorted(
        daily
    ):

        stats = daily[
            date
        ]

        result[date] = {

            "commits":
                stats[
                    "commits"
                ],

            "repositories":
                sorted(
                    stats[
                        "repositories"
                    ]
                ),

            "repository_count":
                len(
                    stats[
                        "repositories"
                    ]
                ),

            "private_repository_count":
                len(
                    stats[
                        "private_repositories"
                    ]
                ),

            "public_repository_count":
                len(
                    stats[
                        "public_repositories"
                    ]
                ),
        }

    return result


# ============================================================
# GLOBAL AGGREGATION
# ============================================================

def aggregate_languages(
    repository_results,
):
    """
    Combine GitHub language statistics
    across active repositories.
    """

    languages = Counter()

    for repository in (
        repository_results
    ):

        languages.update(
            repository[
                "languages"
            ]
        )

    return languages


def aggregate_technologies(
    repository_results,
):
    """
    Count technologies by number
    of repositories using them.
    """

    technology_repositories = defaultdict(
        set
    )

    for repository in (
        repository_results
    ):

        for technology in (
            repository[
                "technologies"
            ]
        ):

            technology_repositories[
                technology
            ].add(
                repository[
                    "full_name"
                ]
            )

    result = []

    sorted_technologies = sorted(
        technology_repositories.items(),
        key=lambda item:
            len(item[1]),
        reverse=True,
    )

    for technology, repositories in (
        sorted_technologies
    ):

        result.append({

            "technology":
                technology,

            "repository_count":
                len(repositories),

            "repositories":
                sorted(
                    repositories
                ),
        })

    return result


def calculate_percentage(
    counter,
):
    """
    Convert a Counter into percentages.
    """

    total = sum(
        counter.values()
    )

    if total == 0:

        return {}

    return {

        key:
            round(
                value / total * 100,
                2,
            )

        for key, value
        in counter.most_common()
    }


# ============================================================
# SNAPSHOT CREATION
# ============================================================

def build_snapshot(
    start,
    end,
    accessible_repositories,
    repository_results,
):
    """
    Build the rolling 12-month snapshot.
    """

    languages = aggregate_languages(
        repository_results
    )

    technologies = aggregate_technologies(
        repository_results
    )

    daily_activity = aggregate_daily_activity(
        repository_results
    )

    private_repositories = sum(
        1
        for repository
        in repository_results

        if repository[
            "private"
        ]
    )

    public_repositories = sum(
        1
        for repository
        in repository_results

        if not repository[
            "private"
        ]
    )

    total_commits = sum(
        repository[
            "commits"
        ]

        for repository
        in repository_results
    )

    return {

        "date":
            end.date().isoformat(),

        "period": {

            "from":
                start.date().isoformat(),

            "to":
                end.date().isoformat(),
        },

        "summary": {

            "accessible_repositories":
                len(
                    accessible_repositories
                ),

            "active_repositories":
                len(
                    repository_results
                ),

            "private_active_repositories":
                private_repositories,

            "public_active_repositories":
                public_repositories,

            "commits":
                total_commits,

            "active_days":
                len(
                    daily_activity
                ),
        },

        "languages": {

            "bytes":
                dict(
                    languages.most_common()
                ),

            "percentage":
                calculate_percentage(
                    languages
                ),
        },

        "technologies":
            technologies,

        "repositories":
            sorted(
                repository_results,
                key=lambda repository:
                    repository[
                        "commits"
                    ],
                reverse=True,
            ),

        "daily_activity":
            daily_activity,
    }


# ============================================================
# HISTORY MANAGEMENT
# ============================================================

def update_history(
    data,
    snapshot,
):
    """
    Add today's snapshot to history.

    If today's snapshot already exists,
    replace it instead of duplicating it.
    """

    history = data.get(
        "history",
        []
    )

    snapshot_date = snapshot[
        "date"
    ]

    history = [
        item

        for item in history

        if item.get(
            "date"
        ) != snapshot_date
    ]

    history.append(
        snapshot
    )

    history.sort(
        key=lambda item:
            item.get(
                "date",
                "",
            )
    )

    data[
        "history"
    ] = history

    return data


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_analysis():
    """
    Main analytics pipeline.
    """

    if not GITHUB_TOKEN:

        raise RuntimeError(
            "GITHUB_TOKEN is not set."
        )

    start, end = (
        get_analysis_period()
    )

    print(
        f"\nAnalyzing @{GITHUB_USERNAME}"
    )

    print(
        f"Period: "
        f"{start.date()} → "
        f"{end.date()}"
    )

    github = GitHubClient(
        GITHUB_TOKEN
    )

    # --------------------------------------------------------
    # 1. Repository discovery
    # --------------------------------------------------------

    repositories = (
        get_user_repositories(
            github
        )
    )

    # --------------------------------------------------------
    # 2. Repository analysis
    # --------------------------------------------------------

    active_repositories = []

    for index, repository in enumerate(
        repositories,
        start=1,
    ):

        print(
            f"\n[{index}/{len(repositories)}] "
            f"{repository['full_name']}"
        )

        result = analyze_repository(
            github,
            repository,
            start,
            end,
        )

        if result:

            active_repositories.append(
                result
            )

    # --------------------------------------------------------
    # 3. Build snapshot
    # --------------------------------------------------------

    snapshot = build_snapshot(
        start,
        end,
        repositories,
        active_repositories,
    )

    # --------------------------------------------------------
    # 4. Load existing data
    # --------------------------------------------------------

    data = load_existing_data()

    data[
        "schema_version"
    ] = 2

    data[
        "username"
    ] = GITHUB_USERNAME

    data[
        "updated_at"
    ] = to_iso_datetime(end)

    # Latest rolling snapshot
    data[
        "current"
    ] = snapshot

    # --------------------------------------------------------
    # 5. Update history
    # --------------------------------------------------------

    data = update_history(
        data,
        snapshot,
    )

    # --------------------------------------------------------
    # 6. Save
    # --------------------------------------------------------

    save_data(
        data
    )

    return snapshot, data


# ============================================================
# CLI
# ============================================================

def print_summary(
    snapshot,
    data,
):
    """
    Print a concise GitHub Actions summary.
    """

    summary = snapshot[
        "summary"
    ]

    print(
        "\n"
        + "=" * 60
    )

    print(
        "GITHUB TECH STACK ANALYSIS COMPLETE"
    )

    print(
        "=" * 60
    )

    print(
        f"Active repositories : "
        f"{summary['active_repositories']}"
    )

    print(
        f"Private repositories: "
        f"{summary['private_active_repositories']}"
    )

    print(
        f"Public repositories : "
        f"{summary['public_active_repositories']}"
    )

    print(
        f"Commits             : "
        f"{summary['commits']}"
    )

    print(
        f"Active days         : "
        f"{summary['active_days']}"
    )

    print(
        f"History snapshots   : "
        f"{len(data['history'])}"
    )

    print(
        f"\nOutput: {OUTPUT_FILE}"
    )

    print(
        "=" * 60
    )


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    try:

        snapshot, data = (
            run_analysis()
        )

        print_summary(
            snapshot,
            data,
        )

    except KeyboardInterrupt:

        print(
            "\nAnalysis stopped."
        )

        sys.exit(130)

    except Exception as error:

        print(
            f"\nERROR: {error}",
            file=sys.stderr,
        )

        sys.exit(1)


if __name__ == "__main__":

    main()