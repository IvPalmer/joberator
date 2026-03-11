# Joberator

Job search automation platform with smart matching and a visual dashboard.

Search LinkedIn, Indeed, Google Jobs, Gupy, and Vagas.com.br — with profile-based scoring and application tracking.

## Setup

### Prerequisites
- Python 3.10+
- Google Chrome or Brave with an active LinkedIn session (for profile sync)
- macOS (LinkedIn cookie extraction uses Keychain — Linux support not yet implemented)

### Install

```bash
git clone https://github.com/IvPalmer/joberator.git
cd joberator
bash scripts/install.sh
```

This will:
1. Create a Python venv and install dependencies
2. Initialize the jobs database at `~/.joberator/jobs.db`
3. Print next steps for profile sync and dashboard

### Sync Your LinkedIn Profile

The matching engine needs your LinkedIn profile to score results. You must be logged into LinkedIn in Chrome or Brave.

```bash
# This reads your li_at cookie from Chrome and syncs your profile via LinkedIn's API.
# First run will trigger a macOS Keychain access prompt — click "Allow".
cd joberator
mcp/.venv/bin/python3 -c "
from linkedin_auth import refresh_cookies
from job_search_server import sync_profile
refresh_cookies()
print(sync_profile())
"
```

Your profile is saved to `~/.joberator/profile.json`. Re-run this if you update your LinkedIn profile.

### Start the Dashboard

```bash
python3 scripts/kanban.py
```

Opens at `http://localhost:5151`.

## Dashboard

- **Search tab** — Search 5 platforms simultaneously, results scored against your profile
- **Board tab** — Kanban board to track applications (interested → applied → interviewing → offered)
- **Settings tab** — Search defaults, scheduled searches, profile info

## Features

### Multi-Platform Search
- **LinkedIn** — Global remote + regional results
- **Indeed** — Regional (e.g., br.indeed.com for Brazil)
- **Google Jobs** — Aggregated listings
- **Gupy** — Brazilian tech job platform (public API)
- **Vagas.com.br** — Brazilian job board (web scraping)

### Smart Matching
- Auto-generates search queries from your LinkedIn profile
- Scores every result by skill match, tech overlap, seniority, and domain relevance
- Color-coded match percentages (high/mid/low)

### Application Tracking
- Save jobs from search results to your board
- Drag-and-drop kanban: interested → applied → interviewing → offered → rejected → archived
- Notes on each job card
- URL deduplication (no double-saves)
- Apply button and status changes directly from job detail modal

### Scheduled Searches
- Set up automated searches from the Settings tab (6h, 12h, daily, 2d, weekly)
- Auto-saves jobs above a configurable match score threshold
- Runs in background while dashboard is open

### LinkedIn Integration
- Reads `li_at` cookie from Chrome/Brave (macOS Keychain decryption)
- Profile sync via Voyager API for skill extraction and matching
- Easy Apply detection on LinkedIn jobs

## Claude Code Integration (Optional)

If you use [Claude Code](https://claude.ai/claude-code), you can add the MCP server for natural language job searching:

```bash
claude mcp add joberator-jobs -s user -- /path/to/joberator/mcp/.venv/bin/python3 /path/to/joberator/mcp/job_search_server.py
```

Then in Claude Code:
```
> Find me remote data engineer jobs paying over $100k
> Search for senior Python developer roles posted this week
```

## Project Structure

```
joberator/
  mcp/
    job_search_server.py    # MCP server with all tools
    linkedin_auth.py        # Chrome cookie extraction + decryption
    matching.py             # Profile fingerprinting + job scoring
    brazil_scrapers.py      # Gupy + Vagas.com.br scrapers
    requirements.txt
  scripts/
    kanban.py               # Dashboard (search + board + settings)
    install.sh              # One-command installer
```

## Data Storage

All data is stored locally in `~/.joberator/`:
- `jobs.db` — SQLite database with saved jobs and statuses
- `profile.json` — Your synced LinkedIn profile
- `config.json` — Search defaults and scheduled search configs

## Troubleshooting

**"Database not found" on dashboard start**
Run `bash scripts/install.sh` to initialize the database.

**No search results / only LinkedIn results**
Make sure all platforms are selected (colored chips in the sidebar). Brazilian platforms (Gupy, Vagas) need Market set to "Brazil".

**LinkedIn cookie errors**
Re-open LinkedIn in Chrome, make sure you're logged in, then re-run the profile sync command. The `li_at` cookie expires periodically.

**macOS Keychain prompt keeps appearing**
Click "Always Allow" when prompted to grant access to Chrome Safe Storage.

## Future: LinkedIn Profile Update

The Voyager API (LinkedIn's internal API) supports profile editing via the same `li_at` cookie used for reading. This could enable programmatic updates to headline, summary, skills, and experience.

### Approach
1. Intercept Chrome DevTools network requests while editing profile fields
2. Capture Voyager API endpoints, methods, headers, and JSON payloads
3. Replay requests with `li_at` cookie + CSRF token (`JSESSIONID`)

### Known Details
- Endpoints are under `/voyager/api/identity/` (POST/PATCH)
- Requires both `li_at` and `JSESSIONID` cookies
- Risk level: low-medium for infrequent edits to your own profile
- No existing Python library supports this — would need custom implementation

### Use Cases
- Auto-update headline to match target roles
- Sync skills from resume to LinkedIn
- Bulk update experience descriptions with keyword optimization
