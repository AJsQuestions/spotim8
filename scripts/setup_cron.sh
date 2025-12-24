#!/bin/bash
# Setup Cron Job for Spotify Sync
#
# This script helps you set up a cron job to run the Spotify sync daily.
# It will add a cron job that runs at 2am daily.
#
# Usage:
#   ./scripts/setup_cron.sh

set -e

# Get the absolute path to the project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SYNC_SCRIPT="$PROJECT_ROOT/scripts/run_sync_local.sh"
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
CRON_COMMAND="cd $PROJECT_ROOT && $SYNC_SCRIPT >> $LOG_DIR/sync.log 2>&1"

# Create temporary file with new cron job
TEMP_CRON=$(mktemp)

# Get existing crontab (if any) and filter out any existing spotim8 entries
(crontab -l 2>/dev/null | grep -v "spotim8\|run_sync_local" || true) > "$TEMP_CRON"

# Add the new cron job
echo "$CRON_SCHEDULE $CRON_COMMAND" >> "$TEMP_CRON"

# Install the new crontab
crontab "$TEMP_CRON"

# Clean up
rm "$TEMP_CRON"

echo "✅ Cron job installed successfully!"
echo ""
echo "Schedule: Daily at 2:00 AM"
echo "Script: $SYNC_SCRIPT"
echo "Logs: $LOG_DIR/sync.log"
echo ""
echo "To view your crontab:"
echo "  crontab -l"
echo ""
echo "To remove this cron job:"
echo "  crontab -e  # Then delete the line with 'spotim8' or 'run_sync_local'"
echo ""
echo "To test the sync script manually:"
echo "  $SYNC_SCRIPT"

