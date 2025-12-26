#!/usr/bin/env python3
"""
Local Spotify Sync Runner (Wrapper)

This is a simple wrapper that ensures the virtual environment is used.
The main sync.py script now handles .env loading internally.

Usage:
    python scripts/runner.py              # Full sync + update
    python scripts/runner.py --skip-sync  # Update only (uses existing data)
    python scripts/runner.py --sync-only  # Sync only, no playlist updates
"""

import os
import sys
import subprocess
from pathlib import Path

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Change to project root directory
os.chdir(PROJECT_ROOT)

# Find virtual environment Python
venv_python = None
if (PROJECT_ROOT / "venv" / "bin" / "python").exists():
    venv_python = str(PROJECT_ROOT / "venv" / "bin" / "python")
elif (PROJECT_ROOT / ".venv" / "bin" / "python").exists():
    venv_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
else:
    # Fallback to system Python
    venv_python = sys.executable

# Create logs directory if it doesn't exist
logs_dir = PROJECT_ROOT / "logs"
logs_dir.mkdir(exist_ok=True)

# Run the sync script with all passed arguments
try:
    cmd = [venv_python, str(SCRIPT_DIR / "sync.py")] + sys.argv[1:]
    result = subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
    sys.exit(0)
except subprocess.CalledProcessError as e:
    sys.exit(e.returncode)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

