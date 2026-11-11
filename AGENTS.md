# joberator

Where: work / freelance / joberator, `~/Dev/work/freelance/joberator` (manifest row `joberator`, lead `joberator-lead`).

Read docs/STATUS.md first: what runs where, the two branches, and what stays out of this repo.

## What this is
A job-search tool: an MCP server (`mcp/job_search_server.py`, server name `joberator-jobs`) that searches LinkedIn, Indeed, Glassdoor, ZipRecruiter and Google Jobs through `python-jobspy` and scores results against a synced LinkedIn profile, plus a dashboard (`scripts/kanban.py`, port 5151) to track applications. The repo is public: keep personal data, account names, cookies and application records out of commits, issues and PRs.

## Layout
- `mcp/`: MCP server, LinkedIn auth (`linkedin_auth.py` reads the browser's `li_at` cookie), matching, Brazil scrapers. Its venv is `mcp/.venv` (uv, Python 3.10).
- `scripts/`: dashboard, installer, auto-apply setup.
- `skills/`: the agent skills. `.agents/skills/` (Codex) and `.claude/skills/` (Claude) link to them; edit them in `skills/`.
- Data lives outside the repo, in `~/.joberator/` (`jobs.db`, `profile.json`, `config.json`, cookies).
- Ignored, never committed: `job-applications/` (the operator's private application records), `nordstack-analytics/` (a separate repo nested here: never commit into it from joberator, and commit there only as the operator, without AI trailers), PDFs and `resume-updates.md`.

## Run and verify
- Compile: `mcp/.venv/bin/python -m py_compile mcp/*.py scripts/kanban.py`.
- MCP server: `cd mcp && .venv/bin/python job_search_server.py` speaks MCP over stdio; `initialize` then `tools/list` returns its tools.
- Dashboard: `mcp/.venv/bin/python scripts/kanban.py` binds `127.0.0.1:5151`, open on localhost, with the local `~/.joberator` data. The operator's live board is production on the VPS: on `vps-deploy`, RUNTIME.md says how to reach it; do not start a local stack to work on production data.
- Tests (on `vps-deploy`): `mcp/.venv/bin/python tests/test_auth.py`.

## Working rules
- LinkedIn stays read-only: no programmatic profile writes through the Voyager API (terms of service and account-ban risk).
- Refresh cookies from the browser before LinkedIn calls (`refresh_cookies` rewrites `~/.joberator/cookies.json`) and never reuse a stale copy: calls made with a stale cookie can invalidate the session.
- Profile sync calls the Voyager API directly (`identity/dash/profiles?decorationId=FullProfileWithEntities-93`); its `included` array mixes entities from several profiles, so filter by `publicIdentifier` and the member URN.
- Changes go through PRs. Production builds from `vps-deploy` (see docs/STATUS.md).

## Lead
`joberator-lead` (Paperclip, reports to `product-chief`) leads this product: its goal, backlog, delivery and verified user outcome. It keeps the issues current, delegates to `joberator-worker-claude` and `joberator-worker-codex`, and reports results and real blockers to `product-chief`. This file is its project brief; `docs/ROADMAP.md` (on `vps-deploy`) is its backlog.
