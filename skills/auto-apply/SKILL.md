# Joberator: Auto Apply

Automate LinkedIn Easy Apply using the GodsScion/Auto_job_applier_linkedIn bot.

## Prerequisites

The auto-apply bot must be set up first. Run:
```bash
/path/to/joberator/scripts/setup-auto-apply.sh
```

## How it works

The bot uses `undetected-chromedriver` to:
1. Log into LinkedIn with your saved Chrome session
2. Search for jobs matching your configured criteria
3. Click through Easy Apply forms automatically
4. Use an optional LLM to answer screening questions intelligently

## Configuration

All config lives in `~/.joberator/auto-apply/config/`:

- `secrets.py` — LinkedIn credentials (or use saved browser session)
- `search.py` — Job titles, locations, experience levels, blacklisted companies
- `settings.py` — Speed settings, stealth mode, background mode

## Usage

When the user asks to auto-apply to jobs:

1. Check if auto-apply is set up: `ls ~/.joberator/auto-apply/`
2. If not set up, guide them through `scripts/setup-auto-apply.sh`
3. If set up, run: `cd ~/.joberator/auto-apply && python runAiBot.py`
4. Monitor the output and report progress

## Safety Notes

- LinkedIn may restrict accounts that apply too aggressively
- Recommended: max 15-20 applications per day
- Use `stealth_mode = True` and conservative `click_gap` settings
- Consider using a LinkedIn Premium account (gets warnings before bans)
- Always review the bot's activity periodically
