#!/usr/bin/env python3
"""
Unified Spotify Sync & Playlist Update

This script:
1. Syncs your Spotify library to local parquet files (optional)
2. Updates monthly playlists with liked songs
3. Updates genre-split monthly playlists
4. Updates master genre playlists

Usage:
    python scripts/spotify_sync.py              # Full sync + update
    python scripts/spotify_sync.py --skip-sync  # Update only (fast, uses existing data)
    python scripts/spotify_sync.py --sync-only  # Sync only, no playlist changes
    python scripts/spotify_sync.py --all-months # Process all months, not just current

Environment Variables:
    Required:
        SPOTIPY_CLIENT_ID       - Spotify app client ID
        SPOTIPY_CLIENT_SECRET   - Spotify app client secret
    
    Optional:
        SPOTIPY_REDIRECT_URI    - Redirect URI (default: http://127.0.0.1:8888/callback)
        SPOTIPY_REFRESH_TOKEN   - Refresh token for headless/CI auth
        PLAYLIST_OWNER_NAME     - Prefix for playlist names (default: "AJ")
        PLAYLIST_PREFIX         - Month playlist prefix (default: "Finds")

Run locally or via cron:
    # Direct run:
    python scripts/spotify_sync.py
    
    # Linux/Mac cron (every day at 2am):
    0 2 * * * cd /path/to/spotim8 && ./scripts/run_sync_local.sh
    
    # Uses refresh token for headless/automated auth
"""

import argparse
import ast
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import random
import requests

# Adaptive backoff multiplier (increases after rate errors, decays on success)
_RATE_BACKOFF_MULTIPLIER = 1.0
_RATE_BACKOFF_MAX = 16.0

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Try to import spotim8 for full library sync
try:
    from spotim8 import Spotim8, CacheConfig, set_response_cache
    SPOTIM8_AVAILABLE = True
except ImportError:
    SPOTIM8_AVAILABLE = False

# Import exhaustive genre rules from shared module
from spotim8.genres import (
    GENRE_SPLIT_RULES, SPLIT_GENRES, GENRE_RULES,
    get_split_genre, get_broad_genre
)


# ============================================================================
# CONFIGURATION - Set via environment variables
# ============================================================================

OWNER_NAME = os.environ.get("PLAYLIST_OWNER_NAME", "AJ")
PREFIX = os.environ.get("PLAYLIST_PREFIX", "Finds")

# Playlist naming templates
MONTHLY_NAME_TEMPLATE = "{owner}{prefix}{mon}{year}"
GENRE_MONTHLY_TEMPLATE = "{genre}{prefix}{mon}{year}"
GENRE_NAME_TEMPLATE = "{owner}am{genre}"

# Master genre playlist limits
MIN_TRACKS_FOR_GENRE = 20
MAX_GENRE_PLAYLISTS = 19

# Paths
DATA_DIR = PROJECT_ROOT / "data"
LIKED_SONGS_PLAYLIST_ID = "liked_songs"

# Month name mapping
MONTH_NAMES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
}

# Genre rules imported from spotim8.genres module (exhaustive list)
# See spotim8/genres.py for the full definitions of:
# - GENRE_SPLIT_RULES (HipHop, Dance keywords)
# - SPLIT_GENRES (["HipHop", "Dance", "Other"])
# - GENRE_RULES (broad category mappings)
# - get_split_genre() and get_broad_genre() functions


# ============================================================================
# UTILITIES
# ============================================================================

