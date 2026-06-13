FROM python:3.11-slim
WORKDIR /app

COPY mcp/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

COPY . .

# Patch kanban.py for container: no browser auto-open, and don't exit when the
# DB is empty (let _ensure_schema create it). The bind address is set via the
# JOBERATOR_HOST env below instead of a sed patch.
RUN sed -i 's|^\(\s*\)webbrowser.open|\1#webbrowser.open|' scripts/kanban.py && \
    sed -i 's|^\(\s*\)exit(1)|\1pass  # patched: allow empty DB|' scripts/kanban.py

# Bind all interfaces so Traefik can reach it. Because this is a non-loopback
# bind, kanban.py serves 503 for every private route until JOBERATOR_PASS (set
# in Dokploy) is present — a misconfigured deploy fails closed (only the public
# /guia page is served) instead of exposing the dashboard.
ENV JOBERATOR_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1
EXPOSE 5151

# DB lives at $HOME/.joberator/jobs.db — mounted as volume by compose/Dokploy
# Pre-create empty schema so kanban.py boots cleanly on a fresh deploy
RUN mkdir -p /root/.joberator && python -c "import sqlite3; c=sqlite3.connect('/root/.joberator/jobs.db'); c.execute('''CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, company TEXT NOT NULL, location TEXT, url TEXT, salary TEXT, source TEXT, description TEXT, notes TEXT, status TEXT DEFAULT \"interested\", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''); c.commit(); c.close()"

CMD ["python", "scripts/kanban.py"]
