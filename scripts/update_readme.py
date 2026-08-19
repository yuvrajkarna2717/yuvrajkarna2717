#!/usr/bin/env python3
"""
Generate the GitHub statistics section in README.md from data/github-stats.json.

This script renders a self-contained, dependency-free SVG "CRT terminal" card
(assets/github-stats.svg) and swaps it into README.md between:

    <!-- GITHUB_STATS_START -->
    <!-- GITHUB_STATS_END -->

Nothing else in README.md is touched. The card is a real .svg file referenced
via <img>, so it renders identically in light/dark GitHub themes and supports
gradients, filters and light SMIL animation (the blinking cursor / power LED).
"""

import datetime
import json
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


README_FILE = Path("README.md")
DATA_FILE = Path("data/github-stats.json")
SVG_FILE = Path("assets/github-stats.svg")

START_MARKER = "<!-- GITHUB_STATS_START -->"
END_MARKER = "<!-- GITHUB_STATS_END -->"

MAX_LANGUAGES = 6
MAX_TECHNOLOGIES = 8
MAX_REPOSITORIES = 5
HEATMAP_DAYS = 140
HEATMAP_COLUMNS = 20

SOCIAL_LINKS = [
    ("github", "https://github.com/yuvrajkarna2717"),
    ("linkedin", "https://www.linkedin.com/in/yuvrajkarna"),
    ("twitter", "https://x.com/yuvrajkarna"),
    ("leetcode", "https://www.leetcode.com/u/yuvrajkarna"),
]


# ============================================================
# THEME — "phosphor CRT" palette / type
# ============================================================

class Theme:
    bezel = "#15120c"
    bezel_edge = "#2a2115"
    screen = "#0b0906"
    screen_edge = "#241b0e"
    divider = "#3a2c14"

    amber_bright = "#ffc94d"
    amber = "#e0a530"
    amber_mid = "#b8801f"
    amber_dim = "#6e5320"
    amber_track = "#241a0a"

    green_led = "#4ee08a"
    text_muted = "#8a7654"

    font = "'JetBrains Mono','Fira Code','SFMono-Regular',Menlo,Consolas,monospace"


T = Theme()


# ============================================================
# DATA
# ============================================================

def load_stats():
    """Load the latest GitHub statistics."""

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Statistics file not found: {DATA_FILE}")

    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


# ============================================================
# SMALL HELPERS
# ============================================================

def esc(value):
    return xml_escape(str(value))


def format_number(value):
    return f"{value:,}"


def format_percentage(value):
    return f"{value:.1f}%"


def clamp(value, low, high):
    return max(low, min(high, value))


def truncate(text, max_chars):
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# ============================================================
# SVG PRIMITIVES
# ============================================================

def svg_text(x, y, content, size=13, color=None, weight=400, anchor="start",
             letter_spacing=None, opacity=None, filter_id=None):
    color = color or T.amber
    parts = [
        f'<text x="{x}" y="{y}" font-family="{T.font}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}"'
    ]
    if letter_spacing is not None:
        parts.append(f' letter-spacing="{letter_spacing}"')
    if opacity is not None:
        parts.append(f' opacity="{opacity}"')
    if filter_id is not None:
        parts.append(f' filter="url(#{filter_id})"')
    parts.append(f'>{esc(content)}</text>')
    return "".join(parts)


def svg_rect(x, y, w, h, fill, rx=0, stroke=None, stroke_width=1, opacity=None, filter_id=None):
    parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"']
    if stroke:
        parts.append(f' stroke="{stroke}" stroke-width="{stroke_width}"')
    if opacity is not None:
        parts.append(f' opacity="{opacity}"')
    if filter_id:
        parts.append(f' filter="url(#{filter_id})"')
    parts.append(" />")
    return "".join(parts)


