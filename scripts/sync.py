#!/usr/bin/env python3
"""
Unified Spotify Sync & Playlist Update

This script:
1. Syncs your Spotify library to local parquet files using spotim8 (optional)
2. Consolidates old monthly playlists into yearly genre-split playlists
3. Updates monthly playlists with liked songs (current year only)
4. Updates genre-split monthly playlists (HipHop, Dance, Other)
5. Updates master genre playlists

IMPORTANT: This script only ADDS tracks to playlists. It never removes tracks.
Manually added tracks are preserved and will remain in the playlists even after
automated updates. Feel free to manually add tracks to any automatically generated
playlists - they will not be removed.

The script automatically loads environment variables from .env file if python-dotenv
is installed and a .env file exists in the project root.

Usage:
    python scripts/sync.py              # Full sync + update
    python scripts/sync.py --skip-sync  # Update only (fast, uses existing data)
    python scripts/sync.py --sync-only  # Sync only, no playlist changes
    python scripts/sync.py --all-months # Process all months, not just current

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
    python scripts/sync.py
    
    # Via wrapper (for cron):
    python scripts/runner.py
    
    # Linux/Mac cron (every day at 2am):
    0 2 * * * cd /path/to/spotim8 && /path/to/venv/bin/python scripts/runner.py
"""

import argparse
import ast
import io
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from tqdm import tqdm

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# Adaptive backoff multiplier (increases after rate errors, decays on success)
_RATE_BACKOFF_MULTIPLIER = 1.0
_RATE_BACKOFF_MAX = 16.0

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import spotim8 for full library sync (required)
from spotim8 import Spotim8, CacheConfig, set_response_cache

# Import genre classification functions from shared module
from spotim8.genres import (
    SPLIT_GENRES,
    get_split_genre, get_broad_genre,
    get_all_split_genres, get_all_broad_genres
)

# Import comprehensive genre inference
from spotim8.genre_inference import (
    infer_genres_comprehensive,
    enhance_artist_genres_from_playlists
)

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

OWNER_NAME = os.environ.get("PLAYLIST_OWNER_NAME", "AJ")
PREFIX = os.environ.get("PLAYLIST_PREFIX", "Finds")

# Playlist naming templates
MONTHLY_NAME_TEMPLATE = "{owner}{prefix}{mon}{year}"
YEARLY_NAME_TEMPLATE = "{owner}{prefix}{year}"  # For consolidating old monthly playlists
GENRE_MONTHLY_TEMPLATE = "{genre}{prefix}{mon}{year}"
GENRE_NAME_TEMPLATE = "{owner}am{genre}"

# Master genre playlist limits
MIN_TRACKS_FOR_GENRE = 20
MAX_GENRE_PLAYLISTS = 19

# Paths
DATA_DIR = PROJECT_ROOT / "data"
LIKED_SONGS_PLAYLIST_ID = "__liked_songs__"  # Match spotim8 library constant

# Month name mapping
MONTH_NAMES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
}

# Genre classification functions:
# - get_split_genre() - Maps tracks to HipHop, Dance, or Other
# - get_broad_genre() - Maps tracks to broad categories (Hip-Hop, Electronic, etc.)
# - SPLIT_GENRES - List of split genres: ["HipHop", "Dance", "Other"]


# ============================================================================
# UTILITIES
# ============================================================================

# Global log buffer for email notifications
_log_buffer = []

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

# Set log function for genre_inference module (after log is defined)
import spotim8.genre_inference as genre_inference_module
genre_inference_module._log_fn = log


def api_call(fn, *args, max_retries: int = 6, backoff_factor: float = 1.0, **kwargs):
    """Call Spotify API method `fn` with retries and exponential backoff on rate limits or transient errors.

    `fn` should be a callable (typically a bound method on a `spotipy.Spotify` client).
    The helper inspects exception attributes for 429/retry-after and uses exponential backoff.
    """
    global _RATE_BACKOFF_MULTIPLIER

    for attempt in range(max_retries):
        try:
            result = fn(*args, **kwargs)
            # Adaptive short delay between successful calls to avoid bursting the API
            try:
                base_delay = float(os.environ.get("SPOTIFY_API_DELAY", "0.15"))
            except Exception:
                base_delay = 0.15
            # Multiply by adaptive multiplier (increases when we hit rate limits)
            delay = base_delay * _RATE_BACKOFF_MULTIPLIER
            if delay and delay > 0:
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
                time.sleep(wait)
                # Increase adaptive multiplier to throttle further successful calls
                try:
                    _RATE_BACKOFF_MULTIPLIER = min(_RATE_BACKOFF_MAX, _RATE_BACKOFF_MULTIPLIER * 2.0)
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


