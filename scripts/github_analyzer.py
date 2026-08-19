#!/usr/bin/env python3

"""
GitHub Engineering Analytics

Collects GitHub activity and converts it into a compact,
UI-friendly JSON dataset.

The script intentionally does NOT store:
- Full commit objects
- Full repository metadata
- Repository file trees
- Dependency lists
- Large raw GitHub responses

It stores only aggregated information useful for a personal
engineering dashboard.

Environment variables:
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
    "GITHUB_TOKEN",
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

    # AI
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
    - authentication
    - pagination
    - rate limiting
    - response caching
    """

    def __init__(self, token):

        self.token = token
        self.cache = {}

    def request(
        self,
        path,
        params=None,
    ):
        """
        Make a GET request to GitHub.
        """

        url = (
            path
            if path.startswith("http")
            else GITHUB_API + path
        )

        if params:

            query = urlencode(
                params
            )

            separator = (
                "&"
                if "?" in url
                else "?"
            )

            url += (
                separator + query
            )

        if url in self.cache:

            return self.cache[url]

        headers = {

            "Accept":
                "application/vnd.github+json",

            "Authorization":
                f"Bearer {self.token}",

            "X-GitHub-Api-Version":
                "2022-11-28",

            "User-Agent":
                "yuvrajkarna-github-analytics",
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
                        .decode(
                            "utf-8"
                        )
                    )

                    self.cache[
                        url
                    ] = data

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

                    wait = 2 ** attempt

                    print(
                        f"Rate limited. "
                        f"Retrying in {wait}s..."
                    )

                    time.sleep(
                        wait
                    )

                    continue

                raise RuntimeError(
                    f"GitHub API "
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
                    f"Network error: "
                    f"{error}"
                )

        raise RuntimeError(
            f"Request failed: {url}"
        )

    def paginate(
        self,
        path,
        params=None,
    ):
        """
        Fetch all pages from an API endpoint.
        """

        params = dict(
            params or {}
        )

        params[
            "per_page"
        ] = 100

        results = []

        page = 1

        while True:

            params[
                "page"
            ] = page

            data = self.request(
                path,
                params,
            )

            if not isinstance(
                data,
                list,
            ):

                return data

            results.extend(
                data
            )

            if len(data) < 100:

                break

            page += 1

        return results


# ============================================================
# DATE HELPERS
# ============================================================

def get_analysis_period():
    """
    Return the rolling 365-day period.
    """

    end = datetime.now(
        timezone.utc
    )

    start = (
        end
        - timedelta(
            days=ANALYSIS_DAYS
        )
    )

    return start, end


def parse_github_date(
    value,
):
    """
    Convert GitHub timestamp
    into a datetime.
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


def to_iso_datetime(
    value,
):
    """
    Convert datetime to ISO format.
    """

    return (
        value
        .astimezone(
            timezone.utc
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


# ============================================================
# FILE HELPERS
# ============================================================

def decode_github_file(
    data,
):
    """
    Decode a GitHub base64 file response.
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


def get_repository_files(
    github,
    repository,
    branch,
):
    """
    Get repository file names.

    These are used only during analysis.
    They are NOT stored in the output JSON.
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
    Read a repository file.
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


# ============================================================
# REPOSITORY DISCOVERY
# ============================================================

def get_user_repositories(
    github,
):
    """
    Get all repositories accessible
    to the authenticated user.

    Includes:
    - public repositories
    - private repositories
    - organization repositories
    - collaborator repositories
    """

    print(
        "\nFetching repositories..."
    )

    repositories = github.paginate(
        "/user/repos",
        {
            "visibility":
                "all",

            "affiliation":
                "owner,collaborator,organization_member",

            "sort":
                "updated",

            "direction":
                "desc",
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
    Get commits authored by the user
    during the analysis period.
    """

    try:

        return github.paginate(
            f"/repos/{repository}/commits",
            {
                "author":
                    GITHUB_USERNAME,

                "since":
                    to_iso_datetime(
                        start
                    ),

                "until":
                    to_iso_datetime(
                        end
                    ),
            },
        )

    except Exception:

        return []


