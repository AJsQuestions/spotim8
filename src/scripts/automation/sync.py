#!/usr/bin/env python3
"""
Unified Spotify Sync & Playlist Update

This script:
1. Syncs your Spotify library to local parquet files using src (optional)
2. Consolidates old monthly playlists into yearly genre-split playlists
3. Updates monthly playlists with liked songs (last 3 months only)
4. Updates genre-split monthly playlists (HipHop, Dance, Other)
5. Updates master genre playlists

IMPORTANT: This script only ADDS tracks to playlists. It never removes tracks.
Manually added tracks are preserved and will remain in the playlists even after
automated updates. Feel free to manually add tracks to any automatically generated
playlists - they will not be removed.

DATA PROTECTION: All destructive operations (track removal, playlist deletion) are
protected with automatic backups and verification to prevent data loss. Backups are
stored in data/.backups/ and can be restored if needed.

The script automatically loads environment variables from .env file if python-dotenv
is installed and a .env file exists in the project root.

Usage:
    python src/scripts/automation/sync.py              # Full sync + update
    python src/scripts/automation/sync.py --skip-sync  # Update only (fast, uses existing data)
    python src/scripts/automation/sync.py --sync-only  # Sync only, no playlist changes
    python src/scripts/automation/sync.py --all-months # Process all months, not just current

Environment Variables (set in .env file or environment):
    Required:
        SPOTIPY_CLIENT_ID       - Spotify app client ID
        SPOTIPY_CLIENT_SECRET   - Spotify app client secret
    
    Optional:
        SPOTIPY_REDIRECT_URI    - Redirect URI (default: http://127.0.0.1:8888/callback)
        SPOTIPY_REFRESH_TOKEN   - Refresh token for headless/CI auth
        PLAYLIST_OWNER_NAME     - Prefix for playlist names (default: "AJ")
        PLAYLIST_PREFIX         - Month playlist prefix (default: "Finds")
        
        Email Notifications (optional):
        EMAIL_ENABLED           - Enable email notifications (true/false)
        EMAIL_SMTP_HOST         - SMTP server (e.g., smtp.gmail.com)
        EMAIL_SMTP_PORT         - SMTP port (default: 587)
        EMAIL_SMTP_USER         - SMTP username
        EMAIL_SMTP_PASSWORD     - SMTP password (use app password for Gmail)
        EMAIL_TO                - Recipient email address
        EMAIL_FROM              - Sender email (defaults to EMAIL_SMTP_USER)
        EMAIL_SUBJECT_PREFIX    - Subject prefix (default: "[Spotify Sync]")

Run locally or via cron:
    # Direct run (loads .env automatically):
    python src/scripts/automation/sync.py
    
    # Via wrapper (for cron):
    python src/scripts/automation/runner.py
    
    # Linux/Mac cron (every day at 2am):
    0 2 * * * cd /path/to/spotim8 && /path/to/venv/bin/python src/scripts/automation/runner.py
"""

import argparse
import ast
import io
import os
import random
import sys
import time
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path
from dateutil.relativedelta import relativedelta
from contextlib import contextmanager
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing as mp

# Suppress urllib3/OpenSSL warnings (common on macOS with LibreSSL)
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*", category=UserWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

import numpy as np
import pandas as pd
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from tqdm import tqdm

# Suppress pandas Period timezone warnings
warnings.filterwarnings('ignore', category=UserWarning, message='.*Converting to PeriodArray.*')

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# Adaptive backoff multiplier (increases after rate errors, decays on success)
# Use constants from config, but allow runtime adjustment
_RATE_BACKOFF_MULTIPLIER = API_RATE_LIMIT_BACKOFF_MULTIPLIER
_RATE_BACKOFF_MAX = 16.0  # Maximum backoff multiplier

# Add project root to path
# Calculate from file: src/scripts/automation/sync.py -> 4 levels up to project root
# (sync.py -> automation -> scripts -> src -> PROJECT_ROOT)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent

# Verify PROJECT_ROOT is correct by checking for project markers
if not (PROJECT_ROOT / "pyproject.toml").exists() and not (PROJECT_ROOT / ".git").exists():
    # Fallback: try to find project root by looking for "src" directory
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").exists() and (parent / "pyproject.toml").exists():
            PROJECT_ROOT = parent
            break

# Add to path (ensure it's first and not duplicated)
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

# Load .env file early so environment variables are available for module-level code
if DOTENV_AVAILABLE:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

# Import spotim8 for full library sync (required)
from src import Spotim8, CacheConfig, set_response_cache, sync_all_export_data

# Import genre classification functions from shared module
from src.features.genres import (
    SPLIT_GENRES,
    get_split_genre, get_broad_genre,
    get_all_split_genres, get_all_broad_genres
)

# Import comprehensive genre inference
from src.features.genre_inference import (
    infer_genres_comprehensive,
    enhance_artist_genres_from_playlists
)

# Import configuration from config module
from src.scripts.automation.config import *

# Import formatting utilities from formatting module
from src.scripts.automation.formatting import format_playlist_name, format_playlist_description, format_yearly_playlist_name

# Import playlist operations from extracted modules
from src.scripts.automation.playlist_creation import create_or_update_playlist
from src.scripts.automation.playlist_update import update_monthly_playlists, update_genre_split_playlists, update_master_genre_playlists
from src.scripts.automation.playlist_consolidation import consolidate_old_monthly_playlists, delete_old_monthly_playlists, delete_duplicate_playlists

# Import common API helpers
from src.scripts.common.api_helpers import api_call, chunked as chunked_helper

# Import email notification module
try:
    import importlib.util
    email_notify_path = Path(__file__).parent / "email_notify.py"
    if email_notify_path.exists():
        spec = importlib.util.spec_from_file_location("email_notify", email_notify_path)
        email_notify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(email_notify)
        send_email_notification = email_notify.send_email_notification
        is_email_enabled = email_notify.is_email_enabled
        EMAIL_AVAILABLE = True
    else:
        EMAIL_AVAILABLE = False
except Exception:
    EMAIL_AVAILABLE = False


# ============================================================================
# CONFIGURATION - Set via environment variables
# ============================================================================

# Import config helpers
from src.scripts.common.config_helpers import parse_str_env

# Note: These are also defined in config.py - consider importing from there instead
# Keeping here for backward compatibility during refactoring
OWNER_NAME = parse_str_env("PLAYLIST_OWNER_NAME", "AJ")

# Individual prefixes for different playlist types
# If not set, falls back to PLAYLIST_PREFIX, then "Finds"
BASE_PREFIX = parse_str_env("PLAYLIST_PREFIX", "Finds")

# Import centralized config helpers (use from config module instead of duplicating)
from src.scripts.common.config_helpers import parse_bool_env

# Alias for backward compatibility during refactoring
_parse_bool_env = parse_bool_env

# Playlist type enable/disable flags (from .env)
# Note: These are also defined in config.py, but we keep them here for backward compatibility
# TODO: Remove these and import from config.py instead
ENABLE_MONTHLY = parse_bool_env("PLAYLIST_ENABLE_MONTHLY", True)
ENABLE_MOST_PLAYED = parse_bool_env("PLAYLIST_ENABLE_MOST_PLAYED", True)
# ENABLE_TIME_BASED removed - Vibes playlists no longer supported
# ENABLE_REPEAT removed - OnRepeat playlists no longer supported
ENABLE_DISCOVERY = parse_bool_env("PLAYLIST_ENABLE_DISCOVERY", True)

PREFIX_MONTHLY = os.environ.get("PLAYLIST_PREFIX_MONTHLY", BASE_PREFIX)
PREFIX_GENRE_MONTHLY = os.environ.get("PLAYLIST_PREFIX_GENRE_MONTHLY", BASE_PREFIX)
PREFIX_YEARLY = os.environ.get("PLAYLIST_PREFIX_YEARLY", BASE_PREFIX)
PREFIX_GENRE_MASTER = os.environ.get("PLAYLIST_PREFIX_GENRE_MASTER", "am")
PREFIX_MOST_PLAYED = os.environ.get("PLAYLIST_PREFIX_MOST_PLAYED", "Top")
PREFIX_TIME_BASED = os.environ.get("PLAYLIST_PREFIX_TIME_BASED", "Vibes")
PREFIX_REPEAT = os.environ.get("PLAYLIST_PREFIX_REPEAT", "OnRepeat")
PREFIX_DISCOVERY = os.environ.get("PLAYLIST_PREFIX_DISCOVERY", "Discovery")

# Playlist naming templates (can be customized via env vars)
MONTHLY_NAME_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_MONTHLY",
    "{owner}{prefix}{mon}{year}"
)
YEARLY_NAME_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_YEARLY",
    "{owner}{prefix}{year}"
)
GENRE_MONTHLY_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_GENRE_MONTHLY",
    "{genre}{prefix}{mon}{year}"
)
GENRE_YEARLY_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_GENRE_YEARLY",
    "{genre}{prefix}{year}"
)
GENRE_NAME_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_GENRE_MASTER",
    "{owner}{prefix}{genre}"
)
MOST_PLAYED_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_MOST_PLAYED",
    "{owner}{prefix}{mon}{year}"
)
TIME_BASED_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_TIME_BASED",
    "{owner}{prefix}{mon}{year}"  # Monthly format, can also use {type} for time-specific
)
REPEAT_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_REPEAT",
    "{owner}{prefix}{mon}{year}"  # Monthly format
)
DISCOVERY_TEMPLATE = os.environ.get(
    "PLAYLIST_TEMPLATE_DISCOVERY",
    "{owner}{prefix}{mon}{year}"
)

# Master genre playlist limits
# Note: These are also defined in config.py - prefer importing from there
# Keeping here for backward compatibility during refactoring
MIN_TRACKS_FOR_GENRE = 10  # Lowered from 20 to 10 for better genre diversity
MAX_GENRE_PLAYLISTS = 25  # Increased from 19 to 25

# Monthly playlist retention (how many recent months to keep as monthly playlists)
KEEP_MONTHLY_MONTHS = int(os.environ.get("KEEP_MONTHLY_MONTHS", "3"))

# Playlist formatting options
DATE_FORMAT = os.environ.get("PLAYLIST_DATE_FORMAT", "short")  # short, medium, long, numeric
SEPARATOR_MONTH = os.environ.get("PLAYLIST_SEPARATOR_MONTH", "none")  # none, space, dash, underscore
SEPARATOR_PREFIX = os.environ.get("PLAYLIST_SEPARATOR_PREFIX", "none")  # none, space, dash, underscore
CAPITALIZATION = os.environ.get("PLAYLIST_CAPITALIZATION", "preserve")  # title, upper, lower, preserve
DESCRIPTION_TEMPLATE = os.environ.get(
    "PLAYLIST_DESCRIPTION_TEMPLATE",
    "{description} from {period} (automatically updated; manual additions welcome)"
)

# Paths
DATA_DIR = PROJECT_ROOT / "data"
LIKED_SONGS_PLAYLIST_ID = "__liked_songs__"  # Match spotim8 library constant

# Month name mapping (short, medium, long)
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

# Genre classification functions:
# - get_split_genre() - Maps tracks to HipHop, Dance, or Other
# - get_broad_genre() - Maps tracks to broad categories (Hip-Hop, Electronic, etc.)
# - SPLIT_GENRES - List of split genres: ["HipHop", "Dance", "Other"]