def log(msg: str) -> None:
    """Print message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


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
        raise ValueError("Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET")
    
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
    if not genre_data:
        return []
    if isinstance(genre_data, list):
        return genre_data
    if isinstance(genre_data, np.ndarray):
        return list(genre_data)
    if isinstance(genre_data, str):
        try:
            return ast.literal_eval(genre_data)
        except (ValueError, SyntaxError):
            return [genre_data]
    return []


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


# ============================================================================
# SPOTIFY API HELPERS
# ============================================================================

def get_existing_playlists(sp: spotipy.Spotify) -> dict:
    """Get all user playlists as {name: id} mapping."""
    mapping = {}
    offset = 0
    while True:
        page = api_call(sp.current_user_playlists, limit=50, offset=offset)
        for item in page.get("items", []):
            mapping[item["name"]] = item["id"]
        if not page.get("next"):
            break
        offset += 50
    return mapping


def get_playlist_tracks(sp: spotipy.Spotify, playlist_id: str) -> set:
    """Get all track URIs in a playlist."""
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
    return uris


# ============================================================================
# DATA SYNC FUNCTIONS
# ============================================================================

def sync_full_library() -> bool:
    """
    Sync full library using spotim8 - updates all parquet files.
    
    Uses incremental sync - only fetches playlists that have changed
    based on Spotify's snapshot_id mechanism.
    
    Updates:
    - playlists.parquet
    - playlist_tracks.parquet  
    - tracks.parquet
    - track_artists.parquet
    - artists.parquet
    """
    if not SPOTIM8_AVAILABLE:
        log("⚠️  spotim8 not available, skipping full library sync")
        return False
    
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
        stats = sf.sync(
            owned_only=True,
            include_liked_songs=True
        )
        
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
        
        return True
        
    except Exception as e:
        log(f"⚠️  Full library sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def sync_liked_songs(sp: spotipy.Spotify) -> list:
    """Sync liked songs from Spotify API and save to parquet."""
    log("Syncing liked songs from Spotify...")
    
    liked_tracks = []
    # Support resuming long syncs using a checkpoint file
    checkpoint_path = DATA_DIR / ".liked_sync_offset"
    offset = 0
    if checkpoint_path.exists():
        try:
            offset = int(checkpoint_path.read_text().strip() or 0)
            log(f"Resuming liked songs sync from offset {offset}")
        except Exception:
            offset = 0
    
    while True:
        page = api_call(sp.current_user_saved_tracks, limit=50, offset=offset)
        items = page.get("items", [])
        
        if not items:
            break
        
        for item in items:
            track = item.get("track", {})
            if track.get("id"):
                liked_tracks.append({
                    "playlist_id": LIKED_SONGS_PLAYLIST_ID,
                    "track_id": track["id"],
                    "added_at": item.get("added_at"),
                    "track_name": track.get("name"),
                    "track_uri": track.get("uri"),
                })
        
        # Advance offset and write checkpoint so we can resume if the job times out
        if not page.get("next"):
            offset += len(items)
            try:
                DATA_DIR.mkdir(exist_ok=True)
                checkpoint_path.write_text(str(offset))
            except Exception:
                pass
            break
        offset += len(items)
        try:
            DATA_DIR.mkdir(exist_ok=True)
            checkpoint_path.write_text(str(offset))
        except Exception:
            pass
        
        if offset % 500 == 0:
            log(f"  Fetched {offset} liked songs...")
    
    log(f"  Total: {len(liked_tracks)} liked songs")
    
    # Save to parquet
    df = pd.DataFrame(liked_tracks)
    DATA_DIR.mkdir(exist_ok=True)
    
    # Load existing or create new
    playlist_tracks_path = DATA_DIR / "playlist_tracks.parquet"
    if playlist_tracks_path.exists():
        existing = pd.read_parquet(playlist_tracks_path)
        # If resuming (checkpoint exists), assume earlier pages are already in `existing`.
        if checkpoint_path.exists():
            # Append only newly fetched rows (avoid duplicating existing liked songs)
            df = pd.concat([existing, df], ignore_index=True)
        else:
            # Remove old liked songs and add new
            existing = existing[existing["playlist_id"] != LIKED_SONGS_PLAYLIST_ID]
            df = pd.concat([existing, df], ignore_index=True)
    
    df.to_parquet(playlist_tracks_path, index=False)
    log(f"  Saved to {playlist_tracks_path}")
    # Sync complete - remove checkpoint
    try:
        if checkpoint_path.exists():
            checkpoint_path.unlink()
    except Exception:
        pass
    
    return liked_tracks


def sync_artists(sp: spotipy.Spotify, track_ids: list) -> tuple:
    """Sync artist data for tracks."""
    log("Syncing artist data...")
    
    all_artists = {}
    track_artists_data = []
    # Support resuming artist sync via checkpointing (store processed artist ids)
    artist_checkpoint = DATA_DIR / ".artist_sync_done"
    processed_artists = set()
    if artist_checkpoint.exists():
        try:
            processed_artists = set(artist_checkpoint.read_text().splitlines())
            log(f"Resuming artist sync, already processed {len(processed_artists)} artists")
        except Exception:
            processed_artists = set()
    
    for chunk in _chunked(list(track_ids), 50):
        tracks = api_call(sp.tracks, chunk)
        for track in tracks.get("tracks", []):
            if not track:
                continue
            tid = track["id"]
            for artist in track.get("artists", []):
                aid = artist["id"]
                track_artists_data.append({"track_id": tid, "artist_id": aid})
                if aid not in all_artists:
                    all_artists[aid] = {"artist_id": aid, "name": artist.get("name")}
    
    # Get full artist info (including genres)
    artist_ids = [aid for aid in all_artists.keys() if aid not in processed_artists]
    for chunk in _chunked(artist_ids, 50):
        artists = api_call(sp.artists, chunk)
        for artist in artists.get("artists", []):
            if artist:
                all_artists[artist["id"]]["genres"] = artist.get("genres", [])
                # Mark artist as processed in checkpoint
                try:
                    DATA_DIR.mkdir(exist_ok=True)
                    with artist_checkpoint.open("a") as f:
                        f.write(artist["id"] + "\n")
                except Exception:
                    pass
    
    # Save
    artists_df = pd.DataFrame(list(all_artists.values()))
    artists_df.to_parquet(DATA_DIR / "artists.parquet", index=False)
    
    track_artists_df = pd.DataFrame(track_artists_data)
    track_artists_df.to_parquet(DATA_DIR / "track_artists.parquet", index=False)
    
    log(f"  Saved {len(artists_df)} artists, {len(track_artists_df)} track-artist links")
    
    return artists_df, track_artists_df


# ============================================================================
# PLAYLIST UPDATE FUNCTIONS
# ============================================================================

def update_monthly_playlists(sp: spotipy.Spotify, current_month_only: bool = True) -> dict:
    """Update monthly playlists with liked songs."""
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
    
    # Get existing playlists
    existing = get_existing_playlists(sp)
    user = api_call(sp.current_user)
    user_id = user["id"]
    
    for month, uris in sorted(month_to_tracks.items()):
        if not uris:
            continue
        
        name = format_playlist_name(MONTHLY_NAME_TEMPLATE, month)
        if name in existing:
            pid = existing[name]
            already = get_playlist_tracks(sp, pid)
            to_add = [u for u in uris if u not in already]

            if to_add:
                for chunk in _chunked(to_add, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                log(f"  {name}: +{len(to_add)} tracks")
            else:
                log(f"  {name}: up to date")
        else:
            pl = api_call(
                sp.user_playlist_create,
                user_id,
                name,
                public=False,
                description=f"Liked songs from {month}",
            )
            pid = pl["id"]

            for chunk in _chunked(uris, 50):
                api_call(sp.playlist_add_items, pid, chunk)
            log(f"  {name}: created with {len(uris)} tracks")
    
    return month_to_tracks


def update_genre_split_playlists(sp: spotipy.Spotify, month_to_tracks: dict) -> None:
    """Update genre-split monthly playlists (HipHop, Dance, Other)."""
    if not month_to_tracks:
        return
    
    log("\n--- Genre-Split Playlists ---")
    
    # Load genre data
    track_artists = pd.read_parquet(DATA_DIR / "track_artists.parquet")
    artists = pd.read_parquet(DATA_DIR / "artists.parquet")
    
    artist_genres_map = artists.set_index("artist_id")["genres"].to_dict()
    
    # Build track -> genre mapping
    all_uris = set(u for uris in month_to_tracks.values() for u in uris)
    track_ids = {u.split(":")[-1] for u in all_uris if u.startswith("spotify:track:")}
    
    track_to_genre = {}
    for _, row in track_artists[track_artists["track_id"].isin(track_ids)].iterrows():
        tid = row["track_id"]
        uri = f"spotify:track:{tid}"
        
        if uri in track_to_genre:
            continue
        
        artist_genres = _parse_genres(artist_genres_map.get(row["artist_id"], []))
        track_to_genre[uri] = get_split_genre(artist_genres)
    
    # Get existing playlists
    existing = get_existing_playlists(sp)
    user = api_call(sp.current_user)
    user_id = user["id"]
    
    for month, uris in sorted(month_to_tracks.items()):
        for genre in SPLIT_GENRES:
            genre_uris = [u for u in uris if track_to_genre.get(u) == genre]
            
            if not genre_uris:
                continue
            
            name = format_playlist_name(GENRE_MONTHLY_TEMPLATE, month, genre)
            
            if name in existing:
                pid = existing[name]
                already = get_playlist_tracks(sp, pid)
                to_add = [u for u in genre_uris if u not in already]

                if to_add:
                    for chunk in _chunked(to_add, 50):
                        api_call(sp.playlist_add_items, pid, chunk)
                    log(f"  {name}: +{len(to_add)} tracks")
            else:
                pl = api_call(
                    sp.user_playlist_create,
                    user_id,
                    name,
                    public=False,
                    description=f"{genre} tracks from {month}",
                )
                pid = pl["id"]

                for chunk in _chunked(genre_uris, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                log(f"  {name}: created with {len(genre_uris)} tracks")


def update_master_genre_playlists(sp: spotipy.Spotify) -> None:
    """Update master genre playlists with all liked songs by genre."""
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
    
    # Build genre mapping
    artist_genres_map = artists.set_index("artist_id")["genres"].to_dict()
    
    uri_to_genre = {}
    for _, row in track_artists[track_artists["track_id"].isin(liked_ids)].iterrows():
        tid = row["track_id"]
        uri = f"spotify:track:{tid}"
        
        if uri in uri_to_genre:
            continue
        
        artist_genres = _parse_genres(artist_genres_map.get(row["artist_id"], []))
        broad = get_broad_genre(artist_genres)
        if broad:
            uri_to_genre[uri] = broad
    
    # Select top genres
    genre_counts = Counter(uri_to_genre.values())
    selected = [g for g, n in genre_counts.most_common(MAX_GENRE_PLAYLISTS) 
                if n >= MIN_TRACKS_FOR_GENRE]
    
    # Get existing playlists
    existing = get_existing_playlists(sp)
    user = api_call(sp.current_user)
    user_id = user["id"]
    
    for genre in selected:
        uris = [u for u in liked_uris if uri_to_genre.get(u) == genre]
        if not uris:
            continue
        
        name = GENRE_NAME_TEMPLATE.format(owner=OWNER_NAME, genre=genre)
        
        if name in existing:
            pid = existing[name]
            already = get_playlist_tracks(sp, pid)
            to_add = [u for u in uris if u not in already]

            if to_add:
                for chunk in _chunked(to_add, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                log(f"  {name}: +{len(to_add)} tracks")
        else:
            pl = api_call(
                sp.user_playlist_create,
                user_id,
                name,
                public=False,
                description=f"All liked songs - {genre}",
            )
            pid = pl["id"]

            for chunk in _chunked(uris, 50):
                api_call(sp.playlist_add_items, pid, chunk)
            log(f"  {name}: created with {len(uris)} tracks")


# ============================================================================
# MAIN
# ============================================================================

def main():
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
    
    # Authenticate
    try:
        sp = get_spotify_client()
        user = api_call(sp.current_user)
        log(f"Authenticated as: {user['display_name']} ({user['id']})")
    except Exception as e:
        log(f"ERROR: Authentication failed: {e}")
        sys.exit(1)
    
    try:
        # Data sync phase
        if not args.skip_sync:
            # Full library sync using spotim8 (includes liked songs and artists)
            spotim8_synced = sync_full_library()
            
            # Only use fallback sync if spotim8 is not available
            if not spotim8_synced:
                log("Using fallback sync (spotim8 not available)")
                liked_tracks = sync_liked_songs(sp)
                
                if liked_tracks:
                    # Sync artists for genre info
                    track_ids = [t["track_id"] for t in liked_tracks]
                    sync_artists(sp, track_ids)
        
        # Playlist update phase
        if not args.sync_only:
            # Update monthly playlists
            month_to_tracks = update_monthly_playlists(
                sp, current_month_only=not args.all_months
            )
            
            # Update genre-split playlists
            if month_to_tracks:
                update_genre_split_playlists(sp, month_to_tracks)
            
            # Update master genre playlists
            update_master_genre_playlists(sp)
        
        log("\n" + "=" * 60)
        log("✅ Complete!")
        log("=" * 60)
        
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

