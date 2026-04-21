FROM python:3.11-slim
WORKDIR /app

COPY mcp/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

COPY . .

# Patch kanban.py for container: bind all interfaces, no browser auto-open,
# and don't exit when DB is empty (let _ensure_schema create it)
RUN sed -i 's|HTTPServer(("127.0.0.1", PORT)|HTTPServer(("0.0.0.0", PORT)|' scripts/kanban.py && \
    sed -i 's|^\(\s*\)webbrowser.open|\1#webbrowser.open|' scripts/kanban.py && \
    sed -i 's|^\(\s*\)exit(1)|\1pass  # patched: allow empty DB|' scripts/kanban.py

ENV PYTHONUNBUFFERED=1
EXPOSE 5151

# DB lives at $HOME/.joberator/jobs.db — mounted as volume by compose/Dokploy
RUN mkdir -p /root/.joberator

CMD ["python", "scripts/kanban.py"]
