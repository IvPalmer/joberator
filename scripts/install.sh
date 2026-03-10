#!/bin/bash
set -e

JOBERATOR_DIR="$(cd "$(dirname "$0")/.." && pwd)"
JOBERATOR_HOME="$HOME/.joberator"

echo "========================================="
echo "  Joberator Installer"
echo "========================================="
echo ""

# Check prerequisites
echo "[1/5] Checking prerequisites..."

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "  ERROR: $1 is required but not installed."
        echo "  Install it with: $2"
        exit 1
    fi
    echo "  OK: $1 found"
}

check_cmd python3 "brew install python3"
check_cmd uv "brew install uv"
check_cmd git "brew install git"
check_cmd claude "npm install -g @anthropic-ai/claude-code"

# Create joberator home
echo ""
echo "[2/5] Setting up joberator home at $JOBERATOR_HOME..."
mkdir -p "$JOBERATOR_HOME"

# Install MCP server dependencies in a venv
echo ""
echo "[3/5] Installing job search MCP server dependencies..."
MCP_DIR="$JOBERATOR_DIR/mcp"
if [ ! -d "$MCP_DIR/.venv" ]; then
    uv venv "$MCP_DIR/.venv"
fi
source "$MCP_DIR/.venv/bin/activate"
uv pip install --quiet python-jobspy "mcp[cli]" 2>&1 | tail -5
deactivate

# Configure MCP server in Claude Code
echo ""
echo "[4/5] Configuring MCP server in Claude Code..."

claude mcp add joberator-jobs -s project -- "$JOBERATOR_DIR/mcp/.venv/bin/python3" "$JOBERATOR_DIR/mcp/job_search_server.py"
echo "  Added joberator-jobs MCP server to Claude Code config"

# Install Claude Code skills
echo ""
echo "[5/5] Installing Claude Code skills..."

SKILLS_DIR="$HOME/.claude/skills"
mkdir -p "$SKILLS_DIR"

# Symlink skills so they stay in sync with the repo
for skill_dir in "$JOBERATOR_DIR/skills"/*/; do
    skill_name=$(basename "$skill_dir")
    target="$SKILLS_DIR/joberator-$skill_name"
    if [ -L "$target" ]; then
        rm "$target"
    fi
    ln -s "$skill_dir" "$target"
    echo "  Linked skill: joberator-$skill_name"
done

echo ""
echo "========================================="
echo "  Joberator installed successfully!"
echo "========================================="
echo ""
echo "Usage:"
echo "  Start a new Claude Code session and try:"
echo "    > Find me remote Python developer jobs paying over \$150k"
echo ""
echo "  The joberator-jobs MCP server will search LinkedIn, Indeed,"
echo "  Glassdoor, ZipRecruiter, and Google Jobs simultaneously."
echo ""
echo "To set up auto-apply (optional):"
echo "  bash $JOBERATOR_DIR/scripts/setup-auto-apply.sh"
echo ""
