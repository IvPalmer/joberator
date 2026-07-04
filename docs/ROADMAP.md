---
goal: "Job-search platform for any user: find, score, and track applications from one dashboard."
owner: operator
lead: joberator-lead
status: draft
next: Inventory the current single-user assumptions before choosing any auth, tenancy, or storage design.
decisions_needed: []
blocked_by: []
---

## Open tasks

- [ ] Inventory the single-user assumptions before multi-user rollout, including `~/.joberator/jobs.db`, `profile.json`, `config.json`, local LinkedIn cookie sync, global scheduled searches, Basic Auth behind oauth2-proxy, and the public `/guia` exception. [T-001] #autonomous-safe
- [ ] Record production runtime receipts in docs: live at `joberator.grooveops.dev`, behind oauth2-proxy, Dokploy-managed, `/guia` public, and SQLite stored in a named volume with 13 rows at the 2026-07-03 restore drill. [T-002] #autonomous-safe
- [ ] Add a CI-ready regression command that runs the auth gate tests and covers `/guia`, locked public bind behavior, `HEAD`, SQLite schema migration, and basic save/list/update/delete job flows. [T-003] #autonomous-safe
- [ ] Decide whether the dirty search-source registry work is intended: `skills/search-jobs/SKILL.md` now references `mcp/search_targets.json`, and the untracked registry encodes LATAM/USD target sources plus manual/referral paths. [T-004]
- [ ] Triage the remaining dirty workspace entries, including `.claude/settings.local.json` and `.claude/launch.json`, into commit-worthy project config versus local-only files to ignore. [T-005]
- [ ] Classify TODO/FIXME/NOTE hotspot output into real code/docs debt versus benign UI/source-data words; the supplied audit says roughly 1.8k markers, while a local broad sample is concentrated in notes/review strings and source registry text. [T-006] #autonomous-safe
- [ ] Refactor storage path handling behind one internal boundary so dashboard, MCP tools, installer, Docker build, and tests agree on where jobs, profile, and config live before adding any user dimension. [T-007] #autonomous-safe
- [ ] Add a lightweight source-registry validation test for `mcp/search_targets.json` once T-004 is accepted, checking required fields, known `search_method` values, and clear handling for manual, referral, marketplace, and scrapeable sources. [T-008] #autonomous-safe
- [ ] After T-001 is complete, choose the minimal "any user" boundary for the pilot app: continue operator-managed single dashboard, add profile switching, or introduce real per-user separation behind the existing proxy. [T-009]
- [ ] Convert the selected boundary into implementation tasks only after the inventory is reviewed, keeping `/guia` public and preserving fail-closed private routes. [T-010]

## Path forward

Start with T-001 because the repo is intentionally single-user today and the strategic goal is generalized for any user.
Then land T-002 so future work preserves the actual fleet boundary: Dokploy, oauth2-proxy, public `/guia`, and the named SQLite volume.
Use T-003 before behavior changes so auth and job-tracking regressions are cheap to detect.
Resolve T-004 and T-005 before committing source-registry or local editor configuration work.
Only after the inventory is reviewed should the project pick a multi-user boundary or propose auth and tenancy changes.
