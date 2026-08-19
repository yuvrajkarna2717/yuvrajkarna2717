#!/usr/bin/env python3

"""
GitHub Engineering Analytics

Sources:
    1. GitHub GraphQL
       - contribution calendar
       - total contributions
       - commit contributions
       - restricted/private contribution count

    2. GitHub REST
       - repositories accessible to the token
       - languages
       - technology detection

Private organization repositories do NOT need to be accessible
to the token for private contribution counts to work.

The output is intentionally compact and UI-friendly.

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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL_API = "https://api.github.com/graphql"

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

    # JavaScript / TypeScript
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

    # Development tools
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
# HTTP HELPERS
# ============================================================

def make_headers(token):
    """
    Create common GitHub API headers.
    """

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "yuvrajkarna-github-analytics",
    }


def make_request(
    url,
    headers,
    body=None,
):
    """
    Perform an HTTP request with retries.
    """

    for attempt in range(4):

        try:

            request = Request(
                url,
                headers=headers,
                data=body,
                method="POST" if body else "GET",
            )

            with urlopen(
                request,
                timeout=30,
            ) as response:

                return json.loads(
                    response
                    .read()
                    .decode("utf-8")
                )

        except HTTPError as error:

            response_body = error.read().decode(
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

                time.sleep(wait)

                continue

            raise RuntimeError(
                f"GitHub API "
                f"{error.code}: "
                f"{response_body[:500]}"
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
        f"Request failed: {url}"
    )


# ============================================================
# REST CLIENT
# ============================================================

class GitHubRESTClient:
    """
    GitHub REST API client.
    """

    def __init__(self, token):

        self.token = token
        self.headers = make_headers(token)
        self.cache = {}

    def get(
        self,
        path,
        params=None,
    ):
        """
        GET request with caching.
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

        data = make_request(
            url,
            self.headers,
        )

        self.cache[
            url
        ] = data

        return data

    def paginate(
        self,
        path,
        params=None,
    ):
        """
        Fetch all pages.
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

            data = self.get(
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
# GRAPHQL CLIENT
# ============================================================

class GitHubGraphQLClient:
    """
    GitHub GraphQL API client.
    """

    def __init__(self, token):

        self.token = token

        self.headers = {
            **make_headers(token),
            "Content-Type":
                "application/json",
        }

    def query(
        self,
        query,
        variables=None,
    ):
        """
        Execute a GraphQL query.
        """

        payload = json.dumps({
            "query": query,
            "variables": variables or {},
        }).encode(
            "utf-8"
        )

        response = make_request(
            GITHUB_GRAPHQL_API,
            self.headers,
            body=payload,
        )

        if response.get(
            "errors"
        ):

            errors = response[
                "errors"
            ]

            messages = [
                error.get(
                    "message",
                    "Unknown GraphQL error",
                )
                for error in errors
            ]

            raise RuntimeError(
                "GraphQL error: "
                + "; ".join(messages)
            )

        return response.get(
            "data",
            {}
        )


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
    Convert GitHub date into datetime.
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
    Convert datetime into ISO format.
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
# GRAPHQL CONTRIBUTION ANALYSIS
# ============================================================

CONTRIBUTION_QUERY = """
query ContributionStats(
    $login: String!,
    $from: DateTime!,
    $to: DateTime!
) {
    user(login: $login) {
        login

        contributionsCollection(
            from: $from,
            to: $to
        ) {
            startedAt
            endedAt

            totalCommitContributions

            totalIssueContributions

            totalPullRequestContributions

            totalPullRequestReviewContributions

            totalRepositoriesWithContributedCommits

            restrictedContributionsCount

            contributionCalendar {
                totalContributions

                weeks {
                    contributionDays {
                        date
                        contributionCount
                        contributionLevel
                    }
                }
            }
        }
    }
}
"""


def get_contribution_stats(
    graphql,
    start,
    end,
):
    """
    Get contribution statistics from GitHub GraphQL.

    This is the important part for private contributions.

    GitHub can return restricted/private contribution counts
    without giving this token access to the private repository
    contents.
    """

    print(
        "\nFetching contribution data..."
    )

    data = graphql.query(
        CONTRIBUTION_QUERY,
        {
            "login":
                GITHUB_USERNAME,

            "from":
                to_iso_datetime(
                    start
                ),

            "to":
                to_iso_datetime(
                    end
                ),
        },
    )

    user = data.get(
        "user"
    )

    if not user:

        raise RuntimeError(
            "GitHub user could not be found."
        )

    collection = user[
        "contributionsCollection"
    ]

    calendar = collection[
        "contributionCalendar"
    ]

    daily_activity = {}

    for week in calendar[
        "weeks"
    ]:

        for day in week[
            "contributionDays"
        ]:

            daily_activity[
                day["date"]
            ] = day[
                "contributionCount"
            ]

    return {

        "commits":
            collection[
                "totalCommitContributions"
            ],

        "issues":
            collection[
                "totalIssueContributions"
            ],

        "pull_requests":
            collection[
                "totalPullRequestContributions"
            ],

        "pull_request_reviews":
            collection[
                "totalPullRequestReviewContributions"
            ],

        "repositories_with_commits":
            collection[
                "totalRepositoriesWithContributedCommits"
            ],

        "total_contributions":
            calendar[
                "totalContributions"
            ],

        "restricted_contributions":
            collection[
                "restrictedContributionsCount"
            ],

        "daily_activity":
            daily_activity,
    }


# ============================================================
# REST REPOSITORY DISCOVERY
# ============================================================

def get_accessible_repositories(
    github,
):
    """
    Get repositories this token is actually
    authorized to inspect.

    This does NOT attempt to bypass organization
    permissions.
    """

    print(
        "\nFetching accessible repositories..."
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
# REPOSITORY FILE HELPERS
# ============================================================

def decode_github_file(
    data,
):
    """
    Decode GitHub base64 file content.
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
    Get repository files.

    These are used for technology detection
    but are never stored in the final JSON.
    """

    try:

        data = github.get(
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
    Read one repository file.
    """

    try:

        data = github.get(
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
# LANGUAGE ANALYSIS
# ============================================================

def get_repository_languages(
    github,
    repository,
):
    """
    Get language byte counts.
    """

    try:

        data = github.get(
            f"/repos/{repository}/languages"
        )

    except Exception:

        return Counter()

    languages = Counter()

    for language, bytes_count in (
        data.items()
    ):

        language = (
            LANGUAGE_ALIASES.get(
                language,
                language,
            )
        )

        languages[
            language
        ] += bytes_count

    return languages


def aggregate_languages(
    repositories,
):
    """
    Aggregate language bytes.
    """

    languages = Counter()

    for repository in (
        repositories
    ):

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
    Convert Counter to percentages.
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

    normalized = {
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

        for file in normalized
    ):

        technologies[
            "GitHub Actions"
        ] += 1

    config_files = {

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
        config_files.items()
    ):

        if filename in normalized:

            technologies[
                technology
            ] += 1

    return technologies


def detect_package_json(
    content,
):
    """
    Detect JavaScript technologies
    from package.json.
    """

    technologies = Counter()

    try:

        package = json.loads(
            content
        )

    except Exception:

        return technologies

    sections = [
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ]

    for section in sections:

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

    return technologies


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

        if (
            not line
            or line.startswith("#")
            or line.startswith("-")
        ):

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
    Detect technologies used by a repository.
    """

    technologies = Counter()

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

    # Languages are also technologies.
    for language in languages:

        technologies[
            language
        ] += 1

    return technologies


# ============================================================
# AUTHORIZED REPOSITORY ANALYSIS
# ============================================================

def analyze_repository(
    github,
    repository,
    start,
    end,
):
    """
    Analyze only a repository the token
    is authorized to access.

    This is separate from private contribution
    statistics obtained from GraphQL.
    """

    full_name = repository[
        "full_name"
    ]

    # --------------------------------------------------------
    # Get user's commits
    # --------------------------------------------------------

    try:

        commits = github.paginate(
            f"/repos/{full_name}/commits",
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

        commits = []

    if not commits:

        return None

    print(
        f"  Active repository: "
        f"{full_name}"
    )

    # --------------------------------------------------------
    # Languages
    # --------------------------------------------------------

    languages = (
        get_repository_languages(
            github,
            full_name,
        )
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
            dict(languages),

        "technologies":
            sorted(
                technologies
            ),
    }


# ============================================================
# TECHNOLOGY AGGREGATION
# ============================================================

def aggregate_technologies(
    repositories,
):
    """
    Calculate technology adoption across
    authorized repositories.

    Percentage means:

        repositories using technology
        ------------------------------
        active repositories

    It does NOT represent coding time.
    """

    technology_repositories = {}

    total_repositories = len(
        repositories
    )

    for repository in repositories:

        for technology in (
            repository[
                "technologies"
            ]
        ):

            technology_repositories.setdefault(
                technology,
                set(),
            ).add(
                repository[
                    "name"
                ]
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
# REPOSITORY SUMMARY
# ============================================================

def build_repository_summary(
    repositories,
):
    """
    Store only useful repository statistics.
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
        key=lambda item:
            item["commits"],
        reverse=True,
    )

    return result


