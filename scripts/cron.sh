#!/bin/bash
# Setup Cron Job for Spotify Sync
#
# This script helps you set up a cron job to run the Spotify sync daily.
# It will add a cron job that runs at 2am daily.
#
# Usage:
#   ./scripts/cron.sh

set -e

# Get the absolute path to the project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SYNC_SCRIPT="$PROJECT_ROOT/scripts/runner.py"
LOG_DIR="$PROJECT_ROOT/logs"

# Verify the sync script exists
if [ ! -f "$SYNC_SCRIPT" ]; then
    echo "ERROR: Sync script not found at $SYNC_SCRIPT"
    exit 1
fi

# Make sure it's executable
chmod +x "$SYNC_SCRIPT"

# Create logs directory
mkdir -p "$LOG_DIR"

# Cron schedule: Run daily at 2am
CRON_SCHEDULE="0 2 * * *"
# Use the wrapper script which handles environment setup properly
WRAPPER_SCRIPT="$PROJECT_ROOT/scripts/cron_wrapper.sh"
if [ ! -f "$WRAPPER_SCRIPT" ]; then
    echo "ERROR: Cron wrapper script not found at $WRAPPER_SCRIPT"
    exit 1
fi
chmod +x "$WRAPPER_SCRIPT"
# Use wrapper script which handles PATH and environment setup
CRON_COMMAND="/bin/bash $WRAPPER_SCRIPT"

# Create temporary file with new cron job
TEMP_CRON=$(mktemp)

# Get existing crontab (if any) and filter out any existing spotim8 entries
(crontab -l 2>/dev/null | grep -v "spotim8\|scripts/runner" || true) > "$TEMP_CRON"

# Add the new cron job
echo "$CRON_SCHEDULE $CRON_COMMAND" >> "$TEMP_CRON"

# Install the new crontab
crontab "$TEMP_CRON"

# Clean up
rm "$TEMP_CRON"

echo "✅ Cron job installed successfully!"
echo ""
echo "Schedule: Daily at 2:00 AM"
echo "Wrapper: $WRAPPER_SCRIPT"
echo "Script: $SYNC_SCRIPT"
echo "Logs: $LOG_DIR/sync.log"
echo ""
echo "To view your crontab:"
echo "  crontab -l"
echo ""
echo "To remove this cron job:"
echo "  crontab -e  # Then delete the line with 'spotim8' or 'cron_wrapper'"
echo ""
echo "To test the sync script manually:"
echo "  /bin/bash $WRAPPER_SCRIPT --skip-sync"

