import fs from "node:fs/promises";
import path from "node:path";

const TOKEN = process.env.GITHUB_TOKEN;
const OUTPUT = process.env.OUTPUT_FILE || "assets/contribution-heatmap.svg";
const YEAR = Number(process.env.CONTRIBUTION_YEAR || new Date().getUTCFullYear());
const PROFILE_URL = process.env.PROFILE_URL || "";

if (!TOKEN) {
  throw new Error("Missing GITHUB_TOKEN environment variable.");
}

if (!Number.isInteger(YEAR) || YEAR < 2008 || YEAR > 9999) {
  throw new Error(`Invalid CONTRIBUTION_YEAR: ${process.env.CONTRIBUTION_YEAR}`);
}

const GRAPHQL_ENDPOINT = "https://api.github.com/graphql";

const query = `
  query ContributionCalendar($from: DateTime!, $to: DateTime!) {
    viewer {
      login
      contributionsCollection(from: $from, to: $to) {
        contributionCalendar {
          totalContributions
          weeks {
            contributionDays {
              date
              weekday
              contributionCount
            }
          }
        }
      }
    }
  }
`;

async function fetchContributions() {
  // GitHub rejects ranges longer than one year, so end on Dec 31 instead of Jan 1.
  const from = `${YEAR}-01-01T00:00:00Z`;
  const to = `${YEAR}-12-31T23:59:59Z`;

  const response = await fetch(GRAPHQL_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "github-profile-contribution-heatmap"
    },
    body: JSON.stringify({ query, variables: { from, to } })
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok || body.errors?.length) {
    const details = body.errors?.map((e) => e.message).join("; ");
    throw new Error(`GitHub GraphQL request failed (${response.status}): ${details || JSON.stringify(body)}`);
  }

  if (!body.data?.viewer) {
    throw new Error("GitHub GraphQL returned no viewer. Check token permissions.");
  }

  return {
    login: body.data.viewer.login,
    calendar: body.data.viewer.contributionsCollection.contributionCalendar
  };
}

function dateKey(date) {
  return date.toISOString().slice(0, 10);
}

function makeYearDays(year, apiWeeks) {
  const byDate = new Map();

  for (const week of apiWeeks) {
    for (const day of week.contributionDays) {
      byDate.set(day.date, Number(day.contributionCount) || 0);
    }
  }

  const days = [];
  const cursor = new Date(Date.UTC(year, 0, 1));
  const end = new Date(Date.UTC(year + 1, 0, 1));

  while (cursor < end) {
    const date = dateKey(cursor);
    days.push({
      date,
      count: byDate.get(date) ?? 0,
      weekday: cursor.getUTCDay()
    });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }

  return days;
}

function calculateStreaks(days) {
  let longest = 0;
  let run = 0;

  for (const day of days) {
    if (day.count > 0) {
      run += 1;
      longest = Math.max(longest, run);
    } else {
      run = 0;
    }
  }

  // Current streak is active if today has activity; otherwise yesterday
  // may still be the latest active day. Dates use UTC consistently.
  const today = dateKey(new Date());
  const yesterdayDate = new Date();
  yesterdayDate.setUTCDate(yesterdayDate.getUTCDate() - 1);
  const yesterday = dateKey(yesterdayDate);

  const latestEligible = today <= `${YEAR}-12-31` && today >= `${YEAR}-01-01`
    ? today
    : (yesterday >= `${YEAR}-01-01` && yesterday <= `${YEAR}-12-31` ? yesterday : null);

  let current = 0;
  if (latestEligible) {
    let index = days.findIndex((d) => d.date === latestEligible);
    if (index >= 0 && days[index].count === 0) index -= 1;
    while (index >= 0 && days[index].count > 0) {
      current += 1;
      index -= 1;
    }
  }

  return { current, longest };
}

function escapeXml(value) {
  return String(value).replace(/[<>&'"]/g, (char) => ({
    "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;"
  })[char]);
}

function colorFor(count) {
  if (count === 0) return "#ebedf0";
  if (count <= 3) return "#9be9a8";
  if (count <= 6) return "#40c463";
  if (count <= 9) return "#30a14e";
  return "#216e39";
}

function formatDate(date) {
  return new Intl.DateTimeFormat("en", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC"
  }).format(new Date(`${date}T00:00:00Z`));
}

