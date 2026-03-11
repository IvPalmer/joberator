# Joberator

Job search automation platform with smart matching, powered by Claude Code.

Search LinkedIn, Indeed, Google Jobs, Gupy, and Vagas.com.br — with profile-based scoring and a visual dashboard.

## Quick Start

```bash
git clone https://github.com/IvPalmer/joberator.git
cd joberator
bash scripts/install.sh
```

## Dashboard

```bash
python scripts/kanban.py
```

Opens at `http://localhost:5151` with:
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

### Scheduled Searches
- Set up cron-style automated searches (6h, 12h, daily, 2d, weekly)
- Auto-saves jobs above a configurable match score threshold
- Runs in background while dashboard is open

### LinkedIn Integration
- Reads `li_at` cookie from Chrome/Brave (macOS Keychain decryption)
- Profile sync via Voyager API for skill extraction and matching
- Easy Apply detection on LinkedIn jobs

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

## Prerequisites

- Python 3.10+
- Claude Code CLI
- Google Chrome/Brave with LinkedIn session (for profile sync)

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

This is documented for future implementation. The official LinkedIn Profile Edit API exists but is gated behind LinkedIn's Partner Program (inaccessible to individual developers).
