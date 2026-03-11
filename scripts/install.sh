#!/bin/bash
set -e

JOBERATOR_DIR="$(cd "$(dirname "$0")/.." && pwd)"
JOBERATOR_HOME="$HOME/.joberator"
MCP_DIR="$JOBERATOR_DIR/mcp"

echo "========================================="
echo "  Joberator Installer"
echo "========================================="
echo ""

# Check prerequisites
echo "[1/4] Checking prerequisites..."

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "  ERROR: $1 is required but not installed."
        echo "  Install it with: $2"
        exit 1
    fi
    echo "  OK: $1 found"
}

check_cmd python3 "brew install python3 (macOS) / sudo apt install python3 (Linux)"
check_cmd git "brew install git (macOS) / sudo apt install git (Linux)"

# Create joberator home
echo ""
echo "[2/4] Setting up data directory at $JOBERATOR_HOME..."
mkdir -p "$JOBERATOR_HOME"

# Install dependencies in a venv
echo ""
echo "[3/4] Installing Python dependencies..."

if [ ! -d "$MCP_DIR/.venv" ]; then
    python3 -m venv "$MCP_DIR/.venv"
fi

"$MCP_DIR/.venv/bin/pip" install --quiet -r "$MCP_DIR/requirements.txt" 2>&1 | tail -5

# Initialize database
echo ""
echo "[4/4] Initializing database..."

"$MCP_DIR/.venv/bin/python3" -c "
import sqlite3, os
db_path = os.path.expanduser('~/.joberator/jobs.db')
conn = sqlite3.connect(db_path)
conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    url TEXT,
    salary TEXT,
    source TEXT,
    description TEXT,
    notes TEXT DEFAULT '',
    status TEXT DEFAULT 'interested',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()
conn.close()
print('  Database ready at', db_path)
"

echo ""
echo "========================================="
echo "  Joberator installed!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. Sync your LinkedIn profile (requires Chrome/Brave with active LinkedIn session):"
echo "     $MCP_DIR/.venv/bin/python3 -c \"from linkedin_auth import refresh_cookies; refresh_cookies()\""
echo "     (This will trigger a macOS Keychain prompt on first run)"
echo ""
echo "  2. Start the dashboard:"
echo "     python3 $JOBERATOR_DIR/scripts/kanban.py"
echo "     Opens at http://localhost:5151"
echo ""
echo "  Optional: Add MCP server to Claude Code (requires claude CLI):"
echo "     claude mcp add joberator-jobs -s user -- $MCP_DIR/.venv/bin/python3 $MCP_DIR/job_search_server.py"
echo ""