def get_commit_date(
    commit,
):
    """
    Extract commit author date.
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


def extract_daily_commits(
    commits,
):
    """
    Convert commits into:

    {
        "2026-08-19": 5
    }
    """

    daily = Counter()

    for commit in commits:

        date = get_commit_date(
            commit
        )

        if not date:

            continue

        date_key = (
            date
            .date()
            .isoformat()
        )

        daily[
            date_key
        ] += 1

    return daily


# ============================================================
# LANGUAGE ANALYSIS
# ============================================================

def get_repository_languages(
    github,
    repository,
):
    """
    Get language byte counts
    from GitHub.
    """

    try:

        data = github.request(
            f"/repos/{repository}/languages"
        )

    except Exception:

        return Counter()

    languages = Counter()

    for language, bytes_count in (
        data.items()
    ):

        normalized = (
            LANGUAGE_ALIASES.get(
                language,
                language,
            )
        )

        languages[
            normalized
        ] += bytes_count

    return languages


def aggregate_languages(
    repositories,
):
    """
    Aggregate language bytes
    across repositories.
    """

    languages = Counter()

    for repository in repositories:

        languages.update(
            repository[
                "languages"
            ]
        )

    return languages


def calculate_percentages(
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
# TECHNOLOGY DETECTION
# ============================================================

def detect_special_files(
    files,
):
    """
    Detect technologies from
    configuration files.
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
        .startswith(
            "dockerfile"
        )

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

    configuration_files = {

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
        configuration_files.items()
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
    Detect JS/TS technologies
    from package.json.
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

    for section in (
        dependency_sections
    ):

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
    Detect development tools
    from npm scripts.
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

    tools = {

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
        tools.items()
    ):

        if keyword in script_text:

            technologies[
                technology
            ] += 1


def detect_requirements(
    content,
):
    """
    Detect Python technologies
    from requirements.txt.
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
    Detect Python technologies
    from pyproject.toml.
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
    Detect all technologies used
    by a repository.
    """

    technologies = Counter()

    # --------------------------------------------------------
    # Configuration files
    # --------------------------------------------------------

    technologies.update(
        detect_special_files(
            files
        )
    )

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
# TECHNOLOGY AGGREGATION
# ============================================================

def aggregate_technologies(
    repositories,
):
    """
    Calculate technology usage.

    Percentage means:

        repositories using technology
        --------------------------------
        total active repositories

    This is intentionally NOT presented
    as percentage of coding time.
    """

    technology_repositories = defaultdict(
        set
    )

    for repository in repositories:

        for technology in (
            repository[
                "technologies"
            ]
        ):

            technology_repositories[
                technology
            ].add(
                repository[
                    "name"
                ]
            )

    total_repositories = len(
        repositories
    )

    result = []

    for technology, repository_set in sorted(
        technology_repositories.items(),
        key=lambda item:
            len(item[1]),
        reverse=True,
    ):

        repository_count = len(
            repository_set
        )

        percentage = 0

        if total_repositories:

            percentage = round(
                repository_count
                / total_repositories
                * 100,
                2,
            )

        result.append({

            "technology":
                technology,

            "repositories":
                repository_count,

            "percentage":
                percentage,
        })

    return result


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

    Only compact information is returned.
    """

    full_name = repository[
        "full_name"
    ]

    commits = get_repository_commits(
        github,
        full_name,
        start,
        end,
    )

    if not commits:

        return None

    print(
        f"  Active: {full_name} "
        f"({len(commits)} commits)"
    )

    languages = (
        get_repository_languages(
            github,
            full_name,
        )
    )

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

    technologies = (
        detect_repository_technologies(
            github,
            full_name,
            files,
            branch,
            languages,
        )
    )

    daily_commits = (
        extract_daily_commits(
            commits
        )
    )

    return {

        "name":
            repository.get(
                "name"
            ),

        "commits":
            len(commits),

        "private":
            bool(
                repository.get(
                    "private",
                    False,
                )
            ),

        "languages":
            dict(
                languages
            ),

        "technologies":
            sorted(
                technologies
            ),

        "daily_commits":
            dict(
                daily_commits
            ),
    }


# ============================================================
# DAILY ACTIVITY AGGREGATION
# ============================================================

def aggregate_daily_activity(
    repositories,
):
    """
    Aggregate commits by day.

    Output remains intentionally tiny.
    """

    daily = Counter()

    for repository in repositories:

        for date, commits in (
            repository[
                "daily_commits"
            ].items()
        ):

            daily[
                date
            ] += commits

    return dict(
        sorted(
            daily.items()
        )
    )


# ============================================================
# ACTIVE REPOSITORY SUMMARY
# ============================================================

def build_repository_summary(
    repositories,
):
    """
    Return only the most useful
    repository-level information.
    """

    result = []

    for repository in repositories:

        result.append({

            "name":
                repository[
                    "name"
                ],

            "commits":
                repository[
                    "commits"
                ],

            "private":
                repository[
                    "private"
                ],
        })

    result.sort(
        key=lambda repository:
            repository[
                "commits"
            ],
        reverse=True,
    )

    return result


# ============================================================
# SNAPSHOT
# ============================================================

def build_snapshot(
    start,
    end,
    accessible_repositories,
    active_repositories,
):
    """
    Build compact rolling 12-month analytics.
    """

    languages = aggregate_languages(
        active_repositories
    )

    technologies = (
        aggregate_technologies(
            active_repositories
        )
    )

    daily_activity = (
        aggregate_daily_activity(
            active_repositories
        )
    )

    total_commits = sum(
        repository[
            "commits"
        ]

        for repository
        in active_repositories
    )

    private_count = sum(
        1

        for repository
        in active_repositories

        if repository[
            "private"
        ]
    )

    public_count = (
        len(active_repositories)
        - private_count
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
                    active_repositories
                ),

            "private_repositories":
                private_count,

            "public_repositories":
                public_count,

            "commits":
                total_commits,

            "active_days":
                len(
                    daily_activity
                ),
        },

        # ----------------------------------------------------
        # Languages
        # ----------------------------------------------------

        "languages": {

            "percentage":
                calculate_percentages(
                    languages
                ),
        },

        # ----------------------------------------------------
        # Technologies
        # ----------------------------------------------------

        "technologies":
            technologies,

        # ----------------------------------------------------
        # Top projects
        # ----------------------------------------------------

        "repositories":
            build_repository_summary(
                active_repositories
            ),

        # ----------------------------------------------------
        # Daily activity
        # ----------------------------------------------------

        "daily_activity":
            daily_activity,
    }


# ============================================================
# HISTORY
# ============================================================

def load_existing_data():
    """
    Load existing analytics history.
    """

    if not os.path.exists(
        OUTPUT_FILE
    ):

        return {

            "schema_version": 3,

            "username":
                GITHUB_USERNAME,

            "updated_at":
                None,

            "current":
                None,

            "history":
                [],
        }

    try:

        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(
                file
            )

    except Exception:

        return {

            "schema_version": 3,

            "username":
                GITHUB_USERNAME,

            "updated_at":
                None,

            "current":
                None,

            "history":
                [],
        }


def update_history(
    data,
    snapshot,
):
    """
    Add today's compact snapshot.

    Existing snapshot for the same date
    is replaced.
    """

    history = data.get(
        "history",
        []
    )

    today = snapshot[
        "date"
    ]

    history = [

        item

        for item in history

        if item.get(
            "date"
        ) != today
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


def save_data(
    data,
):
    """
    Persist compact analytics JSON.
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
# MAIN PIPELINE
# ============================================================

def run():
    """
    Run the complete analytics pipeline.
    """

    if not GITHUB_TOKEN:

        raise RuntimeError(
            "GITHUB_TOKEN is missing."
        )

    start, end = (
        get_analysis_period()
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "GitHub Engineering Analytics"
    )

    print(
        f"User: @{GITHUB_USERNAME}"
    )

    print(
        f"Period: "
        f"{start.date()} → "
        f"{end.date()}"
    )

    print(
        "=" * 60
    )

    github = GitHubClient(
        GITHUB_TOKEN
    )

    # --------------------------------------------------------
    # 1. Discover repositories
    # --------------------------------------------------------

    repositories = (
        get_user_repositories(
            github
        )
    )

    # --------------------------------------------------------
    # 2. Analyze active repositories
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
    # 3. Build compact snapshot
    # --------------------------------------------------------

    snapshot = build_snapshot(
        start,
        end,
        repositories,
        active_repositories,
    )

    # --------------------------------------------------------
    # 4. Load existing history
    # --------------------------------------------------------

    data = load_existing_data()

    data[
        "schema_version"
    ] = 3

    data[
        "username"
    ] = GITHUB_USERNAME

    data[
        "updated_at"
    ] = to_iso_datetime(
        end
    )

    data[
        "current"
    ] = snapshot

    # --------------------------------------------------------
    # 5. Update daily history
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
# OUTPUT
# ============================================================

def print_summary(
    snapshot,
    data,
):
    """
    Print useful information to
    GitHub Actions logs.
    """

    summary = snapshot[
        "summary"
    ]

    print(
        "\n"
        + "=" * 60
    )

    print(
        "ANALYSIS COMPLETE"
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
        f"{summary['private_repositories']}"
    )

    print(
        f"Public repositories : "
        f"{summary['public_repositories']}"
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
        f"\nSaved: {OUTPUT_FILE}"
    )

    print(
        "=" * 60
    )


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    try:

        snapshot, data = run()

        print_summary(
            snapshot,
            data,
        )

    except KeyboardInterrupt:

        print(
            "\nStopped."
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