def _chunked(seq, n=100):
    """Yield chunks of sequence."""
    for i in range(0, len(seq), n):
        yield seq[i:i+n]


def _to_uri(track_id: str) -> str:
    """Convert track ID to Spotify URI."""
    track_id = str(track_id)
    if track_id.startswith("spotify:track:"):
        return track_id
    if len(track_id) >= 20 and ":" not in track_id:
        return f"spotify:track:{track_id}"
    return track_id


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


def format_playlist_name(template: str, month_str: str, genre: str = None) -> str:
    """Format playlist name from month string like '2025-01'."""
    parts = month_str.split("-")
    full_year = parts[0] if len(parts) >= 1 else ""
    month_num = parts[1] if len(parts) >= 2 else ""
    mon = MONTH_NAMES.get(month_num, month_num)
    year = full_year[2:] if len(full_year) == 4 else full_year
    
    return template.format(
        owner=OWNER_NAME,
        prefix=PREFIX,
        genre=genre or "",
        mon=mon,
        year=year
    )


def format_yearly_playlist_name(year: str) -> str:
    """Format yearly playlist name like 'AJFinds2025'."""
    # Handle both 4-digit and 2-digit years
    if len(year) == 4:
        year_short = year[2:]
    else:
        year_short = year
    
    return YEARLY_NAME_TEMPLATE.format(
        owner=OWNER_NAME,
        prefix=PREFIX,
        year=year_short
    )


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
        return _playlist_cache
    
    mapping = {}
    offset = 0
    while True:
        page = api_call(sp.current_user_playlists, limit=50, offset=offset)
        for item in page.get("items", []):
            mapping[item["name"]] = item["id"]
        if not page.get("next"):
            break
        offset += 50
    
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
        return _playlist_tracks_cache[playlist_id]
    
    uris = set()
    offset = 0
    while True:
        page = api_call(
            sp.playlist_items,
            playlist_id,
            fields="items(track(uri)),next",
            limit=100,
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
        # Load all data
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
        
        tracks = pd.read_parquet(tracks_path)
        track_artists = pd.read_parquet(track_artists_path)
        artists = pd.read_parquet(artists_path)
        playlist_tracks = pd.read_parquet(playlist_tracks_path)
        playlists = pd.read_parquet(playlists_path)
        
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
        if stats and (stats.get("playlists_updated", 0) > 0 or stats.get("tracks_added", 0) > 0):
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
            log("  ⏭️  Skipping artist genre enhancement (no playlist changes)")
        
        # Filter to only tracks that need inference
        tracks_to_process = tracks[tracks["track_id"].isin(tracks_needing_inference)]
        
        if len(tracks_to_process) == 0:
            log(f"  ✅ All tracks up to date (smart cache hit)")
            return
        
        tqdm.write(f"  🔄 Inferring genres for {len(tracks_to_process):,} track(s)...")
        
        # Infer genres for tracks that need it
        inferred_genres_map = {}
        
        # Use tqdm for progress bar
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
        
        # Update tracks with inferred genres
        if inferred_genres_map:
            tqdm.write("  💾 Updating track genres...")
            for track_id, genres in inferred_genres_map.items():
                track_mask = tracks["track_id"] == track_id
                track_rows = tracks[track_mask]
                if len(track_rows) > 0:
                    # Use .at for scalar assignment of list values
                    track_idx_val = track_rows.index[0]
                    tracks.at[track_idx_val, "genres"] = genres
            
            # Save updated tracks
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


def sync_full_library() -> bool:
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
        else:
            log("📭 No cached data found - running full sync...")
        
        # Sync library (incremental - only fetches changes based on snapshot_id)
        # Note: We use owned_only=True for playlist_tracks to avoid syncing all followed playlist contents,
        # but we still sync all playlists (owned + followed) metadata so we can learn from their names/descriptions
        stats = sf.sync(
            owned_only=True,  # Only sync tracks from owned playlists (faster)
            include_liked_songs=True
        )
        
        # Ensure we have ALL playlists (owned + followed) for genre inference
        # This allows us to learn from followed playlist names/descriptions
        # The sync() call above already loads all playlists, but we ensure they're fresh
        _ = sf.playlists(force=False)  # Load all playlists including followed (uses cache if fresh)
        
        log(f"✅ Library sync complete: {stats}")
        
        # Only regenerate derived tables if something changed
        if stats.get("playlists_updated", 0) > 0 or stats.get("tracks_added", 0) > 0:
            log("🔧 Regenerating derived tables...")
            _ = sf.tracks()
            _ = sf.artists()
            _ = sf.library_wide()
            log("✅ All parquet files updated")
        else:
            log("✅ No changes detected - using cached derived tables")
        
        # Compute track genres with smart caching - only processes changed tracks
        # This dramatically improves sync runtime by avoiding unnecessary computation
        compute_track_genres_incremental(stats)
        
        return True
        
    except Exception as e:
        log(f"ERROR: Full library sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False




# ============================================================================
# PLAYLIST UPDATE FUNCTIONS
# ============================================================================

def update_monthly_playlists(sp: spotipy.Spotify, current_month_only: bool = True) -> dict:
    """Update monthly playlists with liked songs.
    
    Note: This function only ADDS tracks from liked songs. It never removes tracks.
    Manually added tracks are preserved and will remain in the playlists.
    """
    log("\n--- Monthly Playlists ---")
    
    # Load data
    playlist_tracks_path = DATA_DIR / "playlist_tracks.parquet"
    if not playlist_tracks_path.exists():
        log("No playlist_tracks.parquet found!")
        return {}
    
    library = pd.read_parquet(playlist_tracks_path)
    
    # Get liked songs
    liked = library[library["playlist_id"].astype(str) == LIKED_SONGS_PLAYLIST_ID].copy()
    
    if liked.empty:
        log("No liked songs found!")
        return {}
    
    # Parse timestamps - try multiple column names
    added_col = None
    for col in ["added_at", "playlist_added_at", "track_added_at"]:
        if col in liked.columns:
            added_col = col
            break
    
    if not added_col:
        log("No timestamp column found!")
        return {}
    
    liked[added_col] = pd.to_datetime(liked[added_col], errors="coerce", utc=True)
    liked["month"] = liked[added_col].dt.to_period("M").astype(str)
    
    # Handle both track_uri and track_id columns
    if "track_uri" in liked.columns:
        liked["_uri"] = liked["track_uri"]
    else:
        liked["_uri"] = liked["track_id"].map(_to_uri)
    
    # Build month -> tracks mapping
    month_to_tracks = {}
    for month, group in liked.groupby("month"):
        uris = group["_uri"].dropna().tolist()
        # Deduplicate while preserving order
        seen = set()
        unique = [u for u in uris if not (u in seen or seen.add(u))]
        month_to_tracks[month] = unique
    
    # Filter to current month if requested
    if current_month_only:
        current = datetime.now().strftime("%Y-%m")
        month_to_tracks = {m: v for m, v in month_to_tracks.items() if m == current}
    
    if not month_to_tracks:
        log("No months to process")
        return {}
    
    log(f"Processing {len(month_to_tracks)} month(s)...")
    
    # Get existing playlists (cached)
    existing = get_existing_playlists(sp)
    user = get_user_info(sp)
    user_id = user["id"]
    
    for month, uris in sorted(month_to_tracks.items()):
        if not uris:
            continue
        
        name = format_playlist_name(MONTHLY_NAME_TEMPLATE, month)
        if name in existing:
            pid = existing[name]
            # Get existing tracks (includes both auto-added and manually added tracks)
            already = get_playlist_tracks(sp, pid)
            # Only add tracks that aren't already present (preserves manual additions)
            to_add = [u for u in uris if u not in already]

            if to_add:
                for chunk in _chunked(to_add, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                # Invalidate cache for this playlist since we added tracks
                if pid in _playlist_tracks_cache:
                    del _playlist_tracks_cache[pid]
                log(f"  {name}: +{len(to_add)} tracks (manually added tracks preserved)")
            else:
                log(f"  {name}: up to date")
        else:
            pl = api_call(
                sp.user_playlist_create,
                user_id,
                name,
                public=False,
                description=f"Liked songs from {month} (automatically updated; manual additions welcome)",
            )
            pid = pl["id"]

            for chunk in _chunked(uris, 50):
                api_call(sp.playlist_add_items, pid, chunk)
            # Invalidate playlist cache since we created a new playlist
            _invalidate_playlist_cache()
            log(f"  {name}: created with {len(uris)} tracks")
    
    return month_to_tracks


def consolidate_old_monthly_playlists(sp: spotipy.Spotify) -> None:
    """Consolidate monthly playlists older than the last year into yearly playlists.
    
    Only keeps the last year as monthly (current year).
    For any year older than that:
    - Combine all monthly playlists (e.g., AJFindsJan22, AJFindsFeb22, ...) 
      into 4 yearly playlists:
      - AJFinds{YY} - all tracks from that year
      - AJFindsHipHop{YY} - hip hop tracks from that year
      - AJFindsDance{YY} - dance tracks from that year
      - AJFindsOther{YY} - other tracks from that year
    - Delete the old monthly playlists
    
    If monthly playlists don't exist for a year, creates the consolidated playlists
    directly from liked songs data (robust logic).
    
    Note: This function only ADDS tracks to existing yearly playlists. It never removes tracks.
    Manually added tracks are preserved and will remain in the playlists.
    """
    log("\n--- Consolidating Old Monthly Playlists ---")
    
    current_year = datetime.now().year
    cutoff_year = current_year  # Keep only the current year as monthly
    
    # Get all existing playlists (cached)
    existing = get_existing_playlists(sp)
    user = get_user_info(sp)
    user_id = user["id"]
    
    # Pattern: {owner}{prefix}{mon}{year} e.g., "AJFindsJan23"
    # Extract monthly playlists matching the pattern
    monthly_pattern = f"{OWNER_NAME}{PREFIX}"
    monthly_playlists = {}
    
    for playlist_name, playlist_id in existing.items():
        if playlist_name.startswith(monthly_pattern):
            # Check if it matches monthly format (has a month name)
            for mon_abbr in MONTH_NAMES.values():
                if playlist_name.startswith(f"{monthly_pattern}{mon_abbr}"):
                    # Extract year (2 or 4 digits at the end)
                    remaining = playlist_name[len(f"{monthly_pattern}{mon_abbr}"):]
                    if remaining.isdigit():
                        year_str = remaining
                        # Convert 2-digit year to 4-digit (assume 2000s)
                        if len(year_str) == 2:
                            year = 2000 + int(year_str)
                        else:
                            year = int(year_str)
                        
                        if year < cutoff_year:
                            if year not in monthly_playlists:
                                monthly_playlists[year] = []
                            monthly_playlists[year].append((playlist_name, playlist_id))
                    break
    
    # Load liked songs data to get tracks by year (for robust consolidation)
    year_to_tracks = {}
    try:
        playlist_tracks_path = DATA_DIR / "playlist_tracks.parquet"
        if playlist_tracks_path.exists():
            library = pd.read_parquet(playlist_tracks_path)
            liked = library[library["playlist_id"].astype(str) == LIKED_SONGS_PLAYLIST_ID].copy()
            
            if not liked.empty:
                # Parse timestamps
                added_col = None
                for col in ["added_at", "playlist_added_at", "track_added_at"]:
                    if col in liked.columns:
                        added_col = col
                        break
                
                if added_col:
                    liked[added_col] = pd.to_datetime(liked[added_col], errors="coerce", utc=True)
                    liked["year"] = liked[added_col].dt.year
                    
                    # Handle both track_uri and track_id columns
                    if "track_uri" in liked.columns:
                        liked["_uri"] = liked["track_uri"]
                    else:
                        liked["_uri"] = liked["track_id"].map(_to_uri)
                    
                    # Build year -> tracks mapping
                    for year, group in liked.groupby("year"):
                        if year < cutoff_year:
                            uris = group["_uri"].dropna().tolist()
                            # Deduplicate while preserving order
                            seen = set()
                            unique = [u for u in uris if not (u in seen or seen.add(u))]
                            year_to_tracks[year] = unique
    except Exception as e:
        log(f"  ⚠️  Could not load liked songs data: {e}")
    
    # Only consolidate years that have monthly playlists that need consolidation
    # Skip years where consolidated playlists already exist and no monthly playlists remain
    years_to_consolidate = set()
    
    for year in set(monthly_playlists.keys()) | set(year_to_tracks.keys()):
        # If there are monthly playlists for this year, we need to consolidate
        if year in monthly_playlists:
            years_to_consolidate.add(year)
        else:
            # No monthly playlists - check if consolidated playlists exist
            # Only consolidate if they don't exist yet
            year_short = str(year)[2:] if len(str(year)) == 4 else str(year)
            main_playlist_name = format_yearly_playlist_name(str(year))
            if main_playlist_name not in existing:
                # Consolidated playlist doesn't exist, need to create it
                years_to_consolidate.add(year)
    
    if not years_to_consolidate:
        log("  No old years need consolidation (all already consolidated)")
        return
    
    log(f"  Found {len(years_to_consolidate)} year(s) to consolidate")
    
    # Load genre data for genre splits
    track_to_genres = {}  # Map URI to list of genres (tracks can have multiple)
    try:
        # Try to use stored track genres first (most efficient)
        tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
        if "genres" in tracks_df.columns:
            # Use stored track genres
            for _, track_row in tracks_df.iterrows():
                track_id = track_row["track_id"]
                uri = f"spotify:track:{track_id}"
                stored_genres = _parse_genres(track_row.get("genres"))
                if stored_genres:
                    # Convert stored genres to split genres
                    split_genres = get_all_split_genres(stored_genres)
                    if split_genres:
                        track_to_genres[uri] = split_genres
        
        track_artists = pd.read_parquet(DATA_DIR / "track_artists.parquet")
        artists = pd.read_parquet(DATA_DIR / "artists.parquet")
        artist_genres_map = artists.set_index("artist_id")["genres"].to_dict()
        
        # Build track -> genre mapping for all tracks we might need
        all_track_uris = set()
        for year in years_to_consolidate:
            if year in year_to_tracks:
                all_track_uris.update(year_to_tracks[year])
            if year in monthly_playlists:
                for _, pid in monthly_playlists[year]:
                    all_track_uris.update(get_playlist_tracks(sp, pid))
        
        track_ids = {u.split(":")[-1] for u in all_track_uris if u.startswith("spotify:track:")}
        
        # Fill in missing genres using artist data
        for track_id in track_ids:
            uri = f"spotify:track:{track_id}"
            if uri in track_to_genres:
                continue  # Already have genres from stored data
            
            # Get all genres from all artists on this track
            all_track_genres = _get_all_track_genres(track_id, track_artists, artist_genres_map)
            split_genres = get_all_split_genres(all_track_genres)
            if split_genres:
                track_to_genres[uri] = split_genres
    except Exception as e:
        log(f"  ⚠️  Could not load genre data: {e}")
        log(f"  Will create main playlists only (no genre splits)")
    
    # For each old year, consolidate into 4 playlists
    for year in sorted(years_to_consolidate):
        year_short = str(year)[2:] if len(str(year)) == 4 else str(year)
        
        # Collect all tracks for this year
        all_tracks = set()
        
        # First, try to get tracks from existing monthly playlists
        if year in monthly_playlists:
            for monthly_name, monthly_id in monthly_playlists[year]:
                tracks = get_playlist_tracks(sp, monthly_id)
                all_tracks.update(tracks)
                log(f"    - {monthly_name}: {len(tracks)} tracks")
        
        # If no tracks from playlists, or to ensure completeness, use liked songs data
        if year in year_to_tracks:
            all_tracks.update(year_to_tracks[year])
            if year not in monthly_playlists:
                log(f"    - Using liked songs data: {len(year_to_tracks[year])} tracks")
        
        if not all_tracks:
            log(f"    ⚠️  No tracks found for {year}, skipping")
            continue
        
        all_tracks_list = list(all_tracks)
        
        # Create 4 playlists: main + 3 genre splits
        main_playlist_name = format_yearly_playlist_name(str(year))
        playlist_configs = [
            (main_playlist_name, "All tracks", None),
            (f"{OWNER_NAME}{PREFIX}HipHop{year_short}", "Hip Hop tracks", "HipHop"),
            (f"{OWNER_NAME}{PREFIX}Dance{year_short}", "Dance tracks", "Dance"),
            (f"{OWNER_NAME}{PREFIX}Other{year_short}", "Other tracks", "Other"),
        ]
        
        for playlist_name, description, genre_filter in playlist_configs:
            # Filter tracks by genre if needed (tracks can match multiple genres)
            if genre_filter:
                filtered_tracks = [
                    u for u in all_tracks_list 
                    if genre_filter in track_to_genres.get(u, [])
                ]
            else:
                filtered_tracks = all_tracks_list
            
            if not filtered_tracks:
                log(f"    ⚠️  No {genre_filter or 'all'} tracks for {year}, skipping {playlist_name}")
                continue
            
            # Create or update playlist
            if playlist_name in existing:
                # If we're not consolidating from monthly playlists (they were already deleted),
                # and the playlist already exists, skip the expensive check
                if year not in monthly_playlists:
                    log(f"  {playlist_name}: already consolidated (skipping check)")
                    continue
                
                pid = existing[playlist_name]
                # Get existing tracks (includes both auto-added and manually added tracks)
                already = get_playlist_tracks(sp, pid)
                # Only add tracks that aren't already present (preserves manual additions)
                to_add = [u for u in filtered_tracks if u not in already]
                
                if to_add:
                    for chunk in _chunked(to_add, 50):
                        api_call(sp.playlist_add_items, pid, chunk)
                    log(f"  {playlist_name}: +{len(to_add)} tracks (total: {len(filtered_tracks)}; manually added tracks preserved)")
                else:
                    log(f"  {playlist_name}: already up to date ({len(filtered_tracks)} tracks)")
            else:
                pl = api_call(
                    sp.user_playlist_create,
                    user_id,
                    playlist_name,
                    public=False,
                    description=f"{description} from {year} (automatically updated; manual additions welcome)",
                )
                pid = pl["id"]
                
                for chunk in _chunked(filtered_tracks, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                log(f"  {playlist_name}: created with {len(filtered_tracks)} tracks")
        
        # Delete old monthly playlists if they existed
        if year in monthly_playlists:
            for monthly_name, monthly_id in monthly_playlists[year]:
                try:
                    api_call(sp.user_playlist_unfollow, user_id, monthly_id)
                    # Invalidate cache since we deleted a playlist
                    _invalidate_playlist_cache()
                    log(f"    ✓ Deleted {monthly_name}")
                except Exception as e:
                    log(f"    ⚠️  Failed to delete {monthly_name}: {e}")
        
        log(f"  ✅ Consolidated {year} into 4 playlists")


def delete_old_monthly_playlists(sp: spotipy.Spotify) -> None:
    """Delete old genre-split monthly playlists older than cutoff year.
    
    Standard monthly playlists are handled by consolidate_old_monthly_playlists().
    This function only handles genre-split playlists (HipHopFindsJan23, etc.).
    """
    log("\n--- Deleting Old Genre-Split Monthly Playlists ---")
    
    current_year = datetime.now().year
    cutoff_year = current_year  # Keep only the current year as monthly
    
    # Get all existing playlists
    existing = get_existing_playlists(sp)
    
    # Pattern for genre monthly: {genre}{prefix}{mon}{year}
    genre_patterns = []
    for genre in SPLIT_GENRES:
        genre_patterns.append(f"{genre}{PREFIX}")
    
    playlists_to_delete = []
    
    for playlist_name, playlist_id in existing.items():
        # Check genre-split monthly playlists only
        for genre_pattern in genre_patterns:
            if playlist_name.startswith(genre_pattern):
                for mon_abbr in MONTH_NAMES.values():
                    if playlist_name.startswith(f"{genre_pattern}{mon_abbr}"):
                        remaining = playlist_name[len(f"{genre_pattern}{mon_abbr}"):]
                        if remaining.isdigit():
                            year_str = remaining
                            # Convert 2-digit year to 4-digit (assume 2000s)
                            if len(year_str) == 2:
                                year = 2000 + int(year_str)
                            else:
                                year = int(year_str)
                            
                            if year < cutoff_year:
                                playlists_to_delete.append((playlist_name, playlist_id))
                        break
    
    if not playlists_to_delete:
        log("  No old genre-split monthly playlists to delete")
        return
    
    log(f"  Found {len(playlists_to_delete)} old genre-split monthly playlists to delete")
    
    # Get user ID for deletion (cached)
    user = get_user_info(sp)
    user_id = user["id"]
    
    for playlist_name, playlist_id in playlists_to_delete:
        try:
            api_call(sp.user_playlist_unfollow, user_id, playlist_id)
            # Invalidate cache since we deleted a playlist
            _invalidate_playlist_cache()
            log(f"    ✓ Deleted {playlist_name}")
        except Exception as e:
            log(f"    ⚠️  Failed to delete {playlist_name}: {e}")
    
    log(f"  ✅ Deleted {len(playlists_to_delete)} old genre-split monthly playlists")


def update_genre_split_playlists(sp: spotipy.Spotify, month_to_tracks: dict) -> None:
    """Update genre-split monthly playlists (HipHop, Dance, Other).
    
    Note: This function only ADDS tracks from liked songs. It never removes tracks.
    Manually added tracks are preserved and will remain in the playlists.
    """
    if not month_to_tracks:
        return
    
    log("\n--- Genre-Split Playlists ---")
    
    # Load genre data
    track_artists = pd.read_parquet(DATA_DIR / "track_artists.parquet")
    artists = pd.read_parquet(DATA_DIR / "artists.parquet")
    
    artist_genres_map = artists.set_index("artist_id")["genres"].to_dict()
    
    # Build track -> genres mapping (tracks can have multiple genres)
    # Try to use stored track genres first
    track_to_genres = {}
    tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
    if "genres" in tracks_df.columns:
        # Use stored track genres
        for _, track_row in tracks_df.iterrows():
            track_id = track_row["track_id"]
            uri = f"spotify:track:{track_id}"
            stored_genres = _parse_genres(track_row.get("genres"))
            if stored_genres:
                split_genres = get_all_split_genres(stored_genres)
                if split_genres:
                    track_to_genres[uri] = split_genres
    
    # Fill in missing using artist data
    all_uris = set(u for uris in month_to_tracks.values() for u in uris)
    track_ids = {u.split(":")[-1] for u in all_uris if u.startswith("spotify:track:")}
    
    for track_id in track_ids:
        uri = f"spotify:track:{track_id}"
        if uri in track_to_genres:
            continue  # Already have from stored data
        
        # Get all genres from all artists on this track
        all_track_genres = _get_all_track_genres(track_id, track_artists, artist_genres_map)
        split_genres = get_all_split_genres(all_track_genres)
        if split_genres:
            track_to_genres[uri] = split_genres
    
    # Get existing playlists (cached)
    existing = get_existing_playlists(sp)
    user = get_user_info(sp)
    user_id = user["id"]
    
    for month, uris in sorted(month_to_tracks.items()):
        for genre in SPLIT_GENRES:
            # Tracks can match multiple genres, check if this genre is in the list
            genre_uris = [u for u in uris if genre in track_to_genres.get(u, [])]
            
            if not genre_uris:
                continue
            
            name = format_playlist_name(GENRE_MONTHLY_TEMPLATE, month, genre)
            
            if name in existing:
                pid = existing[name]
                # Get existing tracks (includes both auto-added and manually added tracks)
                already = get_playlist_tracks(sp, pid)
                # Only add tracks that aren't already present (preserves manual additions)
                to_add = [u for u in genre_uris if u not in already]

                if to_add:
                    for chunk in _chunked(to_add, 50):
                        api_call(sp.playlist_add_items, pid, chunk)
                    # Invalidate cache for this playlist since we added tracks
                    if pid in _playlist_tracks_cache:
                        del _playlist_tracks_cache[pid]
                    log(f"  {name}: +{len(to_add)} tracks (manually added tracks preserved)")
            else:
                pl = api_call(
                    sp.user_playlist_create,
                    user_id,
                    name,
                    public=False,
                    description=f"{genre} tracks from {month} (automatically updated; manual additions welcome)",
                )
                pid = pl["id"]

                for chunk in _chunked(genre_uris, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                # Invalidate playlist cache since we created a new playlist
                _invalidate_playlist_cache()
                log(f"  {name}: created with {len(genre_uris)} tracks")


def update_master_genre_playlists(sp: spotipy.Spotify) -> None:
    """Update master genre playlists with all liked songs by genre.
    
    Note: This function only ADDS tracks from liked songs. It never removes tracks.
    Manually added tracks are preserved and will remain in the playlists.
    """
    log("\n--- Master Genre Playlists ---")
    
    # Load data
    library = pd.read_parquet(DATA_DIR / "playlist_tracks.parquet")
    track_artists = pd.read_parquet(DATA_DIR / "track_artists.parquet")
    artists = pd.read_parquet(DATA_DIR / "artists.parquet")
    
    # Get liked songs
    liked = library[library["playlist_id"].astype(str) == LIKED_SONGS_PLAYLIST_ID]
    liked_ids = set(liked["track_id"])
    
    # Build URIs
    if "track_uri" in liked.columns:
        liked_uris = liked["track_uri"].dropna().tolist()
    else:
        liked_uris = [f"spotify:track:{tid}" for tid in liked_ids]
    
    # Build genre mapping - tracks can have MULTIPLE broad genres
    # Try to use stored track genres first, then fall back to artist genres
    uri_to_genres = {}  # Map URI to list of broad genres
    tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
    
    if "genres" in tracks_df.columns:
        # Use stored track genres and convert to broad genres
        for _, track_row in tracks_df.iterrows():
            track_id = track_row["track_id"]
            if track_id not in liked_ids:
                continue
            uri = f"spotify:track:{track_id}"
            stored_genres = _parse_genres(track_row.get("genres"))
            if stored_genres:
                # Convert stored genres to broad genres
                broad_genres = get_all_broad_genres(stored_genres)
                if broad_genres:
                    uri_to_genres[uri] = broad_genres
    
    # Fill in missing using artist data
    artist_genres_map = artists.set_index("artist_id")["genres"].to_dict()
    for track_id in liked_ids:
        uri = f"spotify:track:{track_id}"
        if uri in uri_to_genres:
            continue  # Already have from stored data
        
        # Get all genres from all artists on this track
        all_track_genres = _get_all_track_genres(track_id, track_artists, artist_genres_map)
        # Get ALL matching broad genres (tracks can match multiple)
        broad_genres = get_all_broad_genres(all_track_genres)
        if broad_genres:
            uri_to_genres[uri] = broad_genres
    
    # Count tracks per genre (tracks can contribute to multiple genres)
    genre_counts = Counter()
    for genres_list in uri_to_genres.values():
        for genre in genres_list:
            genre_counts[genre] += 1
    
    # Select top genres
    selected = [g for g, n in genre_counts.most_common(MAX_GENRE_PLAYLISTS) 
                if n >= MIN_TRACKS_FOR_GENRE]
    
    log(f"  Found {len(selected)} genre(s) with >= {MIN_TRACKS_FOR_GENRE} tracks")
    
    # Get existing playlists (cached)
    existing = get_existing_playlists(sp)
    user = get_user_info(sp)
    user_id = user["id"]
    
    for genre in selected:
        # Get all tracks that match this genre (tracks can match multiple genres)
        uris = [u for u in liked_uris if genre in uri_to_genres.get(u, [])]
        if not uris:
            continue
        
        name = GENRE_NAME_TEMPLATE.format(owner=OWNER_NAME, genre=genre)
        
        if name in existing:
            pid = existing[name]
            # Get existing tracks (includes both auto-added and manually added tracks)
            already = get_playlist_tracks(sp, pid)
            # Only add tracks that aren't already present (preserves manual additions)
            to_add = [u for u in uris if u not in already]

            if to_add:
                for chunk in _chunked(to_add, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                # Invalidate cache for this playlist since we added tracks
                if pid in _playlist_tracks_cache:
                    del _playlist_tracks_cache[pid]
                log(f"  {name}: +{len(to_add)} tracks (manually added tracks preserved)")
        else:
            pl = api_call(
                sp.user_playlist_create,
                user_id,
                name,
                public=False,
                description=f"All liked songs - {genre} (automatically updated; manual additions welcome)",
            )
            pid = pl["id"]

            for chunk in _chunked(uris, 50):
                api_call(sp.playlist_add_items, pid, chunk)
            # Invalidate playlist cache since we created a new playlist
            _invalidate_playlist_cache()
            log(f"  {name}: created with {len(uris)} tracks")


# ============================================================================
# MAIN
# ============================================================================

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
        help="Process all months, not just current month"
    )
    args = parser.parse_args()
    
    log("=" * 60)
    log("Spotify Sync & Playlist Update")
    log("=" * 60)
    
    success = False
    error = None
    summary = {}
    
    # Authenticate
    try:
        sp = get_spotify_client()
        user = get_user_info(sp)
        log(f"Authenticated as: {user['display_name']} ({user['id']})")
    except Exception as e:
        log(f"ERROR: Authentication failed: {e}")
        error = e
        _send_email_notification(False, error=error)
        sys.exit(1)
    
    try:
        # Data sync phase
        if not args.skip_sync:
            # Full library sync using spotim8 (includes liked songs and artists)
            sync_success = sync_full_library()
            summary["sync_completed"] = "Yes" if sync_success else "No"
        
        # Playlist update phase
        if not args.sync_only:
            # Consolidate old monthly playlists into yearly (runs first)
            consolidate_old_monthly_playlists(sp)
            
            # Delete old monthly playlists (including genre-split)
            delete_old_monthly_playlists(sp)
            
            # Update monthly playlists
            month_to_tracks = update_monthly_playlists(
                sp, current_month_only=not args.all_months
            )
            if month_to_tracks:
                summary["months_processed"] = len(month_to_tracks)
            
            # Update genre-split playlists
            if month_to_tracks:
                update_genre_split_playlists(sp, month_to_tracks)
            
            # Update master genre playlists
            update_master_genre_playlists(sp)
        
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
        return
    
    log_output = "\n".join(_log_buffer)
    
    try:
        send_email_notification(
            success=success,
            log_output=log_output,
            summary=summary or {},
            error=error
        )
    except Exception as e:
        # Don't fail the sync if email fails
        print(f"⚠️  Email notification error (non-fatal): {e}")


if __name__ == "__main__":
    main()

