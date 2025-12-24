#!/bin/bash
# Local Spotify Sync Runner
# 
# This script runs the spotify_sync.py script locally with proper environment setup.
# It's designed to be run manually or via cron for scheduled automation.
#
# Usage:
#   ./scripts/run_sync_local.sh              # Full sync + update
#   ./scripts/run_sync_local.sh --skip-sync  # Update only (uses existing data)
#   ./scripts/run_sync_local.sh --sync-only  # Sync only, no playlist updates
#
# For cron setup (runs daily at 2am):
#   0 2 * * * /path/to/spotim8/scripts/run_sync_local.sh >> /path/to/spotim8/logs/sync.log 2>&1

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root directory
cd "$PROJECT_ROOT"

# Check if virtual environment exists (optional, but recommended)
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Check for required environment variables
if [ -z "$SPOTIPY_CLIENT_ID" ] || [ -z "$SPOTIPY_CLIENT_SECRET" ]; then
    echo "ERROR: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set"
    echo "Either export them or add them to a .env file in the project root"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Run the sync script with all passed arguments
echo "Starting Spotify sync at $(date)"
python scripts/spotify_sync.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Sync completed successfully at $(date)"
else
    echo "Sync failed with exit code $EXIT_CODE at $(date)"
    exit $EXIT_CODE
fi