def dashed_divider(x, y, w, color=None):
    color = color or T.divider
    return (
        f'<line x1="{x}" y1="{y}" x2="{x + w}" y2="{y}" '
        f'stroke="{color}" stroke-width="1" stroke-dasharray="4 4" />'
    )


def section_label(x, y, label):
    return svg_text(x, y, f"\u25b8 {label}", size=12.5, color=T.amber_bright,
                     weight=700, letter_spacing="1.5")


# ============================================================
# CARD BUILDER
# ============================================================

class Card:
    """Accumulates SVG body fragments and tracks the vertical cursor."""

    def __init__(self, width, pad_x):
        self.width = width
        self.pad_x = pad_x
        self.content_w = width - 2 * pad_x
        self.y = 0
        self.body = []

    def add(self, fragment):
        self.body.append(fragment)

    def advance(self, dy):
        self.y += dy


def build_title_bar(card, updated_at):
    card.advance(30)
    # power LED with a slow flicker
    led_x, led_y = card.pad_x, card.y
    card.add(
        f'<circle cx="{led_x}" cy="{led_y - 4}" r="4" fill="{T.green_led}">'
        f'<animate attributeName="opacity" values="1;0.55;1" dur="2.4s" repeatCount="indefinite" />'
        f'</circle>'
    )
    card.add(svg_text(led_x + 14, led_y, "yuvraj@github", size=13, color=T.amber_bright, weight=700))
    card.add(svg_text(led_x + 14 + 118, led_y, "~ % status.sh", size=13, color=T.text_muted))

    stamp = updated_at.replace("T", " ").replace("Z", " UTC") if updated_at else ""
    if stamp:
        card.add(svg_text(card.pad_x + card.content_w, led_y, stamp, size=11,
                           color=T.text_muted, anchor="end"))

    card.advance(16)
    card.add(dashed_divider(card.pad_x, card.y, card.content_w))
    card.advance(28)


def build_stat_grid(card, stats):
    activity = stats.get("activity", {})
    repositories = stats.get("repositories", {})

    active_days = sum(1 for count in stats.get("daily_activity", {}).values() if count > 0)

    items = [
        (format_number(activity.get("commits", 0)), "COMMITS"),
        (format_number(activity.get("total_contributions", 0)), "CONTRIBUTIONS"),
        (format_number(active_days), "ACTIVE DAYS"),
        (format_number(repositories.get("analyzed", 0)), "PROJECTS"),
    ]

    col_w = card.content_w / len(items)

    for index, (value, label) in enumerate(items):
        cx = card.pad_x + col_w * index + col_w / 2
        card.add(svg_text(cx, card.y, value, size=24, color=T.amber_bright,
                           weight=700, anchor="middle", filter_id="glow"))
        card.add(svg_text(cx, card.y + 20, label, size=9.5, color=T.text_muted,
                           anchor="middle", letter_spacing="1.5"))
        if index > 0:
            divider_x = card.pad_x + col_w * index
            card.add(
                f'<line x1="{divider_x}" y1="{card.y - 28}" x2="{divider_x}" '
                f'y2="{card.y + 14}" stroke="{T.divider}" stroke-width="1" />'
            )

    card.advance(46)
    card.add(dashed_divider(card.pad_x, card.y, card.content_w))
    card.advance(32)


def build_languages(card, stats):
    languages = list(stats.get("languages", {}).get("percentage", {}).items())[:MAX_LANGUAGES]
    if not languages:
        return

    card.add(section_label(card.pad_x, card.y, "LANGUAGES"))
    card.advance(22)

    label_w = 118
    pct_w = 50
    bar_x = card.pad_x + label_w
    bar_w = card.content_w - label_w - pct_w
    bar_h = 8

    for name, pct in languages:
        pct = clamp(pct, 0, 100)
        card.add(svg_text(card.pad_x, card.y + 6, truncate(name, 14), size=12, color=T.amber))
        card.add(svg_rect(bar_x, card.y - 6, bar_w, bar_h, T.amber_track, rx=4))
        fill_w = bar_w * pct / 100
        card.add(svg_rect(bar_x, card.y - 6, fill_w, bar_h, T.amber_bright, rx=4, filter_id="soft-glow"))
        card.add(svg_text(bar_x + bar_w + pct_w, card.y + 6, format_percentage(pct),
                           size=11.5, color=T.amber_mid, anchor="end"))
        card.advance(24)

    card.advance(14)
    card.add(dashed_divider(card.pad_x, card.y, card.content_w))
    card.advance(32)


