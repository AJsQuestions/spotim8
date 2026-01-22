"""
Configuration module for sync automation.

All environment variables and configuration constants are defined here.
"""

import os
from pathlib import Path

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


# Import centralized config helpers
from src.scripts.common.config_helpers import (
    parse_bool_env,
    parse_int_env,
    parse_str_env,
    parse_list_env,
    get_env_or_none,
    require_env
)

# Alias for backward compatibility
_parse_bool_env = parse_bool_env


# Get project root (assumes this file is at src/scripts/automation/config.py)
# Calculate from file: src/scripts/automation/config.py -> 4 levels up to project root
# (config.py -> automation -> scripts -> src -> PROJECT_ROOT)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent

# Load .env file early so environment variables are available
if DOTENV_AVAILABLE:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

# ============================================================================
# BASIC CONFIGURATION
# ============================================================================
# Most commonly customized settings - users typically only change these
OWNER_NAME = parse_str_env("PLAYLIST_OWNER_NAME", "AJ")
BASE_PREFIX = parse_str_env("PLAYLIST_PREFIX", "Finds")

# Playlist type enable/disable flags
# Set to "false" in .env to disable specific playlist types
ENABLE_MONTHLY = parse_bool_env("PLAYLIST_ENABLE_MONTHLY", True)
ENABLE_MOST_PLAYED = parse_bool_env("PLAYLIST_ENABLE_MOST_PLAYED", True)
ENABLE_DISCOVERY = parse_bool_env("PLAYLIST_ENABLE_DISCOVERY", True)

# Individual prefixes for different playlist types
# Most users don't need to customize these - defaults work well
# Only set if you want different prefixes for different playlist types
PREFIX_MONTHLY = parse_str_env("PLAYLIST_PREFIX_MONTHLY", BASE_PREFIX)
PREFIX_GENRE_MONTHLY = parse_str_env("PLAYLIST_PREFIX_GENRE_MONTHLY", BASE_PREFIX)
PREFIX_YEARLY = parse_str_env("PLAYLIST_PREFIX_YEARLY", BASE_PREFIX)
PREFIX_GENRE_MASTER = parse_str_env("PLAYLIST_PREFIX_GENRE_MASTER", "am")
PREFIX_MOST_PLAYED = parse_str_env("PLAYLIST_PREFIX_MOST_PLAYED", "Top")
PREFIX_TIME_BASED = parse_str_env("PLAYLIST_PREFIX_TIME_BASED", "Vibes")  # Deprecated: feature removed
PREFIX_REPEAT = parse_str_env("PLAYLIST_PREFIX_REPEAT", "OnRepeat")  # Deprecated: feature removed
PREFIX_DISCOVERY = parse_str_env("PLAYLIST_PREFIX_DISCOVERY", "Discovery")

# ============================================================================
# PLAYLIST NAME TEMPLATES
# ============================================================================
# Advanced customization - rarely changed, good defaults provided
# Only customize if you need non-standard playlist naming

MONTHLY_NAME_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_MONTHLY",
    "{owner}{prefix}{mon}{year}"
)
YEARLY_NAME_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_YEARLY",
    "{owner}{prefix}{year}"
)
GENRE_MONTHLY_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_GENRE_MONTHLY",
    "{genre}{prefix}{mon}{year}"
)
GENRE_YEARLY_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_GENRE_YEARLY",
    "{genre}{prefix}{year}"
)
GENRE_NAME_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_GENRE_MASTER",
    "{owner}{prefix}{genre}"
)
MOST_PLAYED_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_MOST_PLAYED",
    "{owner}{prefix}{mon}{year}"
)
TIME_BASED_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_TIME_BASED",
    "{owner}{prefix}{mon}{year}"
)
REPEAT_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_REPEAT",
    "{owner}{prefix}{mon}{year}"
)
DISCOVERY_TEMPLATE = parse_str_env(
    "PLAYLIST_TEMPLATE_DISCOVERY",
    "{owner}{prefix}{mon}{year}"
)

# ============================================================================
# PLAYLIST LIMITS AND RETENTION
# ============================================================================

# Genre playlist thresholds
# MIN_TRACKS_FOR_GENRE: Minimum absolute number of tracks (adaptive threshold also used)
# Lower this if you want more genre playlists with fewer tracks
MIN_TRACKS_FOR_GENRE = parse_int_env("MIN_TRACKS_FOR_GENRE", 10)  # Lowered from 20 to 10
MAX_GENRE_PLAYLISTS = parse_int_env("MAX_GENRE_PLAYLISTS", 25)  # Increased from 19 to 25
KEEP_MONTHLY_MONTHS = parse_int_env("KEEP_MONTHLY_MONTHS", 3)

# ============================================================================
# FORMATTING OPTIONS
# ============================================================================
# Advanced formatting customization - most users don't need to change these
DATE_FORMAT = parse_str_env("PLAYLIST_DATE_FORMAT", "short")  # Options: short, medium, long, numeric
SEPARATOR_MONTH = parse_str_env("PLAYLIST_SEPARATOR_MONTH", "none")  # Options: none, space, dash, underscore
SEPARATOR_PREFIX = parse_str_env("PLAYLIST_SEPARATOR_PREFIX", "none")  # Options: none, space, dash, underscore
CAPITALIZATION = parse_str_env("PLAYLIST_CAPITALIZATION", "preserve")  # Options: title, upper, lower, preserve
DESCRIPTION_TEMPLATE = parse_str_env(
    "PLAYLIST_DESCRIPTION_TEMPLATE",
    "{description} from {period} (automatically updated; manual additions welcome)"
)

# ============================================================================
# PATHS AND CONSTANTS
# ============================================================================

DATA_DIR = PROJECT_ROOT / "data"
LIKED_SONGS_PLAYLIST_ID = "__liked_songs__"  # Match spotim8 library constant

# ============================================================================
# MONTH NAME MAPPINGS
# ============================================================================

MONTH_NAMES_SHORT = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
}
MONTH_NAMES_MEDIUM = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December"
}
MONTH_NAMES = MONTH_NAMES_SHORT  # Default to short for backward compatibility

