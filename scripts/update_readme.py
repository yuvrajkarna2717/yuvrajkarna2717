#!/usr/bin/env python3

"""
Generate the GitHub statistics section in README.md
from data/github-stats.json.

Only the section between:

    <!-- GITHUB_STATS_START -->
    <!-- GITHUB_STATS_END -->

is modified.
"""

import json
from pathlib import Path


README_FILE = Path("README.md")
DATA_FILE = Path("data/github-stats.json")

START_MARKER = "<!-- GITHUB_STATS_START -->"
END_MARKER = "<!-- GITHUB_STATS_END -->"

MAX_LANGUAGES = 6
MAX_TECHNOLOGIES = 8
MAX_REPOSITORIES = 5


# ============================================================
# DATA
# ============================================================

def load_stats():
    """Load the latest GitHub statistics."""

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Statistics file not found: {DATA_FILE}"
        )

    with DATA_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


# ============================================================
# FORMATTING
# ============================================================

def make_bar(percentage, width=20):
    """Create a simple text progress bar."""

    filled = round(
        percentage / 100 * width
    )

    filled = max(
        0,
        min(
            width,
            filled,
        ),
    )

    return (
        "█" * filled
        + "░" * (width - filled)
    )


def format_number(value):
    """Format large numbers."""

    return f"{value:,}"


def format_percentage(value):
    """Format percentage."""

    return f"{value:.1f}%"


# ============================================================
# SECTIONS
# ============================================================

def build_activity_section(stats):
    """Build the activity summary."""

    activity = stats.get(
        "activity",
        {},
    )

    repositories = stats.get(
        "repositories",
        {},
    )

    commits = activity.get(
        "commits",
        0,
    )

    contributions = activity.get(
        "total_contributions",
        0,
    )

    active_days = sum(
        1
        for count in stats.get(
            "daily_activity",
            {},
        ).values()
        if count > 0
    )

    projects = repositories.get(
        "analyzed",
        0,
    )

    return f"""
<div align="center">

### 📊 Engineering Activity

<table>
<tr>
<td align="center">
<h3>{format_number(commits)}</h3>
commits
</td>

<td align="center">
<h3>{format_number(contributions)}</h3>
contributions
</td>

<td align="center">
<h3>{format_number(active_days)}</h3>
active days
</td>

<td align="center">
<h3>{format_number(projects)}</h3>
projects
</td>
</tr>
</table>

</div>
""".strip()


def build_languages_section(stats):
    """Build language statistics."""

    languages = (
        stats
        .get("languages", {})
        .get("percentage", {})
    )

    if not languages:
        return ""

    languages = list(
        languages.items()
    )[:MAX_LANGUAGES]

    rows = []

    for language, percentage in languages:

        bar = make_bar(
            percentage
        )

        rows.append(
            f"| **{language}** | "
            f"`{bar}` | "
            f"**{format_percentage(percentage)}** |"
        )

    return (
        "### 💻 Languages\n\n"
        "| Language | Usage | Share |\n"
        "|:--|:--|--:|\n"
        + "\n".join(rows)
    )


def build_technologies_section(stats):
    """Build technology statistics."""

    technologies = stats.get(
        "technologies",
        [],
    )

    if not technologies:
        return ""

    technologies = technologies[
        :MAX_TECHNOLOGIES
    ]

    rows = []

    for item in technologies:

        technology = item.get(
            "technology",
            "Unknown",
        )

        percentage = item.get(
            "percentage",
            0,
        )

        repository_count = item.get(
            "repositories",
            0,
        )

        rows.append(
            f"| **{technology}** | "
            f"{repository_count} | "
            f"**{format_percentage(percentage)}** |"
        )

    return (
        "### 🛠️ Technologies\n\n"
        "| Technology | Repositories | Usage |\n"
        "|:--|--:|--:|\n"
        + "\n".join(rows)
    )