function generateSvg({ login, days }) {
  const cell = 11;
  const gap = 3;
  const step = cell + gap;
  const left = 34;
  const top = 52;
  const right = 14;
  const bottom = 42;

  const firstWeekday = new Date(Date.UTC(YEAR, 0, 1)).getUTCDay();
  const weekCount = Math.ceil((firstWeekday + days.length) / 7);
  const width = left + weekCount * step - gap + right;
  const height = top + 7 * step - gap + bottom + 48;

  const totals = days.reduce((sum, day) => sum + day.count, 0);
  const streaks = calculateStreaks(days);

  const monthLabels = [];
  for (let month = 0; month < 12; month += 1) {
    const first = new Date(Date.UTC(YEAR, month, 1));
    const offset = Math.floor((firstWeekday + Math.floor((first - Date.UTC(YEAR, 0, 1)) / 86400000)) / 7);
    monthLabels.push(`<text class="month" x="${left + offset * step}" y="34">${first.toLocaleString("en", { month: "short", timeZone: "UTC" })}</text>`);
  }

  const weekdayLabels = [
    `<text class="weekday" x="0" y="${top + 1 * step + 9}">Mon</text>`,
    `<text class="weekday" x="0" y="${top + 3 * step + 9}">Wed</text>`,
    `<text class="weekday" x="0" y="${top + 5 * step + 9}">Fri</text>`
  ];

  const cells = days.map((day) => {
    const date = new Date(`${day.date}T00:00:00Z`);
    const dayOfYear = Math.floor((date - Date.UTC(YEAR, 0, 1)) / 86400000);
    const week = Math.floor((firstWeekday + dayOfYear) / 7);
    const x = left + week * step;
    const y = top + day.weekday * step;
    const label = `${day.count} contribution${day.count === 1 ? "" : "s"} on ${formatDate(day.date)}`;
    return `<g><title>${escapeXml(label)}</title><rect x="${x}" y="${y}" width="${cell}" height="${cell}" rx="2" fill="${colorFor(day.count)}" stroke="rgba(27,31,36,0.06)" stroke-width="0.5"/></g>`;
  }).join("\n");

  const statY = top + 7 * step + 23;
  const legendX = Math.max(left, width - 154);
  const legend = [
    `<text class="small" x="${legendX - 35}" y="${statY + 3}">Less</text>`,
    ...["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"].map((color, i) =>
      `<rect x="${legendX + i * 15}" y="${statY - 8}" width="11" height="11" rx="2" fill="${color}"/>`),
    `<text class="small" x="${legendX + 83}" y="${statY + 3}">More</text>`
  ].join("");

  const title = `${totals.toLocaleString("en-US")} contributions in ${YEAR}`;
  const profileLink = PROFILE_URL || `https://github.com/${login}`;
  const statsLine = `${streaks.current} day current streak  ·  ${streaks.longest} day longest streak`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">
  <title id="title">${escapeXml(title)}</title>
  <desc id="desc">GitHub contribution calendar for ${escapeXml(login)} in ${YEAR}. ${escapeXml(statsLine)}. Each square represents one day; darker green means more contributions.</desc>
  <style>
    text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
    .heading { fill: #1f2328; font-size: 15px; font-weight: 600; }
    .subheading { fill: #656d76; font-size: 11px; }
    .month { fill: #656d76; font-size: 10px; }
    .weekday { fill: #656d76; font-size: 9px; }
    .stat { fill: #1f2328; font-size: 11px; font-weight: 600; }
    .small { fill: #656d76; font-size: 9px; }
    @media (prefers-color-scheme: dark) {
      .heading, .stat { fill: #e6edf3; }
      .subheading, .month, .weekday, .small { fill: #9198a1; }
      rect { stroke: rgba(240,246,252,0.08); }
    }
  </style>
  <a href="${escapeXml(profileLink)}">
    <text class="heading" x="0" y="16">${escapeXml(title)}</text>
  </a>
  <text class="subheading" x="0" y="31">${escapeXml(login)} · Public and private contribution counts, when authorized</text>
  ${monthLabels.join("\n  ")}
  ${weekdayLabels.join("\n  ")}
  ${cells}
  <text class="stat" x="0" y="${statY + 24}">${escapeXml(statsLine)}</text>
  ${legend}
</svg>
`;
}

async function main() {
  const { login, calendar } = await fetchContributions();
  const days = makeYearDays(YEAR, calendar.weeks);
  const svg = generateSvg({ login, days });

  await fs.mkdir(path.dirname(OUTPUT), { recursive: true });
  await fs.writeFile(OUTPUT, svg, "utf8");

  const total = days.reduce((sum, day) => sum + day.count, 0);
  const streaks = calculateStreaks(days);
  console.log(`Generated ${OUTPUT}`);
  console.log(`Account: ${login}`);
  console.log(`Year: ${YEAR}`);
  console.log(`Contributions: ${total}`);
  console.log(`Current streak: ${streaks.current}; longest streak: ${streaks.longest}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