def build_technologies(card, stats):
    technologies = stats.get("technologies", [])[:MAX_TECHNOLOGIES]
    if not technologies:
        return

    card.add(section_label(card.pad_x, card.y, "TECHNOLOGIES"))
    card.advance(22)

    columns = 2
    gap = 12
    chip_w = (card.content_w - gap * (columns - 1)) / columns
    chip_h = 30

    for index, item in enumerate(technologies):
        name = item.get("technology", "Unknown")
        pct = clamp(item.get("percentage", 0), 0, 100)
        repo_count = item.get("repositories", 0)

        col = index % columns
        row = index // columns
        x = card.pad_x + col * (chip_w + gap)
        y = card.y + row * (chip_h + 10)

        border_opacity = 0.35 + 0.55 * (pct / 100)
        card.add(svg_rect(x, y, chip_w, chip_h, T.screen_edge, rx=6,
                           stroke=T.amber_dim, stroke_width=1, opacity=None))
        card.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{chip_w:.1f}" height="{chip_h:.1f}" '
            f'rx="6" fill="none" stroke="{T.amber_bright}" stroke-width="1" '
            f'opacity="{border_opacity:.2f}" />'
        )
        card.add(svg_text(x + 12, y + 19, truncate(name, 16), size=12, color=T.amber, weight=600))
        card.add(svg_text(x + chip_w - 12, y + 19, f"{repo_count} repos \u00b7 {format_percentage(pct)}",
                           size=10, color=T.text_muted, anchor="end"))

    rows = -(-len(technologies) // columns)
    card.advance(rows * (chip_h + 10) - 10 + 14)
    card.add(dashed_divider(card.pad_x, card.y, card.content_w))
    card.advance(32)


def build_top_repositories(card, stats):
    repositories = stats.get("repositories", {}).get("top", [])[:MAX_REPOSITORIES]
    if not repositories:
        return

    card.add(section_label(card.pad_x, card.y, "TOP REPOSITORIES"))
    card.advance(22)

    for repository in repositories:
        name = repository.get("name", "unknown")
        commits = repository.get("commits", 0)
        private = repository.get("private", False)

        card.add(svg_text(card.pad_x, card.y + 5, "$", size=12, color=T.amber_dim))
        card.add(svg_text(card.pad_x + 16, card.y + 5, truncate(name, 28), size=12,
                           color=T.amber_bright, weight=600))

        tag_text = "PRIVATE" if private else "PUBLIC"
        tag_color = T.amber_dim if private else T.green_led
        commit_label = f"{format_number(commits)} commits"

        card.add(svg_text(card.pad_x + card.content_w - 70, card.y + 5, commit_label,
                           size=11, color=T.text_muted, anchor="end"))
        card.add(svg_text(card.pad_x + card.content_w, card.y + 5, tag_text,
                           size=9.5, color=tag_color, anchor="end", letter_spacing="1"))
        card.advance(22)

    card.advance(10)
    card.add(dashed_divider(card.pad_x, card.y, card.content_w))
    card.advance(32)


def bucket_color(count, maximum):
    if maximum <= 0 or count <= 0:
        return T.amber_track
    ratio = clamp(count / maximum, 0, 1)
    steps = [
        (0.25, T.amber_dim),
        (0.50, T.amber_mid),
        (0.75, T.amber),
        (1.01, T.amber_bright),
    ]
    for threshold, color in steps:
        if ratio <= threshold:
            return color
    return T.amber_bright


def build_heatmap(card, stats):
    daily_activity = stats.get("daily_activity", {})
    if not daily_activity:
        return

    values = list(daily_activity.values())[-HEATMAP_DAYS:]
    maximum = max(values, default=0)

    card.add(section_label(card.pad_x, card.y, f"ACTIVITY \u00b7 last {len(values)} days"))
    card.advance(22)

    size = 15
    gap = 4
    columns = HEATMAP_COLUMNS

    for index, count in enumerate(values):
        col = index % columns
        row = index // columns
        x = card.pad_x + col * (size + gap)
        y = card.y + row * (size + gap)
        color = bucket_color(count, maximum)
        card.add(svg_rect(x, y, size, size, color, rx=3))

    rows = -(-len(values) // columns)
    grid_h = rows * (size + gap) - gap
    card.advance(grid_h + 18)

    legend_x = card.pad_x
    card.add(svg_text(legend_x, card.y, "less", size=10, color=T.text_muted))
    swatch_x = legend_x + 32
    swatches = [T.amber_track, T.amber_dim, T.amber_mid, T.amber, T.amber_bright]
    for i, color in enumerate(swatches):
        card.add(svg_rect(swatch_x + i * (size - 1), card.y - 11, size - 3, size - 3, color, rx=2))
    card.add(svg_text(swatch_x + len(swatches) * (size - 1) + 8, card.y, "more", size=10, color=T.text_muted))

    card.advance(28)
    card.add(dashed_divider(card.pad_x, card.y, card.content_w))
    card.advance(30)


def build_footer(card, updated_at):
    sync_label = "$ last_sync --utc"
    sync_value = updated_at.replace("T", " ").replace("Z", "") if updated_at else "unknown"

    card.add(svg_text(card.pad_x, card.y, sync_label, size=11, color=T.amber_dim))
    card.add(svg_text(card.pad_x + 130, card.y, sync_value, size=11, color=T.text_muted))

    connect_cmd = "$ connect " + " ".join(f"--{name}" for name, _ in SOCIAL_LINKS)
    card.add(svg_text(card.pad_x + card.content_w, card.y, connect_cmd, size=11,
                       color=T.amber_dim, anchor="end"))

    cursor_x = card.pad_x + card.content_w + 4
    card.add(
        f'<rect x="{cursor_x:.1f}" y="{card.y - 10:.1f}" width="6" height="12" fill="{T.amber_bright}">'
        f'<animate attributeName="opacity" values="1;0;1" dur="1.1s" repeatCount="indefinite" />'
        f'</rect>'
    )

    card.advance(20)


def build_svg(stats):
    width = 880
    pad_x = 28
    updated_at = stats.get("updated_at", "")

    card = Card(width, pad_x)
    card.advance(14)  # top inner padding before title bar starts counting

    build_title_bar(card, updated_at)
    build_stat_grid(card, stats)
    build_languages(card, stats)
    build_technologies(card, stats)
    build_top_repositories(card, stats)
    build_heatmap(card, stats)
    build_footer(card, updated_at)

    height = int(card.y + 20)
    bezel_pad = 14
    total_w = width
    total_h = height + 2 * bezel_pad

    defs = f"""
    <defs>
      <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="2.2" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <filter id="soft-glow" x="-40%" y="-200%" width="180%" height="500%">
        <feGaussianBlur stdDeviation="1.1" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <pattern id="scanlines" width="4" height="4" patternUnits="userSpaceOnUse">
        <rect width="4" height="2" fill="#ffffff" opacity="0.015" />
      </pattern>
      <radialGradient id="vignette" cx="50%" cy="35%" r="75%">
        <stop offset="60%" stop-color="#000000" stop-opacity="0" />
        <stop offset="100%" stop-color="#000000" stop-opacity="0.35" />
      </radialGradient>
    </defs>
    """.strip()

    body = "\n    ".join(card.body)

    svg = f"""<svg width="{total_w}" height="{total_h}" viewBox="0 0 {total_w} {total_h}"
     xmlns="http://www.w3.org/2000/svg" role="img"
     aria-label="Yuvraj Karna — GitHub activity terminal">
  {defs}

  <rect x="0" y="0" width="{total_w}" height="{total_h}" rx="18" fill="{T.bezel}" stroke="{T.bezel_edge}" stroke-width="1" />
  <circle cx="{bezel_pad}" cy="{bezel_pad}" r="2" fill="{T.bezel_edge}" />
  <circle cx="{total_w - bezel_pad}" cy="{bezel_pad}" r="2" fill="{T.bezel_edge}" />
  <circle cx="{bezel_pad}" cy="{total_h - bezel_pad}" r="2" fill="{T.bezel_edge}" />
  <circle cx="{total_w - bezel_pad}" cy="{total_h - bezel_pad}" r="2" fill="{T.bezel_edge}" />

  <rect x="{bezel_pad}" y="{bezel_pad}" width="{total_w - 2 * bezel_pad}" height="{total_h - 2 * bezel_pad}"
        rx="10" fill="{T.screen}" stroke="{T.screen_edge}" stroke-width="1" />

  <g transform="translate({bezel_pad}, {bezel_pad})">
    {body}
  </g>

  <rect x="{bezel_pad}" y="{bezel_pad}" width="{total_w - 2 * bezel_pad}" height="{total_h - 2 * bezel_pad}"
        rx="10" fill="url(#scanlines)" />
  <rect x="{bezel_pad}" y="{bezel_pad}" width="{total_w - 2 * bezel_pad}" height="{total_h - 2 * bezel_pad}"
        rx="10" fill="url(#vignette)" />
</svg>
"""
    return svg


# ============================================================
# README GENERATION
# ============================================================

def build_readme_section():
    """Build the small markdown fragment that sits between the markers."""

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    connect_badges = "\n".join(
        f'  <a href="{url}"><img src="https://img.shields.io/badge/{name.upper()}-connect-1a1408'
        f'?style=flat-square&labelColor=0b0906&color=241a0a" alt="{name}" /></a>'
        for name, url in SOCIAL_LINKS
    )

    return f"""{START_MARKER}

<div align="center">

<img src="./assets/github-stats.svg" alt="Yuvraj Karna's GitHub activity terminal" width="880" />

<sub>auto-generated \u00b7 refreshed {now}</sub>

</div>

{END_MARKER}"""


def update_readme(generated_section):
    """Replace the generated README section."""

    if not README_FILE.exists():
        raise FileNotFoundError(f"README not found: {README_FILE}")

    content = README_FILE.read_text(encoding="utf-8")

    start_index = content.find(START_MARKER)
    end_index = content.find(END_MARKER)

    if start_index == -1 or end_index == -1:
        raise RuntimeError(
            f"README.md must contain both {START_MARKER} and {END_MARKER}"
        )

    end_index += len(END_MARKER)

    updated_content = content[:start_index] + generated_section + content[end_index:]

    if updated_content == content:
        print("README is already up to date.")
        return False

    README_FILE.write_text(updated_content, encoding="utf-8")
    return True


# ============================================================
# MAIN
# ============================================================

def main():
    print("Loading GitHub statistics...")
    stats = load_stats()

    print("Rendering terminal stats card...")
    svg = build_svg(stats)
    SVG_FILE.parent.mkdir(parents=True, exist_ok=True)
    SVG_FILE.write_text(svg, encoding="utf-8")

    print("Generating README section...")
    generated_section = build_readme_section()
    changed = update_readme(generated_section)

    if changed:
        print("README updated successfully.")
    else:
        print("No README changes required.")


if __name__ == "__main__":
    main()