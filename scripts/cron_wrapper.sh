#!/bin/bash
# Cron Wrapper Script for Spotify Sync
#
# This wrapper ensures proper environment setup for cron execution on macOS.
# It handles PATH, virtual environment activation, error logging, and prevents
# concurrent runs.

set -u  # Fail on undefined variables (safer than set -e)

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Set up PATH for macOS cron (cron has minimal PATH)
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Change to project root
cd "$PROJECT_ROOT" || {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): ERROR: Cannot change to project root: $PROJECT_ROOT" >&2
    exit 1
}

# Create logs directory if it doesn't exist
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/sync.log"
LOCK_FILE="$LOG_DIR/sync.lock"
MAX_LOG_SIZE=$((50 * 1024 * 1024))  # 50MB max log size
SYNC_TIMEOUT=3600  # 1 hour timeout (sync should complete faster)

# Function to log messages
log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $*" | tee -a "$LOG_FILE"
}

# Function to cleanup on exit
cleanup() {
    local exit_code=$?
    if [ -f "$LOCK_FILE" ]; then
        rm -f "$LOCK_FILE"
    fi
    if [ $exit_code -ne 0 ]; then
        log_msg "ERROR: Sync failed with exit code $exit_code"
    fi
    exit $exit_code
}
trap cleanup EXIT INT TERM

# Check for lock file (prevent concurrent runs)
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        log_msg "WARNING: Previous sync still running (PID: $PID), skipping this run"
        exit 0  # Exit gracefully - don't fail cron job
    else
        log_msg "WARNING: Stale lock file found, removing it"
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file with current PID
echo $$ > "$LOCK_FILE"

# Rotate log if it's too large (macOS-compatible)
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$LOG_SIZE" -gt $MAX_LOG_SIZE ]; then
        log_msg "Rotating log file (exceeded ${MAX_LOG_SIZE} bytes, current: ${LOG_SIZE})"
        # Create timestamped backup
        BACKUP_FILE="${LOG_FILE}.$(date +%Y%m%d_%H%M%S).old"
        mv "$LOG_FILE" "$BACKUP_FILE" 2>/dev/null || true
        touch "$LOG_FILE"
        # Keep only last 3 old logs
        ls -t "${LOG_FILE}".*.old 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null || true
    fi
fi

# Find virtual environment directory
VENV_DIR="$PROJECT_ROOT/venv"
if [ ! -d "$VENV_DIR" ]; then
    VENV_DIR="$PROJECT_ROOT/.venv"
fi

# Verify venv exists
if [ ! -d "$VENV_DIR" ]; then
    log_msg "ERROR: Virtual environment not found at $PROJECT_ROOT/venv or $PROJECT_ROOT/.venv"
    exit 1
fi

# Verify .env file exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    log_msg "ERROR: .env file not found at $PROJECT_ROOT/.env"
    exit 1
fi

SYNC_SCRIPT="$PROJECT_ROOT/scripts/sync.py"

# Verify the sync script exists
if [ ! -f "$SYNC_SCRIPT" ]; then
    log_msg "ERROR: Sync script not found at $SYNC_SCRIPT"
    exit 1
fi

# Verify Python is available
if [ ! -f "$VENV_DIR/bin/python" ]; then
    log_msg "ERROR: Python not found in virtual environment at $VENV_DIR/bin/python"
    exit 1
fi

log_msg "=========================================="
log_msg "Starting Spotify sync cron job"
log_msg "=========================================="

# Activate the virtual environment
if ! source "$VENV_DIR/bin/activate" 2>/dev/null; then
    log_msg "ERROR: Failed to activate virtual environment"
    exit 1
fi

# Verify critical Python packages are available
if ! python -c "import spotipy, pandas, requests" 2>/dev/null; then
    log_msg "ERROR: Missing required Python packages (spotipy, pandas, requests)"
    exit 1
fi

# Run the sync script
# Note: Using direct execution instead of timeout wrapper for better reliability
# The sync script has its own retry logic and should complete within reasonable time
log_msg "Running sync script..."
python "$SYNC_SCRIPT" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log_msg "=========================================="
    log_msg "Sync completed successfully"
    log_msg "=========================================="
else
    log_msg "=========================================="
    log_msg "Sync failed with exit code: $EXIT_CODE"
    log_msg "=========================================="
fi

exit $EXIT_CODE
