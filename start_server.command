#!/bin/bash

# Ensure we are in the project directory
cd "$(dirname "$0")"

echo "=========================================="
echo "   Menu Zen Backend Launcher"
echo "=========================================="

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    echo "Please install Python 3 from https://www.python.org/downloads/"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Checking/Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the manage script
echo "Starting server..."
python scripts/manage.py start

# Keep terminal open if server crashes or stops
echo ""
echo "Server stopped."
read -n 1 -s -r -p "Press any key to close this window..."