# ============================================================================
# UTILITIES
# ============================================================================

# Global log buffer for email notifications
_log_buffer = []
# Global verbose flag (set by command-line argument)
_verbose = False

def log(msg: str) -> None:
    """Print message with timestamp and optionally buffer for email.
    
    Uses tqdm.write() to avoid interfering with progress bars.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {msg}"
    # Use tqdm.write() to avoid interfering with progress bars
    try:
        tqdm.write(log_line)
    except NameError:
        # tqdm not imported yet, use regular print
        print(log_line)
    
    # Buffer log for email notification
    if EMAIL_AVAILABLE and is_email_enabled():
        _log_buffer.append(log_line)

def verbose_log(msg: str) -> None:
    """Print verbose message only if verbose mode is enabled.
    
    Uses same formatting as log() but only prints when --verbose is set.
    """
    if _verbose:
        log(f"🔍 [VERBOSE] {msg}")

# Set log function for genre_inference module (after log is defined)
import src.features.genre_inference as genre_inference_module
genre_inference_module._log_fn = log


@contextmanager
def timed_step(step_name: str):
    """Context manager to time and log execution of a step."""
    start_time = time.time()
    log(f"⏱️  [START] {step_name}")
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        log(f"⏱️  [END] {step_name} (took {elapsed:.2f}s)")


def api_call(fn: Callable, *args, max_retries: int = API_RATE_LIMIT_MAX_RETRIES, backoff_factor: float = 1.0, **kwargs) -> Any:
    """Call Spotify API method `fn` with retries and exponential backoff on rate limits or transient errors.

    `fn` should be a callable (typically a bound method on a `spotipy.Spotify` client).
    The helper inspects exception attributes for 429/retry-after and uses exponential backoff.
    """
    global _RATE_BACKOFF_MULTIPLIER

    # Verbose logging for API calls
    fn_name = getattr(fn, '__name__', str(fn))
    verbose_log(f"API call: {fn_name}()")
    if _verbose and args:
        verbose_log(f"  Args: {args[:2]}{'...' if len(args) > 2 else ''}")
    if _verbose and kwargs:
        verbose_log(f"  Kwargs: {list(kwargs.keys())}")

    for attempt in range(max_retries):
        try:
            result = fn(*args, **kwargs)
            # Adaptive short delay between successful calls to avoid bursting the API
            try:
                base_delay = float(os.environ.get("SPOTIFY_API_DELAY", str(API_RATE_LIMIT_DELAY)))
            except Exception:
                base_delay = API_RATE_LIMIT_DELAY
            # Multiply by adaptive multiplier (increases when we hit rate limits)
            delay = base_delay * _RATE_BACKOFF_MULTIPLIER
            if delay and delay > 0:
                if _verbose and delay > 0.2:
                    verbose_log(f"  API delay: {delay:.2f}s (backoff multiplier: {_RATE_BACKOFF_MULTIPLIER:.2f})")
                time.sleep(delay)
            # Decay multiplier slowly towards 1.0 on success
            try:
                _RATE_BACKOFF_MULTIPLIER = max(1.0, _RATE_BACKOFF_MULTIPLIER * 0.90)
            except Exception:
                pass
            return result
        except Exception as e:
            status = getattr(e, "http_status", None) or getattr(e, "status", None)
            # Try to find a Retry-After header if present
            retry_after = None
            headers = getattr(e, "headers", None)
            if headers and isinstance(headers, dict):
                retry_after = headers.get("Retry-After") or headers.get("retry-after")
            # Spotipy may include the underlying response in args; try common locations
            if not retry_after and hasattr(e, "args") and e.args:
                try:
                    # args may include a dict with 'headers'
                    for a in e.args:
                        if isinstance(a, dict) and "headers" in a and isinstance(a["headers"], dict):
                            retry_after = a["headers"].get("Retry-After") or a["headers"].get("retry-after")
                            break
                except Exception:
                    pass

            is_rate = status == 429 or (retry_after is not None) or ("rate limit" in str(e).lower())
            is_transient = isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))

            if is_rate or is_transient:
                wait = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                if retry_after:
                    try:
                        wait = max(wait, int(retry_after))
                    except Exception:
                        pass
                log(f"Transient/rate error: {e} — retrying in {wait:.1f}s (attempt {attempt+1}/{max_retries})")
                verbose_log(f"  API call {fn_name}() failed with status {status}, retry_after={retry_after}")
                time.sleep(wait)
                # Increase adaptive multiplier to throttle further successful calls
                try:
                    old_mult = _RATE_BACKOFF_MULTIPLIER
                    _RATE_BACKOFF_MULTIPLIER = min(_RATE_BACKOFF_MAX, _RATE_BACKOFF_MULTIPLIER * 2.0)
                    if _verbose and _RATE_BACKOFF_MULTIPLIER != old_mult:
                        verbose_log(f"  Increased backoff multiplier: {old_mult:.2f} → {_RATE_BACKOFF_MULTIPLIER:.2f}")
                except Exception:
                    pass
                continue

            # Not a retryable error; re-raise
            raise

    # Exhausted retries
    raise RuntimeError(f"API call failed after {max_retries} attempts: {fn}")


def get_spotify_client() -> spotipy.Spotify:
    """
    Get authenticated Spotify client.
    
    Uses refresh token if available (for CI/CD), otherwise interactive auth.
    """
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    refresh_token = os.environ.get("SPOTIPY_REFRESH_TOKEN")
    
    if not all([client_id, client_secret]):
        raise ValueError(
            "Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET. "
            "Set them in environment variables or .env file."
        )
    
    scopes = "user-library-read playlist-modify-private playlist-modify-public playlist-read-private"
    
    if refresh_token:
        # Headless auth using refresh token (for CI/CD)
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scopes
        )
        token_info = auth.refresh_access_token(refresh_token)
        return spotipy.Spotify(auth=token_info["access_token"])
    else:
        # Interactive auth (for local use)
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scopes,
            cache_path=str(DATA_DIR / ".cache")
        )
        return spotipy.Spotify(auth_manager=auth)


# _chunked is now imported as chunked_helper from ..common.api_helpers
# For backward compatibility, create an alias
_chunked = chunked_helper


def _to_uri(track_id: str) -> str:
    """Convert track ID to Spotify URI."""
    track_id = str(track_id)
    if track_id.startswith("spotify:track:"):
        return track_id
    if len(track_id) >= MIN_TRACK_ID_LENGTH and ":" not in track_id:
        return f"spotify:track:{track_id}"
    return track_id


# Global cache for genre data (loaded lazily)
_genre_data_cache = None

def _load_genre_data() -> tuple:
    """Load genre data from parquet files (artists, track_artists). Returns (track_artists, artists) or (None, None) if not available."""
    global _genre_data_cache
    if _genre_data_cache is not None:
        return _genre_data_cache
    
    try:
        track_artists_path = DATA_DIR / "track_artists.parquet"
        artists_path = DATA_DIR / "artists.parquet"
        
        if not (track_artists_path.exists() and artists_path.exists()):
            _genre_data_cache = (None, None)
            return (None, None)
        
        track_artists = pd.read_parquet(track_artists_path)
        artists = pd.read_parquet(artists_path)
        _genre_data_cache = (track_artists, artists)
        return (track_artists, artists)
    except Exception as e:
        verbose_log(f"Failed to load genre data: {e}")
        _genre_data_cache = (None, None)
        return (None, None)

def _uri_to_track_id(track_uri: str) -> str:
    """Extract track ID from track URI."""
    if track_uri.startswith("spotify:track:"):
        return track_uri.replace("spotify:track:", "")
    return track_uri

def _get_genres_from_track_uris(track_uris: list) -> tuple:
    """Get genres from a list of track URIs using cached data.
    
    Returns:
        tuple: (specific_genres_counter, broad_genres_counter)
            - specific_genres_counter: Counter of specific genres (e.g., "trap", "alternative hip hop")
            - broad_genres_counter: Counter of broad genres (e.g., "Hip-Hop", "Electronic")
    """
    from collections import Counter
    from src.features.genres import get_all_broad_genres
    
    track_artists, artists = _load_genre_data()
    if track_artists is None or artists is None:
        return Counter(), Counter()
    
    # Convert URIs to track IDs
    track_ids = [_uri_to_track_id(uri) for uri in track_uris]
    
    # Get artists for these tracks (track -> artists mapping)
    track_artists_subset = track_artists[track_artists['track_id'].isin(track_ids)]
    if len(track_artists_subset) == 0:
        return Counter(), Counter()
    
    # Build track -> artist_ids mapping
    track_to_artists = {}
    for _, row in track_artists_subset.iterrows():
        track_id = row['track_id']
        artist_id = row['artist_id']
        if track_id not in track_to_artists:
            track_to_artists[track_id] = []
        track_to_artists[track_id].append(artist_id)
    
    # Get unique artist IDs
    all_artist_ids = track_artists_subset['artist_id'].unique()
    
    # Get genres from these artists
    artists_subset = artists[artists['artist_id'].isin(all_artist_ids)]
    artist_genres_map = {}
    for idx, row in artists_subset.iterrows():
        artist_id = row['artist_id']
        genres_list = row['genres']
        try:
            if genres_list is None:
                artist_genres_map[artist_id] = []
            elif isinstance(genres_list, (list, tuple)):
                artist_genres_map[artist_id] = list(genres_list) if len(genres_list) > 0 else []
            elif hasattr(genres_list, '__iter__') and not isinstance(genres_list, str):
                artist_genres_map[artist_id] = list(genres_list) if len(list(genres_list)) > 0 else []
            else:
                artist_genres_map[artist_id] = []
        except (TypeError, ValueError, AttributeError):
            artist_genres_map[artist_id] = []
    
    # Count genres per track (each track contributes once per genre)
    specific_genres_counter = Counter()
    broad_genres_counter = Counter()
    
    for track_id, artist_ids in track_to_artists.items():
        # Collect all genres from all artists on this track
        track_genres = set()
        for artist_id in artist_ids:
            track_genres.update(artist_genres_map.get(artist_id, []))
        
        # Count specific genres (each genre counts once per track)
        specific_genres_counter.update(track_genres)
        
        # Get broad genres for this track's genres
        broad_genres = get_all_broad_genres(list(track_genres))
        # Count broad genres (each broad genre counts once per track)
        broad_genres_counter.update(broad_genres)
    
    return specific_genres_counter, broad_genres_counter

def _get_genre_emoji(genre: str) -> str:
    """Get emoji for a genre."""
    genre_lower = genre.lower()
    emoji_map = {
        # Broad genres
        "hip-hop": "🎤",
        "electronic": "🎧",
        "dance": "💃",
        "r&b/soul": "💜",
        "r&b": "💜",
        "soul": "💜",
        "rock": "🎸",
        "pop": "🎶",
        "jazz": "🎷",
        "country/folk": "🌾",
        "country": "🌾",
        "folk": "🌾",
        "classical": "🎻",
        "metal": "⚡",
        "blues": "🎹",
        "latin": "🎊",
        "world": "🌍",
        "indie": "🎨",
        "alternative": "🎵",
        # Specific genres
        "hiphop": "🎤",
        "trap": "🎧",
        "house": "🏠",
        "techno": "⚡",
        "dubstep": "🔊",
        "rap": "🎤",
        "funk": "🎺",
        "disco": "🪩",
        "reggae": "☀️",
        "punk": "🤘",
        "gospel": "✨",
    }
    
    # Check exact match first
    if genre_lower in emoji_map:
        return emoji_map[genre_lower]
    
    # Check partial matches
    for key, emoji in emoji_map.items():
        if key in genre_lower or genre_lower in key:
            return emoji
    
    # Default emoji
    return "🎵"

def _format_genre_tags(specific_genres_counter, broad_genres_counter, max_tags: int = SPOTIFY_MAX_GENRE_TAGS, max_length: int = SPOTIFY_MAX_GENRE_TAG_LENGTH) -> str:
    """Format genre counters as a tag string for playlist description.
    
    Args:
        specific_genres_counter: Counter of specific genres
        broad_genres_counter: Counter of broad genres
        max_tags: Maximum number of tags to include
        max_length: Maximum length of the tag string
    """
    from collections import Counter
    
    if not specific_genres_counter and not broad_genres_counter:
        return ""
    
    # Combine both counters, removing duplicates (prefer broad genre name if same)
    # Sort everything by frequency (popularity)
    combined_items = []
    
    # Add all genres with their counts, preferring broad genre names
    all_genre_names = set(broad_genres_counter.keys()) | set(specific_genres_counter.keys())
    
    for genre in all_genre_names:
        broad_count = broad_genres_counter.get(genre, 0)
        specific_count = specific_genres_counter.get(genre, 0)
        # Use the maximum count (most accurate representation)
        total_count = max(broad_count, specific_count)
        combined_items.append((genre, total_count))
    
    # Sort by frequency (descending), then alphabetically
    combined_items.sort(key=lambda x: (-x[1], x[0]))
    
    # Extract genres in order (sorted by popularity)
    unique_genres = [genre for genre, count in combined_items]
    
    # Limit number of tags and format with emojis
    total_genres = len(unique_genres)
    if total_genres > max_tags:
        unique_genres = unique_genres[:max_tags]
        remaining = total_genres - max_tags
        # Format with emojis
        genre_tags = [f"{_get_genre_emoji(g)} {g}" for g in unique_genres]
        tag_str = ", ".join(genre_tags) + f" (+{remaining} more)"
    else:
        # Format with emojis
        genre_tags = [f"{_get_genre_emoji(g)} {g}" for g in unique_genres]
        tag_str = ", ".join(genre_tags)
    
    # Truncate if still too long
    if len(tag_str) > max_length:
        tag_str = tag_str[:max_length - 10] + "..."
    
    return tag_str

def _add_genre_tags_to_description(current_description: str, track_uris: list, max_tags: int = SPOTIFY_MAX_GENRE_TAGS) -> str:
    """Add or update genre tags in playlist description."""
    # Get genres for tracks (counters)
    specific_genres_counter, broad_genres_counter = _get_genres_from_track_uris(track_uris)
    if not specific_genres_counter and not broad_genres_counter:
        return current_description  # No genres found, return as-is
    
    # Format genre tags
    genre_tags = _format_genre_tags(specific_genres_counter, broad_genres_counter, max_tags=max_tags, max_length=200)
    
    # Use constant from config
    MAX_DESCRIPTION_LENGTH = SPOTIFY_MAX_DESCRIPTION_LENGTH
    
    # Build new description (check for emoji genre tags or "Genres:" pattern)
    # Look for common emoji patterns or "Genres:" prefix
    has_genre_tags = "Genres:" in current_description or any(emoji in current_description for emoji in ["🎤", "🎧", "💃", "💜", "🎸", "🎶", "🎷"])
    
    if has_genre_tags:
        # Replace existing genre tags
        # Try to find where genre tags start (look for emoji or "Genres:")
        lines = current_description.split("\n")
        base_lines = []
        found_genre_start = False
        for line in lines:
            if "Genres:" in line or any(emoji in line for emoji in ["🎤", "🎧", "💃", "💜", "🎸", "🎶", "🎷"]):
                found_genre_start = True
                break
            if line.strip():
                base_lines.append(line)
        
        base_description = "\n".join(base_lines).strip()
        new_description = f"{base_description}\n\n{genre_tags}" if base_description else genre_tags
    else:
        # Append genre tags
        if current_description:
            new_description = f"{current_description}\n\n{genre_tags}"
        else:
            new_description = genre_tags
    
    # Ensure total doesn't exceed limit
    if len(new_description) > MAX_DESCRIPTION_LENGTH:
        # Truncate genre tags if needed
        has_genre_tags = "Genres:" in current_description or any(emoji in current_description for emoji in ["🎤", "🎧", "💃", "💜", "🎸", "🎶", "🎷"])
        if current_description and not has_genre_tags:
            available_space = MAX_DESCRIPTION_LENGTH - len(current_description) - 3
            if available_space > 20:
                genre_tags = _format_genre_tags(specific_genres_counter, broad_genres_counter, max_tags=max_tags, max_length=available_space - 10)
                new_description = f"{current_description}\n\n{genre_tags}"
            else:
                # Not enough space, return original
                return current_description
        else:
            # Just genre tags, truncate
            genre_tags = _format_genre_tags(specific_genres_counter, broad_genres_counter, max_tags=max_tags, max_length=MAX_DESCRIPTION_LENGTH - 10)
            new_description = genre_tags
    
    return new_description

def _update_playlist_description_with_genres(sp: spotipy.Spotify, user_id: str, playlist_id: str, track_uris: list = None) -> bool:
    """Update playlist description with genre tags and rich statistics.
    
    Args:
        sp: Spotify client
        user_id: User ID
        playlist_id: Playlist ID
        track_uris: Optional list of track URIs. If None, gets all tracks from playlist.
    """
    try:
        # Get current description
        pl = api_call(sp.playlist, playlist_id, fields="description,name")
        current_description = pl.get("description", "") or ""
        playlist_name = pl.get("name", "Unknown")
        
        # Get track URIs - use provided ones or fetch all from playlist
        if track_uris is None:
            track_uris = list(get_playlist_tracks(sp, playlist_id, force_refresh=False))
        
        if not track_uris:
            return False  # No tracks, skip
        
        # Add genre tags (basic)
        genre_description = _add_genre_tags_to_description(current_description, track_uris)
        
        # Enhance with rich statistics if enabled
        use_rich_descriptions = _parse_bool_env("ENABLE_RICH_PLAYLIST_DESCRIPTIONS", True)
        if use_rich_descriptions:
            try:
                from .playlist_aesthetics import enhance_playlist_description
                import pandas as pd
                
                # Load data for statistics
                tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
                playlist_tracks_df = pd.read_parquet(DATA_DIR / "playlist_tracks.parquet")
                
                # Extract genre tags from description
                genre_tags = None
                if "Genres:" in genre_description or any(emoji in genre_description for emoji in ["🎤", "🎧", "💃", "💜", "🎸", "🎶", "🎷"]):
                    # Extract genre tags section
                    lines = genre_description.split("\n")
                    for i, line in enumerate(lines):
                        if "Genres:" in line or any(emoji in line for emoji in ["🎤", "🎧", "💃", "💜", "🎸", "🎶", "🎷"]):
                            genre_tags = "\n".join(lines[i:])
                            break
                
                # Enhance description
                enhanced = enhance_playlist_description(
                    sp, playlist_id, current_description,
                    tracks_df, playlist_tracks_df, genre_tags
                )
                new_description = enhanced
            except Exception as e:
                verbose_log(f"  Failed to enhance description with statistics: {e}, using basic description")
                new_description = genre_description
        else:
            new_description = genre_description
        
        # Sanitize and validate description
        MAX_DESCRIPTION_LENGTH = SPOTIFY_MAX_DESCRIPTION_LENGTH
        
        # Ensure description is a string and not None
        if new_description is None:
            new_description = ""
        new_description = str(new_description)
        
        # Remove invalid characters (control characters, but keep newlines and tabs)
        import re
        # Keep printable characters, newlines, tabs, and common Unicode
        new_description = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', new_description)
        
        # Truncate to Spotify's 300 character limit
        if len(new_description) > MAX_DESCRIPTION_LENGTH:
            verbose_log(f"  Warning: Description for '{playlist_name}' is {len(new_description)} chars, truncating to {MAX_DESCRIPTION_LENGTH}")
            # Truncate intelligently - try to preserve important parts
            if "\n" in new_description:
                # Try to keep first line (base description) and truncate rest
                lines = new_description.split("\n")
                if len(lines[0]) <= MAX_DESCRIPTION_LENGTH - 10:
                    remaining = MAX_DESCRIPTION_LENGTH - len(lines[0]) - 5
                    rest = "\n".join(lines[1:])
                    if len(rest) > remaining:
                        rest = rest[:remaining] + "..."
                    new_description = lines[0] + "\n" + rest
                else:
                    new_description = new_description[:MAX_DESCRIPTION_LENGTH - 3] + "..."
            else:
                new_description = new_description[:MAX_DESCRIPTION_LENGTH - 3] + "..."
        
        # Final safety check - ensure we never exceed limit
        if len(new_description) > MAX_DESCRIPTION_LENGTH:
            new_description = new_description[:MAX_DESCRIPTION_LENGTH]
        
        # Ensure description is not empty (Spotify might reject empty descriptions)
        if not new_description.strip():
            verbose_log(f"  Skipping description update for '{playlist_name}' (description would be empty)")
            return False
        
        # Only update if changed
        if new_description != current_description:
            try:
                # Additional validation: ensure description is valid UTF-8
                new_description.encode('utf-8')
                
                api_call(
                    sp.user_playlist_change_details,
                    user_id,
                    playlist_id,
                    description=new_description
                )
                verbose_log(f"  ✅ Updated description for playlist '{playlist_name}' ({len(new_description)} chars)")
                return True
            except UnicodeEncodeError as e:
                verbose_log(f"  ⚠️  Invalid encoding in description for '{playlist_name}': {e}")
                # Try to fix encoding issues
                try:
                    new_description = new_description.encode('utf-8', errors='ignore').decode('utf-8')
                    api_call(
                        sp.user_playlist_change_details,
                        user_id,
                        playlist_id,
                        description=new_description
                    )
                    verbose_log(f"  ✅ Updated description for playlist '{playlist_name}' after encoding fix ({len(new_description)} chars)")
                    return True
                except Exception as e2:
                    verbose_log(f"  ❌ Failed to update description after encoding fix: {e2}")
                    return False
            except Exception as api_error:
                verbose_log(f"  ❌ Failed to update description via API: {api_error}")
                verbose_log(f"  Description length: {len(new_description)}, preview: {new_description[:100]}...")
                # Log first 200 chars for debugging
                verbose_log(f"  Full description (first 200 chars): {repr(new_description[:200])}")
                return False
        return False
    except Exception as e:
        verbose_log(f"  Failed to update description: {e}")
        return False

def _parse_genres(genre_data) -> list:
    """Parse genre data from various formats."""
    # Handle None or empty
    if genre_data is None:
        return []
    # Handle numpy arrays first (before checking truthiness which fails on arrays)
    if isinstance(genre_data, np.ndarray):
        return list(genre_data) if len(genre_data) > 0 else []
    # Handle empty collections
    if not genre_data:
        return []
    if isinstance(genre_data, list):
        return genre_data
    if isinstance(genre_data, str):
        try:
            return ast.literal_eval(genre_data)
        except (ValueError, SyntaxError):
            return [genre_data]
    return []


def _get_all_track_genres(track_id: str, track_artists: pd.DataFrame, artist_genres_map: dict) -> list:
    """Get all genres from all artists on a track.
    
    Collects genres from ALL artists on the track (not just the primary artist)
    to get more complete genre information for better classification.
    
    Args:
        track_id: The track ID
        track_artists: DataFrame with track_id and artist_id columns
        artist_genres_map: Dictionary mapping artist_id to genres list
    
    Returns:
        Combined list of all unique genres from all artists on the track
    """
    # Get all artists for this track
    track_artist_rows = track_artists[track_artists["track_id"] == track_id]
    
    # Collect all genres from all artists
    all_genres = []
    for _, row in track_artist_rows.iterrows():
        artist_id = row["artist_id"]
        artist_genres = _parse_genres(artist_genres_map.get(artist_id, []))
        all_genres.extend(artist_genres)
    
    # Return unique genres while preserving order
    seen = set()
    unique_genres = []
    for genre in all_genres:
        if genre not in seen:
            seen.add(genre)
            unique_genres.append(genre)
    
    return unique_genres


# ============================================================================
# FORMATTING HELPERS
# ============================================================================

def _get_separator(sep_type: str) -> str:
    """Get separator character based on type."""
    sep_map = {
        "none": "",
        "space": " ",
        "dash": "-",
        "underscore": "_",
    }
    return sep_map.get(sep_type.lower(), "")


def _format_date(month_str: str = None, year: str = None) -> tuple:
    """
    Format date components based on DATE_FORMAT setting.
    
    Returns:
        (month_str, year_str) tuple with formatted components
    """
    mon = ""
    year_str = ""
    
    if month_str:
        parts = month_str.split("-")
        full_year = parts[0] if len(parts) >= 1 else ""
        month_num = parts[1] if len(parts) >= 2 else ""
        
        if DATE_FORMAT == "numeric":
            mon = month_num
            year_str = full_year
        elif DATE_FORMAT == "medium":
            mon = MONTH_NAMES_MEDIUM.get(month_num, month_num)
            year_str = full_year
        elif DATE_FORMAT == "long":
            mon = MONTH_NAMES_MEDIUM.get(month_num, month_num)
            year_str = full_year
        else:  # short (default)
            mon = MONTH_NAMES_SHORT.get(month_num, month_num)
            year_str = full_year[2:] if len(full_year) == 4 else full_year
    elif year:
        # Handle year parameter if provided directly
        if DATE_FORMAT == "numeric":
            year_str = year
        else:
            year_str = year[2:] if len(year) == 4 else year
    
    # Apply separator between month and year if both present
    if mon and year_str and SEPARATOR_MONTH != "none":
        sep = _get_separator(SEPARATOR_MONTH)
        if DATE_FORMAT == "medium" or DATE_FORMAT == "long":
            # For medium/long, add space before year: "November 2024"
            mon = f"{mon}{sep}{year_str}"
            year_str = ""  # Year is now part of mon
        else:
            # For short/numeric, keep them separate for template
            pass
    
    return mon, year_str


def _apply_capitalization(text: str) -> str:
    """Apply capitalization style to text."""
    if CAPITALIZATION == "upper":
        return text.upper()
    elif CAPITALIZATION == "lower":
        return text.lower()
    elif CAPITALIZATION == "title":
        return text.title()
    else:  # preserve
        return text


def format_playlist_name(template: str, month_str: str = None, genre: str = None, 
                         prefix: str = None, playlist_type: str = "monthly", year: str = None) -> str:
    """Format playlist name from template.
    
    Args:
        template: Template string with placeholders
        month_str: Month string like '2025-01' (optional)
        genre: Genre name (optional)
        prefix: Override prefix (optional, uses type-specific prefix if not provided)
        playlist_type: Type of playlist to determine prefix ("monthly", "genre_monthly", 
                      "yearly", "genre_master", "most_played", "time_based", "repeat", "discovery")
    """
    # Determine prefix based on playlist type if not provided
    if prefix is None:
        prefix_map = {
            "monthly": PREFIX_MONTHLY,
            "genre_monthly": PREFIX_GENRE_MONTHLY,
            "yearly": PREFIX_YEARLY,
            "genre_master": PREFIX_GENRE_MASTER,
            "most_played": PREFIX_MOST_PLAYED,
            # "time_based": PREFIX_TIME_BASED,  # Vibes removed
            # "repeat": PREFIX_REPEAT,  # OnRepeat removed
            "discovery": PREFIX_DISCOVERY,
        }
        prefix = prefix_map.get(playlist_type, BASE_PREFIX)
    
    # Format date components
    mon, year_str = _format_date(month_str, year)
    
    # Check if month already includes year (for medium/long formats)
    month_includes_year = (DATE_FORMAT == "medium" or DATE_FORMAT == "long") and mon and not year_str
    
    # Build components (before capitalization)
    owner = OWNER_NAME
    prefix_str = prefix
    genre_str = genre or ""
    
    # Apply capitalization
    owner = _apply_capitalization(owner)
    prefix_str = _apply_capitalization(prefix_str)
    genre_str = _apply_capitalization(genre_str)
    mon = _apply_capitalization(mon)
    year_str = _apply_capitalization(year_str)
    
    # Apply separators before formatting
    prefix_sep = _get_separator(SEPARATOR_PREFIX)
    month_sep = _get_separator(SEPARATOR_MONTH) if mon and year_str and not month_includes_year else ""
    
    # Build formatted components with separators
    if SEPARATOR_PREFIX != "none" and prefix_str:
        # Add separator between owner and prefix if both present
        owner_prefix = f"{owner}{prefix_sep}{prefix_str}" if owner else prefix_str
    else:
        owner_prefix = f"{owner}{prefix_str}" if owner else prefix_str
    
    # Handle month/year separator
    date_includes_year = False
    if month_includes_year:
        # Month already includes year (e.g., "November 2024")
        date_part = mon
        date_includes_year = True
    elif mon and year_str:
        # Add separator between month and year
        # FIX: Always include year_str in date_part, even if month_sep is empty
        if month_sep:
            date_part = f"{mon}{month_sep}{year_str}"
        else:
            date_part = f"{mon}{year_str}"
        # FIX: date_part now includes the year, so set date_includes_year = True
        # This prevents {year} placeholder from being replaced with year_str again
        date_includes_year = True
    elif mon:
        date_part = mon
        date_includes_year = False  # No year in date_part
    elif year_str:
        # Only year, no month - keep them separate for template replacement
        date_part = ""
        date_includes_year = False  # Year should be replaced separately in template
    else:
        date_part = ""
        date_includes_year = False
    
    # Format the name using components
    # Replace template placeholders with formatted components
    formatted = template
    formatted = formatted.replace("{owner}", owner)
    formatted = formatted.replace("{prefix}", prefix_str)
    formatted = formatted.replace("{genre}", genre_str)
    formatted = formatted.replace("{mon}", date_part if (mon or month_includes_year) else "")
    # FIX: Only replace {year} if date_part doesn't already include it
    # This prevents duplicate years (e.g., "AJFindsJan2626" should be "AJFindsJan26")
    if date_includes_year:
        # Year is already included in date_part, replace {year} with empty string to avoid duplication
        formatted = formatted.replace("{year}", "")
    else:
        # Year should be replaced separately in template (no month, or only year)
        formatted = formatted.replace("{year}", year_str if year_str else "")
    
    # If template uses {owner}{prefix} pattern, replace with combined version
    if "{owner}{prefix}" in template or (owner and prefix_str and owner_prefix != f"{owner}{prefix_str}"):
        # Try to replace owner+prefix combination
        formatted = formatted.replace(f"{owner}{prefix_str}", owner_prefix)
    
    return formatted


def format_playlist_description(description: str, period: str = None, date: str = None, 
                                playlist_type: str = None, genre: str = None) -> str:
    """
    Format playlist description using template.
    
    Args:
        description: Base description text
        period: Period string (e.g., "Nov 2024", "2024")
        date: Specific date string
        playlist_type: Type of playlist
        genre: Genre name
    
    Returns:
        Formatted description string
    """
    return DESCRIPTION_TEMPLATE.format(
        description=description or "",
        period=period or "",
        date=date or "",
        type=playlist_type or "",
        genre=genre or ""
    )


def format_yearly_playlist_name(year: str) -> str:
    """Format yearly playlist name like 'AJFinds2025'."""
    # Handle both 4-digit and 2-digit years
    if len(year) == 4:
        year_short = year[2:]
    else:
        year_short = year
    
    return format_playlist_name(YEARLY_NAME_TEMPLATE, year=year_short, playlist_type="yearly")


# ============================================================================
# SPOTIFY API HELPERS (with smart caching)
# ============================================================================

# In-memory caches (per-run, invalidated when needed)
_playlist_cache: dict = None  # {name: id}
_playlist_tracks_cache: dict = {}  # {playlist_id: set of URIs}
_user_cache: dict = None  # user info
_playlist_cache_valid = False

def _invalidate_playlist_cache():
    """Invalidate playlist and playlist tracks cache (call after modifying playlists)."""
    global _playlist_cache, _playlist_tracks_cache, _playlist_cache_valid
    _playlist_cache = None
    _playlist_tracks_cache = {}
    _playlist_cache_valid = False

def get_existing_playlists(sp: spotipy.Spotify, force_refresh: bool = False) -> dict:
    """Get all user playlists as {name: id} mapping.
    
    Cached in-memory for the duration of the run. Call _invalidate_playlist_cache()
    after modifying playlists (creating/deleting) to ensure fresh data.
    """
    global _playlist_cache, _playlist_cache_valid
    
    if _playlist_cache is not None and not force_refresh and _playlist_cache_valid:
        verbose_log(f"Using cached playlists ({len(_playlist_cache)} playlists)")
        return _playlist_cache
    
    verbose_log(f"Fetching playlists from API (force_refresh={force_refresh})...")
    
    mapping = {}
    offset = 0
    while True:
        page = api_call(sp.current_user_playlists, limit=SPOTIFY_API_PAGINATION_LIMIT, offset=offset)
        for item in page.get("items", []):
            mapping[item["name"]] = item["id"]
        if not page.get("next"):
            break
        offset += SPOTIFY_API_PAGINATION_LIMIT
    
    _playlist_cache = mapping
    _playlist_cache_valid = True
    return mapping


def get_playlist_tracks(sp: spotipy.Spotify, playlist_id: str, force_refresh: bool = False) -> set:
    """Get all track URIs in a playlist.
    
    Cached in-memory for the duration of the run. Cache is automatically
    invalidated for a playlist when tracks are added to it.
    """
    global _playlist_tracks_cache
    
    if playlist_id in _playlist_tracks_cache and not force_refresh:
        verbose_log(f"Using cached tracks for playlist {playlist_id} ({len(_playlist_tracks_cache[playlist_id])} tracks)")
        return _playlist_tracks_cache[playlist_id]
    
    verbose_log(f"Fetching tracks for playlist {playlist_id} from API (force_refresh={force_refresh})...")
    
    uris = set()
    offset = 0
    while True:
        page = api_call(
            sp.playlist_items,
            playlist_id,
            fields="items(track(uri)),next",
            limit=SPOTIFY_API_MAX_TRACKS_PER_REQUEST,
            offset=offset,
        )
        for item in page.get("items", []):
            if item.get("track", {}).get("uri"):
                uris.add(item["track"]["uri"])
        if not page.get("next"):
            break
        offset += 100
    
    _playlist_tracks_cache[playlist_id] = uris
    return uris


def get_user_info(sp: spotipy.Spotify, force_refresh: bool = False) -> dict:
    """Get current user info (cached in-memory)."""
    global _user_cache
    
    if _user_cache is not None and not force_refresh:
        return _user_cache
    
    _user_cache = api_call(sp.current_user)
    return _user_cache


# ============================================================================
# DATA SYNC FUNCTIONS
# ============================================================================

def compute_track_genres_incremental(stats: dict = None) -> None:
    """Compute and store track genres with smart caching.
    
    Only re-infers genres for tracks that have changed:
    - New tracks (not yet inferred)
    - Tracks in playlists that were updated
    - Tracks whose artists had genres enhanced
    
    This dramatically improves sync runtime by avoiding unnecessary computation.
    """
    log("\n--- Computing Track Genres (Smart Caching) ---")
    
    try:
        # Load all data (with caching to avoid repeated reads)
        tracks_path = DATA_DIR / "tracks.parquet"
        track_artists_path = DATA_DIR / "track_artists.parquet"
        artists_path = DATA_DIR / "artists.parquet"
        playlist_tracks_path = DATA_DIR / "playlist_tracks.parquet"
        playlists_path = DATA_DIR / "playlists.parquet"
        
        if not all(p.exists() for p in [tracks_path, track_artists_path, artists_path, playlist_tracks_path, playlists_path]):
            log("  ⚠️  Missing required data files, skipping genre computation")
            return
        
        # Check file modification times for smart caching
        playlist_tracks_mtime = playlist_tracks_path.stat().st_mtime if playlist_tracks_path.exists() else 0
        playlists_mtime = playlists_path.stat().st_mtime if playlists_path.exists() else 0
        
        # Load parquet files (use engine='pyarrow' for faster reads if available)
        verbose_log(f"Loading parquet files from {DATA_DIR}...")
        try:
            verbose_log("  Attempting to load with pyarrow engine...")
            tracks = pd.read_parquet(tracks_path, engine='pyarrow')
            verbose_log(f"    Loaded tracks: {len(tracks):,} rows")
            track_artists = pd.read_parquet(track_artists_path, engine='pyarrow')
            verbose_log(f"    Loaded track_artists: {len(track_artists):,} rows")
            artists = pd.read_parquet(artists_path, engine='pyarrow')
            verbose_log(f"    Loaded artists: {len(artists):,} rows")
            playlist_tracks = pd.read_parquet(playlist_tracks_path, engine='pyarrow')
            verbose_log(f"    Loaded playlist_tracks: {len(playlist_tracks):,} rows")
            playlists = pd.read_parquet(playlists_path, engine='pyarrow')
            verbose_log(f"    Loaded playlists: {len(playlists):,} rows")
        except Exception as e:
            # Fallback to default engine if pyarrow not available
            verbose_log(f"  PyArrow not available, using default engine: {e}")
            tracks = pd.read_parquet(tracks_path)
            verbose_log(f"    Loaded tracks: {len(tracks):,} rows")
            track_artists = pd.read_parquet(track_artists_path)
            verbose_log(f"    Loaded track_artists: {len(track_artists):,} rows")
            artists = pd.read_parquet(artists_path)
            verbose_log(f"    Loaded artists: {len(artists):,} rows")
            playlist_tracks = pd.read_parquet(playlist_tracks_path)
            verbose_log(f"    Loaded playlist_tracks: {len(playlist_tracks):,} rows")
            playlists = pd.read_parquet(playlists_path)
            verbose_log(f"    Loaded playlists: {len(playlists):,} rows")
        
        # Check if genres column exists, if not create it
        if "genres" not in tracks.columns:
            tracks["genres"] = None
        
        # Determine which tracks need genre inference
        tracks_needing_inference = set()
        
        # 1. Tracks without genres
        def needs_genres(genres_val):
            """Check if track needs genre inference."""
            # Handle None
            if genres_val is None:
                return True
            
            # Handle numpy arrays first (before checking isna which fails on arrays)
            if isinstance(genres_val, np.ndarray):
                return len(genres_val) == 0
            
            # Check if it's a list
            if isinstance(genres_val, list):
                return len(genres_val) == 0
            
            # Check if NaN (but only for scalar values, use try-except to handle arrays)
            try:
                # First check if it's a scalar by trying to use pd.isna
                scalar_check = pd.api.types.is_scalar(genres_val)
                if scalar_check:
                    if pd.isna(genres_val):
                        return True
            except (ValueError, TypeError):
                # If isna fails (e.g., on arrays), continue to next check
                pass
            
            # For other types (including arrays), try to check length
            try:
                if hasattr(genres_val, '__len__'):
                    return len(genres_val) == 0
            except (TypeError, AttributeError):
                pass
            
            # Unknown type or couldn't determine - treat as needing genres
            return True
        
        tracks_without_genres = tracks[tracks["genres"].apply(needs_genres)]
        tracks_needing_inference.update(tracks_without_genres["track_id"].tolist())
        
        # 2. New tracks added in this sync (if stats provided)
        if stats and stats.get("tracks_added", 0) > 0:
            # Find tracks in playlist_tracks that don't have genres yet
            playlist_track_ids = set(playlist_tracks["track_id"].unique())
            # Helper function to check if track has valid genres
            def has_valid_genres(genres_val):
                if genres_val is None or pd.isna(genres_val):
                    return False
                if isinstance(genres_val, list):
                    return len(genres_val) > 0
                return False
            
            tracks_with_genres = set(tracks[tracks["genres"].apply(has_valid_genres)]["track_id"].tolist())
            new_track_ids = playlist_track_ids - tracks_with_genres
            tracks_needing_inference.update(new_track_ids)
        
        total_tracks = len(tracks)
        needs_inference = len(tracks_needing_inference)
        already_has_genres = total_tracks - needs_inference
        
        if needs_inference == 0:
            log(f"  ✅ All {total_tracks:,} tracks already have genres (smart cache hit)")
            return
        
        log(f"  📊 Genre status: {already_has_genres:,} cached, {needs_inference:,} need inference")
        
        # Only enhance artist genres if playlists changed (smart caching)
        # Skip if most tracks already have genres (enhancement is expensive and not needed)
        if stats and (stats.get("playlists_updated", 0) > 0 or stats.get("tracks_added", 0) > 0):
            # Quick check: if we already have most tracks with genres, skip enhancement
            # (it's expensive - iterates through all artists and playlists)
            tracks_with_genres_pct = (already_has_genres / total_tracks * 100) if total_tracks > 0 else 0
            if tracks_with_genres_pct < 90:
                # Less than 90% have genres - enhancement might help
                # But limit to reasonable number of artists to avoid timeout
                artists_without_genres = artists[artists["genres"].apply(
                    lambda g: g is None or (isinstance(g, list) and len(g) == 0) or 
                    (pd.api.types.is_scalar(g) and pd.isna(g))
                )]
                
                if len(artists_without_genres) > 500:
                    log(f"  ⏭️  Skipping artist genre enhancement (too many artists without genres: {len(artists_without_genres):,})")
                else:
                    tqdm.write("  🔄 Enhancing artist genres from playlist patterns...")
                    artists_before = artists.copy()
                    artists_enhanced = enhance_artist_genres_from_playlists(
                        artists, track_artists, playlist_tracks, playlists
                    )
                    
                    # Check if any artists had their genres enhanced
                    enhanced_artist_ids = set()
                    artists_dict_before = artists_before.set_index("artist_id")["genres"].to_dict()
                    artists_dict_after = artists_enhanced.set_index("artist_id")["genres"].to_dict()
                    
                    for artist_id in artists_dict_after.keys():
                        old_genres = set(_parse_genres(artists_dict_before.get(artist_id, [])))
                        new_genres = set(_parse_genres(artists_dict_after.get(artist_id, [])))
                        if old_genres != new_genres:
                            enhanced_artist_ids.add(artist_id)
                    
                    if enhanced_artist_ids:
                        # Save enhanced artists back
                        artists_enhanced.to_parquet(artists_path, index=False)
                        artists = artists_enhanced
                        # Re-infer genres for tracks by enhanced artists
                        enhanced_track_ids = track_artists[track_artists["artist_id"].isin(enhanced_artist_ids)]["track_id"].unique()
                        tracks_needing_inference.update(enhanced_track_ids)
                        tqdm.write(f"  ✨ Enhanced {len(enhanced_artist_ids)} artists - re-inferring {len(enhanced_track_ids)} tracks")
                    else:
                        artists = artists_enhanced  # Use enhanced even if no changes (for consistency)
            else:
                log(f"  ⏭️  Skipping artist genre enhancement ({tracks_with_genres_pct:.1f}% tracks already have genres)")
        else:
            log("  ⏭️  Skipping artist genre enhancement (no playlist changes)")
        
        # Filter to only tracks that need inference
        tracks_to_process = tracks[tracks["track_id"].isin(tracks_needing_inference)]
        
        if len(tracks_to_process) == 0:
            log(f"  ✅ All tracks up to date (smart cache hit)")
            return
        
        tqdm.write(f"  🔄 Inferring genres for {len(tracks_to_process):,} track(s)...")
        
        # Use parallel processing for genre inference (major performance boost)
        num_workers = int(os.environ.get("GENRE_INFERENCE_WORKERS", min(mp.cpu_count() or 4, 8)))
        use_parallel = _parse_bool_env("USE_PARALLEL_GENRE_INFERENCE", True) and len(tracks_to_process) > PARALLEL_MIN_TRACKS
        
        # Prepare track data list for processing
        track_data_list = [
            {
                'track_id': row.track_id,
                'track_name': getattr(row, 'name', None),
                'album_name': getattr(row, 'album_name', None),
            }
            for row in tracks_to_process.itertuples()
        ]
        
        inferred_genres_map = {}
        
        if use_parallel and num_workers > 1:
            tqdm.write(f"  🚀 Using {num_workers} parallel workers for genre inference...")
            verbose_log(f"Parallel processing enabled with {num_workers} workers")
            verbose_log(f"Processing {len(track_data_list)} tracks in parallel")
            
            # Worker function that processes a single track
            # Uses ThreadPoolExecutor which can access the full DataFrames in memory
            def _process_track(track_data):
                """Process a single track's genre inference."""
                try:
                    track_id = track_data['track_id']
                    track_name = track_data['track_name']
                    album_name = track_data['album_name']
                    
                    genres = infer_genres_comprehensive(
                        track_id=track_id,
                        track_name=track_name,
                        album_name=album_name,
                        track_artists=track_artists,
                        artists=artists,
                        playlist_tracks=playlist_tracks,
                        playlists=playlists,
                        mode="split"
                    )
                    return (track_id, genres)
                except Exception as e:
                    # Return empty genres on error to avoid blocking
                    return (track_data.get('track_id', ''), [])
            
            # Use ThreadPoolExecutor for parallel processing
            # ThreadPoolExecutor shares memory, avoiding pickle overhead with DataFrames
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                # Submit all tasks
                futures = {executor.submit(_process_track, track_data): track_data['track_id'] 
                          for track_data in track_data_list}
                
                # Process completed tasks with progress bar
                with tqdm(total=len(track_data_list), desc="  Inferring genres", unit="track", 
                         ncols=100, leave=False) as pbar:
                    for future in as_completed(futures):
                        try:
                            track_id, genres = future.result(timeout=30)  # 30s timeout per track
                            inferred_genres_map[track_id] = genres
                        except Exception as e:
                            track_id = futures[future]
                            tqdm.write(f"  ⚠️  Error inferring genres for {track_id}: {e}")
                            inferred_genres_map[track_id] = []
                        finally:
                            pbar.update(1)
        else:
            verbose_log(f"Sequential processing (parallel disabled or small batch: {len(track_data_list)} tracks)")
            # Sequential processing for small batches or when parallel is disabled
            track_iterator = tracks_to_process.itertuples()
            if len(tracks_to_process) > 0:
                track_iterator = tqdm(
                    track_iterator,
                    total=len(tracks_to_process),
                    desc="  Inferring genres",
                    unit="track",
                    ncols=100,
                    leave=False
                )
            
            for track_row in track_iterator:
                track_id = track_row.track_id
                track_name = getattr(track_row, 'name', None)
                album_name = getattr(track_row, 'album_name', None)
                
                try:
                    genres = infer_genres_comprehensive(
                        track_id=track_id,
                        track_name=track_name,
                        album_name=album_name,
                        track_artists=track_artists,
                        artists=artists,
                        playlist_tracks=playlist_tracks,
                        playlists=playlists,
                        mode="split"  # Use split genres for tracks
                    )
                    inferred_genres_map[track_id] = genres
                except Exception as e:
                    tqdm.write(f"  ⚠️  Error inferring genres for {track_id}: {e}")
                    inferred_genres_map[track_id] = []
        
        # Update tracks with inferred genres (optimized batch update)
        if inferred_genres_map:
            tqdm.write("  💾 Updating track genres...")
            # Build index map for faster lookups (O(1) instead of O(n) per lookup)
            # Create a mapping from track_id to DataFrame index
            track_id_to_row_idx = {}
            for idx, track_id in tracks['track_id'].items():
                if track_id in inferred_genres_map:
                    track_id_to_row_idx[track_id] = idx
            
            # Batch update using .at for efficient single-cell updates
            for track_id, genres in inferred_genres_map.items():
                if track_id in track_id_to_row_idx:
                    tracks.at[track_id_to_row_idx[track_id], "genres"] = genres
            
            # Save updated tracks (use pyarrow engine for faster writes if available)
            try:
                tracks.to_parquet(tracks_path, index=False, engine='pyarrow')
            except Exception:
                tracks.to_parquet(tracks_path, index=False)
        
        # Count tracks with valid genres (avoiding pandas array ambiguity)
        def has_valid_genre(g):
            if g is None:
                return False
            try:
                if pd.api.types.is_scalar(g):
                    if pd.isna(g):
                        return False
                if isinstance(g, list):
                    return len(g) > 0
                if isinstance(g, (np.ndarray, pd.Series)):
                    return len(g) > 0
                return bool(g)
            except (ValueError, TypeError):
                return False
        
        tracks_with_genres_after = tracks["genres"].apply(has_valid_genre).sum()
        log(f"  ✅ Inferred genres for {len(inferred_genres_map):,} track(s) ({tracks_with_genres_after:,} total tracks with genres)")
        
    except Exception as e:
        log(f"  ⚠️  Genre inference error (non-fatal): {e}")
        import traceback
        traceback.print_exc()