def build_top_repositories_section(stats):
    """Build top repository statistics."""

    repositories = (
        stats
        .get("repositories", {})
        .get("top", [])
    )

    if not repositories:
        return ""

    repositories = repositories[
        :MAX_REPOSITORIES
    ]

    rows = []

    for repository in repositories:

        name = repository.get(
            "name",
            "Unknown",
        )

        commits = repository.get(
            "commits",
            0,
        )

        private = repository.get(
            "private",
            False,
        )

        visibility = (
            "🔒 Private"
            if private
            else "🌎 Public"
        )

        rows.append(
            f"| `{name}` | "
            f"{format_number(commits)} | "
            f"{visibility} |"
        )

    return (
        "### 📦 Most Active Projects\n\n"
        "| Repository | Commits | Visibility |\n"
        "|:--|--:|:--|\n"
        + "\n".join(rows)
    )


def build_daily_activity_section(stats):
    """Build a compact activity heatmap."""

    daily_activity = stats.get(
        "daily_activity",
        {},
    )

    if not daily_activity:
        return ""

    values = list(
        daily_activity.values()
    )

    maximum = max(
        values,
        default=0,
    )

    if maximum == 0:
        return ""

    cells = []

    for count in values:

        if count == 0:
            cell = "·"
        elif count <= maximum * 0.25:
            cell = "░"
        elif count <= maximum * 0.50:
            cell = "▒"
        elif count <= maximum * 0.75:
            cell = "▓"
        else:
            cell = "█"

        cells.append(cell)

    # Keep the README reasonably compact.
    # Show approximately the last 180 days.
    cells = cells[-180:]

    # Break into rows.
    rows = []

    for index in range(
        0,
        len(cells),
        30,
    ):

        rows.append(
            "".join(
                cells[
                    index:index + 30
                ]
            )
        )

    return (
        "### 🔥 Recent Activity\n\n"
        "```text\n"
        + "\n".join(rows)
        + "\n"
        "```\n\n"
        "> `·` none  `░` low  `▒` medium  "
        "`▓` high  `█` very high"
    )


# ============================================================
# README GENERATION
# ============================================================

def build_github_stats_section(stats):
    """Build the complete generated section."""

    updated_at = stats.get(
        "updated_at",
        "",
    )

    activity = build_activity_section(
        stats
    )

    languages = build_languages_section(
        stats
    )

    technologies = build_technologies_section(
        stats
    )

    repositories = build_top_repositories_section(
        stats
    )

    daily_activity = build_daily_activity_section(
        stats
    )

    sections = [
        activity,
        languages,
        technologies,
        repositories,
        daily_activity,
    ]

    sections = [
        section
        for section in sections
        if section
    ]

    return (
        f"{START_MARKER}\n\n"
        + "\n\n".join(sections)
        + f"\n\n"
        f"<p align=\"center\">\n"
        f"<sub>Updated automatically · "
        f"{updated_at}</sub>\n"
        f"</p>\n\n"
        f"{END_MARKER}"
    )


def update_readme(generated_section):
    """Replace the generated README section."""

    if not README_FILE.exists():

        raise FileNotFoundError(
            f"README not found: {README_FILE}"
        )

    content = README_FILE.read_text(
        encoding="utf-8"
    )

    start_index = content.find(
        START_MARKER
    )

    end_index = content.find(
        END_MARKER
    )

    if (
        start_index == -1
        or end_index == -1
    ):

        raise RuntimeError(
            "README.md must contain both "
            f"{START_MARKER} and "
            f"{END_MARKER}"
        )

    end_index += len(
        END_MARKER
    )

    updated_content = (
        content[:start_index]
        + generated_section
        + content[end_index:]
    )

    if updated_content == content:

        print(
            "README is already up to date."
        )

        return False

    README_FILE.write_text(
        updated_content,
        encoding="utf-8",
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Loading GitHub statistics..."
    )

    stats = load_stats()

    print(
        "Generating README section..."
    )

    generated_section = (
        build_github_stats_section(
            stats
        )
    )

    changed = update_readme(
        generated_section
    )

    if changed:

        print(
            "README updated successfully."
        )

    else:

        print(
            "No README changes required."
        )


if __name__ == "__main__":
    main()