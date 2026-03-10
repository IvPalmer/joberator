#!/bin/bash
set -e

JOBERATOR_HOME="$HOME/.joberator"
AUTO_APPLY_DIR="$JOBERATOR_HOME/auto-apply"

echo "========================================="
echo "  Joberator Auto-Apply Setup"
echo "========================================="
echo ""
echo "This will install GodsScion/Auto_job_applier_linkedIn"
echo "for automated LinkedIn Easy Apply."
echo ""
echo "WARNING: LinkedIn automation violates their TOS."
echo "Use at your own risk. Recommended: max 15-20 apps/day."
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Check prerequisites
echo ""
echo "[1/4] Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python version: $PYTHON_VERSION"

if ! command -v google-chrome &>/dev/null && ! [ -d "/Applications/Google Chrome.app" ]; then
    echo "ERROR: Google Chrome is required"
    exit 1
fi
echo "  Chrome: found"

# Clone the repo
echo ""
echo "[2/4] Cloning Auto_job_applier_linkedIn..."

if [ -d "$AUTO_APPLY_DIR" ]; then
    echo "  Directory exists, pulling latest..."
    cd "$AUTO_APPLY_DIR" && git pull
else
    git clone https://github.com/GodsScion/Auto_job_applier_linkedIn.git "$AUTO_APPLY_DIR"
fi

# Install dependencies
echo ""
echo "[3/4] Installing dependencies..."
cd "$AUTO_APPLY_DIR"
pip3 install --quiet undetected-chromedriver pyautogui setuptools openai flask-cors flask 2>&1 | tail -5

# Guide config
echo ""
echo "[4/4] Configuration needed"
echo ""
echo "You need to edit the config files in:"
echo "  $AUTO_APPLY_DIR/config/"
echo ""
echo "Required files to edit:"
echo "  1. secrets.py   — LinkedIn email/password"
echo "  2. search.py    — Job titles, locations, filters"
echo "  3. personals.py — Your name, phone, email"
echo "  4. questions.py — Default answers + resume path"
echo "  5. settings.py  — Speed/stealth settings"
echo ""
echo "Recommended settings.py changes:"
echo "  run_in_background = True"
echo "  stealth_mode = True"
echo "  click_gap = 5  (seconds between actions)"
echo ""
echo "========================================="
echo "  Auto-apply installed!"
echo "========================================="
echo ""
echo "To run:"
echo "  cd $AUTO_APPLY_DIR && python3 runAiBot.py"
echo ""
echo "Or from Claude Code:"
echo "  > Start auto-applying to LinkedIn jobs"
echo ""