# ============================================================
# SNAPSHOT
# ============================================================

def build_snapshot(
    start,
    end,
    contribution_stats,
    accessible_repositories,
    analyzed_repositories,
):
    """
    Build compact dashboard data.
    """

    languages = aggregate_languages(
        analyzed_repositories
    )

    technologies = aggregate_technologies(
        analyzed_repositories
    )

    private_authorized = sum(
        1
        for repository
        in analyzed_repositories

        if repository[
            "private"
        ]
    )

    public_authorized = (
        len(analyzed_repositories)
        - private_authorized
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

        # ----------------------------------------------------
        # Complete GitHub contribution activity
        # ----------------------------------------------------

        "activity": {

            "commits":
                contribution_stats[
                    "commits"
                ],

            "issues":
                contribution_stats[
                    "issues"
                ],

            "pull_requests":
                contribution_stats[
                    "pull_requests"
                ],

            "pull_request_reviews":
                contribution_stats[
                    "pull_request_reviews"
                ],

            "total_contributions":
                contribution_stats[
                    "total_contributions"
                ],

            "restricted_contributions":
                contribution_stats[
                    "restricted_contributions"
                ],

            "repositories_with_commits":
                contribution_stats[
                    "repositories_with_commits"
                ],
        },

        # ----------------------------------------------------
        # Repository access
        # ----------------------------------------------------

        "repositories": {

            "accessible":
                len(
                    accessible_repositories
                ),

            "analyzed":
                len(
                    analyzed_repositories
                ),

            "private_analyzed":
                private_authorized,

            "public_analyzed":
                public_authorized,

            "top":
                build_repository_summary(
                    analyzed_repositories
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
        # Daily GitHub contributions
        # ----------------------------------------------------

        "daily_activity":
            contribution_stats[
                "daily_activity"
            ],
    }


def save_data(data):
    """
    Write the latest analytics snapshot.
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
    Execute the complete analytics pipeline.
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

    # --------------------------------------------------------
    # Clients
    # --------------------------------------------------------

    rest = GitHubRESTClient(
        GITHUB_TOKEN
    )

    graphql = GitHubGraphQLClient(
        GITHUB_TOKEN
    )

    # --------------------------------------------------------
    # 1. COMPLETE CONTRIBUTION DATA
    # --------------------------------------------------------

    contribution_stats = (
        get_contribution_stats(
            graphql,
            start,
            end,
        )
    )

    print(
        f"Total contributions: "
        f"{contribution_stats['total_contributions']}"
    )

    print(
        f"Commit contributions: "
        f"{contribution_stats['commits']}"
    )

    print(
        f"Restricted contributions: "
        f"{contribution_stats['restricted_contributions']}"
    )

    # --------------------------------------------------------
    # 2. AUTHORIZED REPOSITORIES
    # --------------------------------------------------------

    accessible_repositories = (
        get_accessible_repositories(
            rest
        )
    )

    # --------------------------------------------------------
    # 3. TECHNOLOGY ANALYSIS
    # --------------------------------------------------------

    analyzed_repositories = []

    for index, repository in enumerate(
        accessible_repositories,
        start=1,
    ):

        print(
            f"\n[{index}/"
            f"{len(accessible_repositories)}]"
        )

        result = analyze_repository(
            rest,
            repository,
            start,
            end,
        )

        if result:

            analyzed_repositories.append(
                result
            )

    # --------------------------------------------------------
    # 4. BUILD SNAPSHOT
    # --------------------------------------------------------

    snapshot = build_snapshot(
        start,
        end,
        contribution_stats,
        accessible_repositories,
        analyzed_repositories,
    )

    # --------------------------------------------------------
    # 5. LOAD EXISTING DATA
    # --------------------------------------------------------


    data = {
        "schema_version": 4,
        "username": GITHUB_USERNAME,
        "updated_at": to_iso_datetime(end),
        **snapshot,
    }

    # --------------------------------------------------------
    # 6. SAVE
    # --------------------------------------------------------

    save_data(
        data
    )

    return snapshot, data


# ============================================================
# SUMMARY
# ============================================================

def print_summary(data):

    activity = data[
        "activity"
    ]

    repositories = data[
        "repositories"
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
        f"Total contributions : "
        f"{activity['total_contributions']}"
    )

    print(
        f"Commit contributions: "
        f"{activity['commits']}"
    )

    print(
        f"Restricted/private   : "
        f"{activity['restricted_contributions']}"
    )

    print(
        f"Accessible repos     : "
        f"{repositories['accessible']}"
    )

    print(
        f"Analyzed repos       : "
        f"{repositories['analyzed']}"
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

        data = run()

        print_summary(
            data
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