def sync_full_library(force: bool = False) -> bool:
    """
    Sync full library using spotim8 - updates all parquet files.
    
    Uses incremental sync - only fetches playlists that have changed
    based on Spotify's snapshot_id mechanism.
    
    Updates:
    - playlists.parquet
    - playlist_tracks.parquet  
    - tracks.parquet (with genres column)
    - track_artists.parquet
    - artists.parquet (enhanced with inferred genres)
    """
    log("\n--- Full Library Sync ---")
    
    try:
        # Enable API response caching
        api_cache_dir = DATA_DIR / ".api_cache"
        set_response_cache(api_cache_dir, ttl=3600)
        
        # Initialize client
        sf = Spotim8.from_env(
            progress=True,
            cache=CacheConfig(dir=DATA_DIR)
        )
        
        # Check for existing cached data
        existing_status = sf.status()
        if existing_status.get("playlist_tracks_count", 0) > 0:
            log(f"📦 Found cached data from {existing_status.get('last_sync', 'unknown')}")
            log(f"   • {existing_status.get('playlists_count', 0):,} playlists")
            log(f"   • {existing_status.get('playlist_tracks_count', 0):,} playlist tracks")
            log(f"   • {existing_status.get('tracks_count', 0):,} unique tracks")
            log(f"   • {existing_status.get('artists_count', 0):,} artists")
            log("🔄 Running incremental sync (only changed playlists)...")
            verbose_log(f"Cache directory: {DATA_DIR}")
            verbose_log(f"API cache directory: {api_cache_dir}")
        else:
            log("📭 No cached data found - running full sync...")
            verbose_log(f"Cache directory: {DATA_DIR}")
            verbose_log(f"API cache directory: {api_cache_dir}")
        
        # Sync library (incremental - only fetches changes based on snapshot_id)
        # Note: We use owned_only=True for playlist_tracks to avoid syncing all followed playlist contents,
        # but we still sync all playlists (owned + followed) metadata so we can learn from their names/descriptions
        with timed_step("Spotify Library Sync (API calls)"):
            stats = sf.sync(
                force=force,  # Force full sync if True, otherwise incremental
                owned_only=True,  # Only sync tracks from owned playlists (faster)
                include_liked_songs=True
            )
        
        with timed_step("Load All Playlists"):
            # Ensure we have ALL playlists (owned + followed) for genre inference
            # This allows us to learn from followed playlist names/descriptions
            # The sync() call above already loads all playlists, but we ensure they're fresh
            _ = sf.playlists(force=force)  # Load all playlists including followed (uses cache if fresh, or force if requested)
        
        log(f"✅ Library sync complete: {stats}")
        
        # Only regenerate derived tables if something changed
        if stats.get("playlists_updated", 0) > 0 or stats.get("tracks_added", 0) > 0:
            with timed_step("Regenerate Derived Tables"):
                log("🔧 Regenerating derived tables...")
                verbose_log(f"Stats: {stats}")
                verbose_log("Loading tracks table...")
                _ = sf.tracks()
                verbose_log("Loading artists table...")
                _ = sf.artists()
                verbose_log("Loading library_wide table...")
                _ = sf.library_wide()
                log("✅ All parquet files updated")
        else:
            log("✅ No changes detected - using cached derived tables")
            verbose_log(f"Stats: {stats}")
        
        # Compute track genres with smart caching - only processes changed tracks
        # This dramatically improves sync runtime by avoiding unnecessary computation
        # Skip entirely if all tracks already have genres (common case after initial sync)
        # Only run genre inference if there were actual changes or tracks need inference
        # Skip if no tracks were added/updated (fast path optimization)
        if stats and stats.get("tracks_added", 0) == 0 and stats.get("playlists_updated", 0) == 0:
            log("  ⏭️  Skipping genre inference (no changes detected - using cached data)")
        else:
            with timed_step("Genre Inference Check"):
                try:
                    # Use faster parquet read with pyarrow if available
                    try:
                        verbose_log(f"Loading tracks.parquet with pyarrow engine...")
                        tracks_check = pd.read_parquet(DATA_DIR / "tracks.parquet", engine='pyarrow')
                        verbose_log(f"Loaded {len(tracks_check):,} tracks using pyarrow")
                    except Exception:
                        verbose_log(f"Loading tracks.parquet with default engine (pyarrow not available)...")
                        tracks_check = pd.read_parquet(DATA_DIR / "tracks.parquet")
                        verbose_log(f"Loaded {len(tracks_check):,} tracks using default engine")
                    
                    tracks_needing = tracks_check[tracks_check["genres"].apply(
                        lambda g: g is None or (isinstance(g, list) and len(g) == 0) or 
                        (pd.api.types.is_scalar(g) and pd.isna(g))
                    )]
                    if len(tracks_needing) == 0:
                        log("  ⏭️  Skipping genre inference (all tracks already have genres)")
                    else:
                        # Check if genre inference is enabled and within limits
                        max_tracks_for_inference = int(os.environ.get("MAX_TRACKS_FOR_INFERENCE", "10000"))
                        enable_inference = _parse_bool_env("ENABLE_GENRE_INFERENCE", True)
                        
                        if not enable_inference:
                            log(f"  ⏭️  Skipping genre inference (disabled via ENABLE_GENRE_INFERENCE)")
                        elif len(tracks_needing) > max_tracks_for_inference:
                            log(f"  ⏭️  Skipping genre inference ({len(tracks_needing):,} tracks need inference - exceeds limit of {max_tracks_for_inference:,})")
                            log(f"      Set MAX_TRACKS_FOR_INFERENCE env var to increase limit")
                        else:
                            # Process genre inference
                            with timed_step("Genre Inference Processing"):
                                log(f"  🔄 Processing genre inference for {len(tracks_needing):,} tracks...")
                                compute_track_genres_incremental(stats)
                except Exception as e:
                    # If check fails, skip to avoid blocking
                    log(f"  ⏭️  Skipping genre inference (error: {e})")
        
        # Sync export data (Account Data, Extended History, Technical Logs)
        # Wrap in try-except to prevent export data sync from stopping the script
        # Export data sync can be slow or fail on large files, so we make it non-fatal
        with timed_step("Sync Export Data"):
            try:
                log("  🔄 Starting export data sync...")
                sync_export_data()
                log("  ✅ Export data sync completed")
            except KeyboardInterrupt:
                log("  ⚠️  Export data sync interrupted by user")
                raise  # Re-raise to allow proper cleanup
            except Exception as e:
                log(f"  ⚠️  Export data sync error (non-fatal, continuing): {e}")
                import traceback
                log(traceback.format_exc())
                # Continue execution - export data sync is optional
        
        return True
        
    except Exception as e:
        log(f"ERROR: Full library sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def sync_export_data() -> bool:
    """
    Sync all Spotify export data (Account Data, Extended History, Technical Logs).
    
    Updates:
    - streaming_history.parquet
    - search_queries.parquet
    - wrapped_data.json
    - follow_data.parquet
    - library_snapshot.parquet
    - playback_errors.parquet
    - playback_retries.parquet
    - webapi_events.parquet
    """
    log("\n--- Export Data Sync ---")
    
    try:
        # Find export folders in data directory
        account_data_dir = DATA_DIR / "Spotify Account Data"
        extended_history_dir = DATA_DIR / "Spotify Extended Streaming History"
        technical_log_dir = DATA_DIR / "Spotify Technical Log Information"
        
        # Check if any export folders exist
        if not any([account_data_dir.exists(), extended_history_dir.exists(), technical_log_dir.exists()]):
            log("ℹ️  No export folders found - skipping export data sync")
            log(f"   Place export folders in {DATA_DIR} to enable:")
            log("   - Spotify Account Data/")
            log("   - Spotify Extended Streaming History/")
            log("   - Spotify Technical Log Information/")
            return True
        
        # Sync all export data
        results = sync_all_export_data(
            account_data_dir=account_data_dir if account_data_dir.exists() else Path("/tmp"),
            extended_history_dir=extended_history_dir if extended_history_dir.exists() else Path("/tmp"),
            technical_log_dir=technical_log_dir if technical_log_dir.exists() else Path("/tmp"),
            data_dir=DATA_DIR,
            force=False
        )
        
        # Log summary
        log("\n📊 Export Data Sync Summary:")
        for key, value in results.items():
            if value is not None and value is not False:
                if isinstance(value, int):
                    log(f"   ✅ {key}: {value:,} records")
                else:
                    log(f"   ✅ {key}: synced")
            else:
                log(f"   ⚠️  {key}: not available")
        
        return True
        
    except Exception as e:
        log(f"❌ Export data sync failed: {e}")
        import traceback
        log(traceback.format_exc())
        return False


# ============================================================================
# PLAYLIST UPDATE FUNCTIONS
# ============================================================================

def rename_playlists_with_old_prefixes(sp: spotipy.Spotify) -> None:
    """Rename playlists that use old prefixes to match new prefix configuration.
    
    This handles migration from old prefix names (e.g., "Auto", "AJAuto") to new
    prefix-based naming (e.g., "Finds", "AJFnds").
    
    Common old prefix patterns:
    - "Auto" -> MONTHLY prefix (e.g., "Fnds")
    - "Top" -> MOST_PLAYED prefix (if changed)
    - "Vibes" -> removed (no longer supported)
    - "OnRepeat" or "Repeat" -> removed (no longer supported)
    - "Discover" or "Discovery" -> DISCOVERY prefix (if changed)
    """
    log("\n--- Renaming Playlists with Old Prefixes ---")
    
    existing = get_existing_playlists(sp, force_refresh=True)
    user = get_user_info(sp)
    user_id = user["id"]
    
    # Build mapping of old prefixes to new prefixes
    # Only include mappings where the prefix actually changed
    old_to_new = {}
    
    # Check "Auto" -> monthly prefix
    if PREFIX_MONTHLY != "Auto" and PREFIX_MONTHLY != "auto":
        old_to_new["Auto"] = PREFIX_MONTHLY
        old_to_new["auto"] = PREFIX_MONTHLY.lower()
        old_to_new["AUTO"] = PREFIX_MONTHLY.upper()
    
    # Check other prefixes if they changed (less common, but handle them)
    if PREFIX_MOST_PLAYED != "Top":
        old_to_new["Top"] = PREFIX_MOST_PLAYED
    # Vibes removed - no longer supported
    # if PREFIX_TIME_BASED != "Vibes":
    #     old_to_new["Vibes"] = PREFIX_TIME_BASED
    # OnRepeat removed - no longer supported
    # if PREFIX_REPEAT not in ["OnRepeat", "Repeat", "Rpt"]:
    #     old_to_new["OnRepeat"] = PREFIX_REPEAT
    #     old_to_new["Repeat"] = PREFIX_REPEAT
    if PREFIX_DISCOVERY not in ["Discover", "Discovery", "Dscvr"]:
        old_to_new["Discover"] = PREFIX_DISCOVERY
        old_to_new["Discovery"] = PREFIX_DISCOVERY
    
    if not old_to_new:
        log("  ℹ️  No prefix changes detected - skipping rename")
        return
    
    renamed_count = 0
    
    for old_name, playlist_id in list(existing.items()):
        new_name = None
        
        # Check each old prefix pattern
        for old_prefix, new_prefix in old_to_new.items():
            # Check if old prefix appears in the name
            if old_prefix in old_name:
                # Try to extract the suffix (date/genre part) and reconstruct
                # Pattern: [Owner][OldPrefix][Suffix]
                # Example: "AJAutoNov24" -> "AJFndsNov24"
                # Example: "AJAutoHipHop" -> "AJFndsHipHop"
                
                # Find where the old prefix starts and ends
                prefix_start = old_name.find(old_prefix)
                if prefix_start == -1:
                    continue
                
                prefix_end = prefix_start + len(old_prefix)
                before_prefix = old_name[:prefix_start]
                suffix = old_name[prefix_end:]
                
                # Reconstruct with new prefix, preserving case
                if old_prefix.isupper():
                    new_prefix_used = new_prefix.upper()
                elif old_prefix.islower():
                    new_prefix_used = new_prefix.lower()
                elif old_prefix[0].isupper():
                    new_prefix_used = new_prefix.title() if len(new_prefix) > 1 else new_prefix.upper()
                else:
                    new_prefix_used = new_prefix
                
                new_name = f"{before_prefix}{new_prefix_used}{suffix}"
                
                # Only rename if the new name is different and doesn't already exist
                if new_name != old_name and new_name not in existing:
                    try:
                        api_call(
                            sp.user_playlist_change_details,
                            user_id,
                            playlist_id,
                            name=new_name
                        )
                        log(f"  ✅ Renamed: '{old_name}' -> '{new_name}'")
                        renamed_count += 1
                        # Invalidate cache so we get fresh data
                        _invalidate_playlist_cache()
                        # Update existing dict for this run
                        existing[new_name] = playlist_id
                        del existing[old_name]
                    except Exception as e:
                        log(f"  ⚠️  Failed to rename '{old_name}': {e}")
                elif new_name in existing:
                    log(f"  ⚠️  Skipped '{old_name}' -> '{new_name}' (target name already exists)")
                break  # Only apply first matching pattern
    
    if renamed_count > 0:
        log(f"  ✅ Renamed {renamed_count} playlist(s)")
    else:
        log("  ℹ️  No playlists needed renaming")


def fix_incorrectly_named_yearly_genre_playlists(sp: spotipy.Spotify) -> None:
    """Fix yearly genre playlists that were incorrectly named using GENRE_MONTHLY_TEMPLATE.
    
    This fixes playlists that were created with the monthly template (which includes {mon})
    but should have been created with the yearly template (which doesn't include {mon}).
    The wrong names might have literal template placeholders like {mon}, {year}, etc.
    """
    log("\n--- Fixing Incorrectly Named Yearly Genre Playlists ---")
    
    existing = get_existing_playlists(sp, force_refresh=True)
    user = get_user_info(sp)
    user_id = user["id"]
    
    renamed_count = 0
    template_placeholders = ["{mon}", "{year}", "{prefix}", "{genre}", "{owner}"]
    
def get_most_played_tracks(history_df: pd.DataFrame, month_str: str = None, limit: int = 50) -> list:
    """
    Get most played tracks for a given month (or all data if month_str is None) from streaming history.
    
    Args:
        history_df: Streaming history DataFrame
        month_str: Month string like '2025-01' (None to use all data)
        limit: Maximum number of tracks to return
    
    Returns:
        List of track URIs (most played first)
    """
    if history_df is None or history_df.empty:
        return []
    
    # Filter to month if provided
    if month_str:
        month_data = history_df.copy()
        month_data['month'] = month_data['timestamp'].dt.to_period('M').astype(str)
        month_data = month_data[month_data['month'] == month_str].copy()
    else:
        month_data = history_df.copy()
    
    if month_data.empty:
        return []
    
    # Group by track URI and sum play counts and duration
    if 'track_uri' in month_data.columns:
        track_col = 'track_uri'
    elif 'spotify_track_uri' in month_data.columns:
        track_col = 'spotify_track_uri'
    else:
        # Try to construct from track name/artist (less reliable)
        return []
    
    # Count plays and sum duration
    track_stats = month_data.groupby(track_col).agg({
        'ms_played': ['count', 'sum']
    }).reset_index()
    track_stats.columns = ['track_uri', 'play_count', 'total_ms']
    
    # Sort by play count (primary) and total duration (secondary)
    track_stats = track_stats.sort_values(['play_count', 'total_ms'], ascending=False)
    
    # Get top tracks
    top_tracks = track_stats.head(limit)['track_uri'].tolist()
    
    # Filter out None/NaN values
    return [uri for uri in top_tracks if pd.notna(uri) and uri]


def get_time_based_tracks(history_df: pd.DataFrame, month_str: str = None, time_type: str = "morning", limit: int = 50) -> list:
    """
    Get tracks played at specific times for a given month (or all data if month_str is None).
    
    Args:
        history_df: Streaming history DataFrame
        month_str: Month string like '2025-01' (None to use all data)
        time_type: "morning" (6-11), "afternoon" (12-17), "evening" (18-23), "night" (0-5), "weekend"
        limit: Maximum number of tracks to return
    
    Returns:
        List of track URIs
    """
    if history_df is None or history_df.empty:
        return []
    
    # Filter to month if provided
    if month_str:
        history_df = history_df.copy()
        history_df['month'] = history_df['timestamp'].dt.to_period('M').astype(str)
        month_data = history_df[history_df['month'] == month_str].copy()
    else:
        month_data = history_df.copy()
    
    if month_data.empty:
        return []
    
    # Filter by time
    if time_type == "morning":
        filtered = month_data[(month_data['hour'] >= 6) & (month_data['hour'] < 12)]
    elif time_type == "afternoon":
        filtered = month_data[(month_data['hour'] >= 12) & (month_data['hour'] < 18)]
    elif time_type == "evening":
        filtered = month_data[(month_data['hour'] >= 18) & (month_data['hour'] < 24)]
    elif time_type == "night":
        filtered = month_data[(month_data['hour'] >= 0) & (month_data['hour'] < 6)]
    elif time_type == "weekend":
        filtered = month_data[month_data['day_of_week_num'].isin([5, 6])]  # Sat, Sun
    else:
        return []
    
    if filtered.empty:
        return []
    
    # Get track URI column
    if 'track_uri' in filtered.columns:
        track_col = 'track_uri'
    elif 'spotify_track_uri' in filtered.columns:
        track_col = 'spotify_track_uri'
    else:
        return []
    
    # Get most played tracks for this time period
    track_stats = filtered.groupby(track_col).agg({
        'ms_played': ['count', 'sum']
    }).reset_index()
    track_stats.columns = ['track_uri', 'play_count', 'total_ms']
    track_stats = track_stats.sort_values(['play_count', 'total_ms'], ascending=False)
    
    top_tracks = track_stats.head(limit)['track_uri'].tolist()
    return [uri for uri in top_tracks if pd.notna(uri) and uri]


def get_repeat_tracks(history_df: pd.DataFrame, month_str: str = None, min_repeats: int = 3, limit: int = 50) -> list:
    """
    Get tracks that were played multiple times (on repeat) in a given month (or all data if month_str is None).
    
    Args:
        history_df: Streaming history DataFrame
        month_str: Month string like '2025-01' (None to use all data)
        min_repeats: Minimum number of plays to be considered "on repeat"
        limit: Maximum number of tracks to return
    
    Returns:
        List of track URIs
    """
    if history_df is None or history_df.empty:
        return []
    
    # Filter to month if provided
    if month_str:
        history_df = history_df.copy()
        history_df['month'] = history_df['timestamp'].dt.to_period('M').astype(str)
        month_data = history_df[history_df['month'] == month_str].copy()
    else:
        month_data = history_df.copy()
    
    if month_data.empty:
        return []
    
    # Get track URI column
    if 'track_uri' in month_data.columns:
        track_col = 'track_uri'
    elif 'spotify_track_uri' in month_data.columns:
        track_col = 'spotify_track_uri'
    else:
        return []
    
    # Count plays per track
    play_counts = month_data.groupby(track_col).size().reset_index(name='play_count')
    
    # Filter to tracks played at least min_repeats times
    repeat_tracks = play_counts[play_counts['play_count'] >= min_repeats].copy()
    
    # Sort by play count (most repeated first)
    repeat_tracks = repeat_tracks.sort_values('play_count', ascending=False)
    
    # Get top tracks
    top_tracks = repeat_tracks.head(limit)[track_col].tolist()
    return [uri for uri in top_tracks if pd.notna(uri) and uri]


def get_discovery_tracks(history_df: pd.DataFrame, month_str: str = None, limit: int = DEFAULT_DISCOVERY_TRACK_LIMIT) -> list:
    """
    Get newly discovered tracks (first time played) in a given month (or all data if month_str is None).
    
    Args:
        history_df: Streaming history DataFrame
        month_str: Month string like '2025-01' (None to use all data - finds first plays overall)
        limit: Maximum number of tracks to return
    
    Returns:
        List of track URIs
    """
    if history_df is None or history_df.empty:
        return []
    
    # Get track URI column
    if 'track_uri' in history_df.columns:
        track_col = 'track_uri'
    elif 'spotify_track_uri' in history_df.columns:
        track_col = 'spotify_track_uri'
    else:
        return []
    
    # Filter to month if provided
    if month_str:
        history_df = history_df.copy()
        history_df['month'] = history_df['timestamp'].dt.to_period('M').astype(str)
        month_data = history_df[history_df['month'] == month_str].copy()
        
        if month_data.empty:
            return []
        
        # Get all tracks played before this month
        before_month = history_df[history_df['month'] < month_str]
        known_tracks = set()
        if not before_month.empty and track_col in before_month.columns:
            known_tracks = set(before_month[track_col].dropna().unique())
        
        # Get tracks played in this month that weren't played before
        month_tracks = month_data[track_col].dropna().unique()
        new_tracks = [uri for uri in month_tracks if uri not in known_tracks]
        
        # Sort by first play time (earliest discoveries first)
        first_plays = month_data[month_data[track_col].isin(new_tracks)].sort_values('timestamp')
        first_plays = first_plays.drop_duplicates(subset=[track_col], keep='first')
        sorted_new_tracks = first_plays[track_col].tolist()
        
        # Return top tracks
        return sorted_new_tracks[:limit]
    else:
        # No month specified - find first plays overall
        first_plays = history_df.sort_values('timestamp').drop_duplicates(subset=[track_col], keep='first')
        sorted_new_tracks = first_plays[track_col].tolist()
        
        # Return top tracks
        return sorted_new_tracks[:limit]


def main():
    # Load environment variables from .env file if available
    if DOTENV_AVAILABLE:
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    
    # Clear log buffer at start
    global _log_buffer
    _log_buffer = []
    
    parser = argparse.ArgumentParser(
        description="Sync Spotify library and update playlists",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/spotify_sync.py              # Full sync + update
    python scripts/spotify_sync.py --skip-sync  # Update only (fast)
    python scripts/spotify_sync.py --sync-only  # Sync only, no playlist changes
    python scripts/spotify_sync.py --all-months # Process all months
    python scripts/spotify_sync.py --verbose    # Enable detailed logging
    python scripts/spotify_sync.py -v --skip-sync  # Verbose mode + skip sync
        """
    )
    parser.add_argument(
        "--skip-sync", action="store_true",
        help="Skip data sync, use existing parquet files (faster for local runs)"
    )
    parser.add_argument(
        "--sync-only", action="store_true",
        help="Only sync data, don't update playlists"
    )
    parser.add_argument(
        "--all-months", action="store_true",
        help="Process all months (deprecated: now uses last 3 months by default)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging for detailed debugging information"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force full sync without using cache (re-fetch all data)"
    )
    args = parser.parse_args()
    
    # Set global verbose flag
    global _verbose
    _verbose = args.verbose
    if _verbose:
        verbose_log("Verbose logging enabled - detailed output will be shown")
    
    log("=" * 60)
    log("Spotify Sync & Playlist Update")
    log("=" * 60)
    
    success = False
    error = None
    summary = {}
    
        # Authenticate
    try:
        verbose_log("Initializing Spotify client...")
        sp = get_spotify_client()
        verbose_log("Fetching user info...")
        user = get_user_info(sp)
        log(f"Authenticated as: {user['display_name']} ({user['id']})")
        verbose_log(f"User details: email={user.get('email', 'N/A')}, followers={user.get('followers', {}).get('total', 'N/A')}, product={user.get('product', 'N/A')}")
    except Exception as e:
        log(f"ERROR: Authentication failed: {e}")
        verbose_log(f"Authentication error details: {type(e).__name__}: {str(e)}")
        if _verbose:
            import traceback
            verbose_log(f"Traceback:\n{traceback.format_exc()}")
        error = e
        _send_email_notification(False, error=error)
        sys.exit(1)
    
    try:
        verbose_log(f"Configuration: skip_sync={args.skip_sync}, sync_only={args.sync_only}, all_months={args.all_months}")
        verbose_log(f"Environment: KEEP_MONTHLY_MONTHS={KEEP_MONTHLY_MONTHS}, OWNER_NAME={OWNER_NAME}, BASE_PREFIX={BASE_PREFIX}")
        
        # Data sync phase
        if not args.skip_sync:
            verbose_log("Starting full library sync phase...")
            with timed_step("Full Library Sync"):
                # Full library sync using spotim8 (includes liked songs and artists)
                sync_success = sync_full_library(force=args.force)
                summary["sync_completed"] = "Yes" if sync_success else "No"
                verbose_log(f"Sync completed: success={sync_success}")
        else:
            verbose_log("Skipping data sync (--skip-sync flag set)")
        
        # Playlist update phase
        if not args.sync_only:
            verbose_log("Starting playlist update phase...")
            with timed_step("Rename Playlists with Old Prefixes"):
                # Rename playlists with old prefixes (runs first, before other updates)
                rename_playlists_with_old_prefixes(sp)
            
            with timed_step("Fix Incorrectly Named Yearly Genre Playlists"):
                # Fix yearly genre playlists that were created with wrong template
                fix_incorrectly_named_yearly_genre_playlists(sp)
            
            with timed_step("Consolidate Old Monthly Playlists"):
                # Consolidate old monthly playlists into yearly (runs first)
                # Consolidates anything older than the last N months (default: 3)
                consolidate_old_monthly_playlists(sp, keep_last_n_months=KEEP_MONTHLY_MONTHS)
            
            with timed_step("Delete Old Monthly Playlists"):
                # Delete old monthly playlists (including genre-split)
                delete_old_monthly_playlists(sp)
            
            with timed_step("Update Monthly Playlists"):
                # Update monthly playlists (only last N months, default: 3)
                month_to_tracks = update_monthly_playlists(
                    sp, keep_last_n_months=KEEP_MONTHLY_MONTHS
                )
                if month_to_tracks:
                    summary["months_processed"] = len(month_to_tracks)
            
            # Update genre-split playlists
            if month_to_tracks:
                with timed_step("Update Genre-Split Playlists"):
                    update_genre_split_playlists(sp, month_to_tracks)
            
            with timed_step("Update Master Genre Playlists"):
                # Update master genre playlists
                update_master_genre_playlists(sp)
            
            # Optional: Run health check if enabled
            if _parse_bool_env("ENABLE_HEALTH_CHECK", False):
                with timed_step("Playlist Health Check"):
                    try:
                        from .playlist_organization import get_playlist_organization_report, print_organization_report
                        import pandas as pd
                        
                        playlists_df = pd.read_parquet(DATA_DIR / "playlists.parquet")
                        playlist_tracks_df = pd.read_parquet(DATA_DIR / "playlist_tracks.parquet")
                        tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
                        
                        owned_playlists = playlists_df[playlists_df.get("is_owned", False) == True].copy()
                        report = get_playlist_organization_report(
                            owned_playlists, playlist_tracks_df, tracks_df
                        )
                        print_organization_report(report)
                    except Exception as e:
                        verbose_log(f"  Health check failed (non-fatal): {e}")
            
            # Optional: Generate insights report if enabled
            if _parse_bool_env("ENABLE_INSIGHTS_REPORT", False):
                with timed_step("Generating Insights Report"):
                    try:
                        from .playlist_intelligence import generate_listening_insights_report
                        import pandas as pd
                        
                        playlists_df = pd.read_parquet(DATA_DIR / "playlists.parquet")
                        playlist_tracks_df = pd.read_parquet(DATA_DIR / "playlist_tracks.parquet")
                        tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
                        
                        streaming_history_df = None
                        streaming_path = DATA_DIR / "streaming_history.parquet"
                        if streaming_path.exists():
                            streaming_history_df = pd.read_parquet(streaming_path)
                        
                        report = generate_listening_insights_report(
                            playlists_df,
                            playlist_tracks_df,
                            tracks_df,
                            streaming_history_df
                        )
                        log("\n" + report)
                    except Exception as e:
                        verbose_log(f"  Insights report failed (non-fatal): {e}")
            
            # Optional: Generate genre discovery report if enabled
            if _parse_bool_env("ENABLE_GENRE_DISCOVERY", False):
                with timed_step("Genre Discovery Analysis"):
                    try:
                        from .genre_enhancement import generate_genre_discovery_report
                        import pandas as pd
                        
                        tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
                        track_artists_df = pd.read_parquet(DATA_DIR / "track_artists.parquet")
                        artists_df = pd.read_parquet(DATA_DIR / "artists.parquet")
                        playlist_tracks_df = pd.read_parquet(DATA_DIR / "playlist_tracks.parquet")
                        playlists_df = pd.read_parquet(DATA_DIR / "playlists.parquet")
                        
                        streaming_history_df = None
                        streaming_path = DATA_DIR / "streaming_history.parquet"
                        if streaming_path.exists():
                            streaming_history_df = pd.read_parquet(streaming_path)
                        
                        report = generate_genre_discovery_report(
                            tracks_df,
                            track_artists_df,
                            artists_df,
                            playlist_tracks_df,
                            playlists_df,
                            streaming_history_df
                        )
                        log("\n" + report)
                    except Exception as e:
                        verbose_log(f"  Genre discovery failed (non-fatal): {e}")
        
        log("\n" + "=" * 60)
        log("✅ Complete!")
        log("=" * 60)
        success = True
        
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        error_trace = traceback.format_exc()
        log(error_trace)
        error = e
        success = False
    
    finally:
        # Send email notification
        _send_email_notification(success, summary=summary, error=error)
        
        if not success:
            sys.exit(1)


def _send_email_notification(success: bool, summary: dict = None, error: Exception = None):
    """Helper to send email notification with captured logs."""
    if not EMAIL_AVAILABLE:
        log("  ℹ️  Email notifications not available (email_notify.py not found)")
        return
    
    if not is_email_enabled():
        log("  ℹ️  Email notifications disabled (EMAIL_ENABLED not set to true)")
        return
    
    log_output = "\n".join(_log_buffer)
    
    try:
        log("  📧 Sending email notification...")
        email_sent = send_email_notification(
            success=success,
            log_output=log_output,
            summary=summary or {},
            error=error
        )
        if email_sent:
            log("  ✅ Email notification sent successfully")
        else:
            log("  ⚠️  Email notification failed (check email configuration)")
    except Exception as e:
        # Don't fail the sync if email fails
        log(f"  ⚠️  Email notification error (non-fatal): {e}")
        import traceback
        log(traceback.format_exc())


if __name__ == "__main__":
    main()

