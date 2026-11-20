---
name: search-jobs
description: Search job boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs) through the joberator-jobs MCP server and present the best matches. Use when the user asks to find or search for jobs.
---

# Joberator: Job Search

Search for jobs matching the user's criteria using the `joberator-jobs` MCP server.

## How to use

The user will ask to search for jobs. Use the `search_jobs` MCP tool to find matching positions.

### Examples

**Basic search:**
- "Find me remote Python developer jobs"
- "Search for data engineer positions in San Francisco"
- "Look for fullstack developer jobs paying over $150k"

### Process

1. Parse the user's request to extract: search terms, location, salary, remote preference, job type
2. Call the `search_jobs` tool with appropriate parameters
3. Present results in a clean, scannable format
4. Highlight the best matches and why they fit
5. Ask if the user wants to refine the search or see more details on specific jobs

### Tips

- Default to `is_remote: true` if the user mentions remote work
- Use `hours_old: 24` for "recent" or "new" jobs, `72` for default, `168` for "this week"
- If salary is mentioned, set `min_salary` accordingly
- For broader results, search all sites. For faster results, use just `linkedin,indeed`
- LinkedIn rate-limits after ~10 pages — keep `results_wanted` at 20-30 for best reliability

## Target source registry (`mcp/search_targets.json`, local only)

The operator keeps a curated list of priority sources (companies, LATAM marketplaces, communities, recruiters) in `mcp/search_targets.json`. The file is gitignored because this repo is public: it holds the salary goal and contact names. If it exists, read its `goal` field and, when asked to "search everywhere" / "any positions", sweep the registry, not just the default boards. Each entry has a `search_method` that tells you HOW to pull it — `search_jobs` cannot scrape most of them:

- `jobspy` — the `search_jobs` MCP tool (linkedin/indeed/google).
- `ats_public_board` / `public_board` — fetch the `url` directly (WebFetch / the ATS JSON, e.g. Greenhouse/Trakstar). Not jobspy.
- `marketplace_profile` — login-gated talent marketplace. Profile-based matching, nothing to scrape; remind the user to keep the profile live.
- `manual` — login-gated community channels; the user checks manually.
- `referral` / `relationship` — go through the named contact or recruiter; no board.
- `unconfirmed` — needs the user to clarify before use.

Respect each entry's `currency` flag against the file's `goal`; entries the file marks off-target are fallbacks only.
