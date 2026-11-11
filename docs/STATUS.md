# Status (2026-11-11)

- Production: https://joberator.grooveops.dev, a Dokploy app built from the `vps-deploy` branch (rebuilt on push). The dashboard sits behind the fleet's Google login (oauth2-proxy at the edge); the `/guia` review page is public. The app's own Basic Auth gate and its fail-closed mode are described in the README on `vps-deploy`. SQLite lives in a named volume on the server.
- Branches: `main` is the default branch and is contained in `vps-deploy`. The deploy side (Dockerfile, RUNTIME.md, docs/ROADMAP.md, tests/, ui-lab/, the dashboard auth gate and `/guia`) exists only on `vps-deploy`.
- Mac checkout: `~/Dev/work/freelance/joberator`, usually on `main`. The MCP server is not registered in any Claude or Codex config (checked 2026-11-11); add it to a `.mcp.json` when a session needs it.
- Private state is not in this repo: the application records sit in the ignored `job-applications/`, and the operator's notes live in his private elder-brain wiki (`wiki/projects/joberator.md`).
