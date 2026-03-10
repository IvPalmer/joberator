#!/bin/bash
set -e

echo "========================================="
echo "  Joberator Uninstaller"
echo "========================================="
echo ""

# Remove MCP server config
echo "[1/3] Removing MCP server from Claude Code config..."
MCP_CONFIG="$HOME/.claude/.mcp.json"
if [ -f "$MCP_CONFIG" ]; then
    python3 << 'PYEOF'
import json, os
config_path = os.path.expanduser("~/.claude/.mcp.json")
with open(config_path, "r") as f:
    config = json.load(f)
if "joberator-jobs" in config:
    del config["joberator-jobs"]
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print("  Removed joberator-jobs MCP server")
else:
    print("  MCP server not found in config")
PYEOF
fi

# Remove skill symlinks
echo "[2/3] Removing skill symlinks..."
for link in "$HOME/.claude/skills"/joberator-*; do
    if [ -L "$link" ]; then
        rm "$link"
        echo "  Removed: $(basename "$link")"
    fi
done

# Remove auto-apply
echo "[3/3] Removing auto-apply bot..."
if [ -d "$HOME/.joberator" ]; then
    read -p "Remove ~/.joberator directory? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$HOME/.joberator"
        echo "  Removed ~/.joberator"
    fi
fi

echo ""
echo "Joberator uninstalled. The repo itself was not deleted."
echo ""
