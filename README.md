# Joberator

Job search and auto-apply automation for Claude Code.

Search LinkedIn, Indeed, Glassdoor, ZipRecruiter, and Google Jobs directly from Claude Code — then optionally auto-apply to LinkedIn Easy Apply jobs.

## Quick Start

```bash
git clone https://github.com/YOUR_USER/joberator.git
cd joberator
bash scripts/install.sh
```

Then start a new Claude Code session:

```
> Find me remote fullstack developer jobs paying over $150k
> Search for data engineer positions in Austin, TX posted in the last 24 hours
> Look for senior Python developer roles at companies hiring right now
```

## What It Does

### Job Search (MCP Server)
- Searches **5 job boards simultaneously**: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs
- **No login required** — scrapes public job listings
- **Zero ban risk** — no account interaction
- Filters by: keywords, location, salary, remote, job type, recency
- Returns structured results with title, company, salary, URL, description

### Auto Apply (Optional)
- Automates **LinkedIn Easy Apply** using browser automation
- Uses `undetected-chromedriver` for stealth
- Optional LLM integration for answering screening questions
- Powered by [GodsScion/Auto_job_applier_linkedIn](https://github.com/GodsScion/Auto_job_applier_linkedIn)

```bash
bash scripts/setup-auto-apply.sh
```

## Prerequisites

- Python 3.10+
- Claude Code CLI
- Google Chrome (for auto-apply only)

## Project Structure

```
joberator/
  mcp/
    job_search_server.py    # MCP server for job search
    requirements.txt
  skills/
    search-jobs/SKILL.md    # Claude Code skill for job search
    auto-apply/SKILL.md     # Claude Code skill for auto-apply
  scripts/
    install.sh              # One-command installer
    setup-auto-apply.sh     # Auto-apply bot setup
    uninstall.sh            # Clean uninstall
```

## Auto-Apply Safety

LinkedIn automation violates their Terms of Service. To minimize risk:

- Keep applications under **15-20 per day**
- Use `stealth_mode = True` in settings
- Set conservative `click_gap` (5+ seconds)
- Consider using a LinkedIn Premium account (gets warnings before bans)
- Monitor the bot's activity regularly

## Uninstall

```bash
bash scripts/uninstall.sh
```

Removes MCP server config, skill symlinks, and optionally the auto-apply bot.
