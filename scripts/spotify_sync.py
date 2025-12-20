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
        PLAYLIST_OWNER_NAME     - Prefix for playlist names (default: "")
        PLAYLIST_PREFIX         - Month playlist prefix (default: "Finds")

Run via cron or GitHub Actions:
    # Linux/Mac cron (every day at 2am):
    0 2 * * * /path/to/python /path/to/spotify_sync.py
    
    # GitHub Actions - uses refresh token for headless auth
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

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Try to import spotim8 for full library sync
try:
    from spotim8 import Spotim8, CacheConfig, set_response_cache
    SPOTIM8_AVAILABLE = True
except ImportError:
    SPOTIM8_AVAILABLE = False


# ============================================================================
# CONFIGURATION - Set via environment variables
# ============================================================================

OWNER_NAME = os.environ.get("PLAYLIST_OWNER_NAME", "")
PREFIX = os.environ.get("PLAYLIST_PREFIX", "Finds")

# Playlist naming templates
MONTHLY_NAME_TEMPLATE = "{owner}{prefix}{mon}{year}"
GENRE_MONTHLY_TEMPLATE = "{genre}{prefix}{mon}{year}"
GENRE_NAME_TEMPLATE = "{owner}am{genre}"

# Genre categories for split playlists
SPLIT_GENRES = ["HipHop", "Dance", "Other"]

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

# Genre classification rules for split playlists (HipHop/Dance/Other)
GENRE_SPLIT_RULES = {
    "HipHop": [
        "hip hop", "rap", "trap", "drill", "grime", "crunk", "phonk",
        "boom bap", "dirty south", "gangsta", "uk drill", "melodic rap",
        "conscious hip hop", "underground hip hop", "southern hip hop"
    ],
    "Dance": [
        "electronic", "edm", "house", "techno", "trance", "dubstep",
        "drum and bass", "ambient", "garage", "deep house", "minimal",
        "synthwave", "future bass", "electro", "dance", "electronica",
        "uk garage", "breakbeat", "hardstyle", "progressive house"
    ]
}

# Broad genre classification for master playlists
GENRE_RULES = [
    (["hip hop", "rap", "trap", "drill", "grime", "crunk", "boom bap", "dirty south", "phonk"], "Hip-Hop"),
    (["r&b", "rnb", "soul", "neo soul", "funk", "motown", "disco"], "R&B/Soul"),
    (["electronic", "edm", "house", "techno", "trance", "dubstep", "drum and bass", "ambient"], "Electronic"),
    (["rock", "alternative", "grunge", "punk", "emo", "post-punk", "shoegaze"], "Rock"),
    (["metal", "heavy metal", "death metal", "black metal", "thrash"], "Metal"),
    (["indie", "indie rock", "indie pop", "lo-fi", "dream pop"], "Indie"),
    (["pop", "dance pop", "synth pop", "electropop"], "Pop"),
    (["latin", "reggaeton", "salsa", "bachata", "cumbia"], "Latin"),
    (["afrobeat", "k-pop", "reggae", "dancehall", "world"], "World"),
    (["jazz", "smooth jazz", "bebop", "swing"], "Jazz"),
    (["classical", "orchestra", "symphony", "opera"], "Classical"),
    (["country", "folk", "americana", "bluegrass"], "Country/Folk"),
]


# ============================================================================
# UTILITIES
# ============================================================================

def log(msg: str) -> None:
    """Print message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


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


def get_split_genre(genre_list: list) -> str:
    """Map genres to HipHop, Dance, or Other."""
    if not genre_list:
        return "Other"
    combined = " ".join(genre_list).lower()
    for genre_name, keywords in GENRE_SPLIT_RULES.items():
        if any(kw in combined for kw in keywords):
            return genre_name
    return "Other"


def get_broad_genre(genre_list: list) -> str | None:
    """Map genres to broad category for master playlists."""
    if not genre_list:
        return None
    combined = " ".join(genre_list).lower()
    for keywords, category in GENRE_RULES:
        if any(kw in combined for kw in keywords):
            return category
    return None


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
        page = sp.current_user_playlists(limit=50, offset=offset)
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
        page = sp.playlist_items(
            playlist_id, 
            fields="items(track(uri)),next", 
            limit=100, 
            offset=offset
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
        
        # Sync library (incremental - only fetches changes)
        stats = sf.sync(
            owned_only=True,
            include_liked_songs=True
        )
        
        log(f"✅ Library sync complete: {stats}")
        
        # Force regenerate derived tables
        _ = sf.tracks()
        _ = sf.artists()
        _ = sf.library_wide()
        
        log("✅ All parquet files updated")
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
    offset = 0
    
    while True:
        page = sp.current_user_saved_tracks(limit=50, offset=offset)
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
        
        if not page.get("next"):
            break
        offset += 50
        
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
        # Remove old liked songs and add new
        existing = existing[existing["playlist_id"] != LIKED_SONGS_PLAYLIST_ID]
        df = pd.concat([existing, df], ignore_index=True)
    
    df.to_parquet(playlist_tracks_path, index=False)
    log(f"  Saved to {playlist_tracks_path}")
    
    return liked_tracks


def sync_artists(sp: spotipy.Spotify, track_ids: list) -> tuple:
    """Sync artist data for tracks."""
    log("Syncing artist data...")
    
    all_artists = {}
    track_artists_data = []
    
    for chunk in _chunked(list(track_ids), 50):
        tracks = sp.tracks(chunk)
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
    artist_ids = list(all_artists.keys())
    for chunk in _chunked(artist_ids, 50):
        artists = sp.artists(chunk)
        for artist in artists.get("artists", []):
            if artist:
                all_artists[artist["id"]]["genres"] = artist.get("genres", [])
    
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
    user_id = sp.current_user()["id"]
    
    for month, uris in sorted(month_to_tracks.items()):
        if not uris:
            continue
        
        name = format_playlist_name(MONTHLY_NAME_TEMPLATE, month)
        
        if name in existing:
            pid = existing[name]
            already = get_playlist_tracks(sp, pid)
            to_add = [u for u in uris if u not in already]
            
            if to_add:
                for chunk in _chunked(to_add, 100):
                    sp.playlist_add_items(pid, chunk)
                log(f"  {name}: +{len(to_add)} tracks")
            else:
                log(f"  {name}: up to date")
        else:
            pl = sp.user_playlist_create(
                user_id, name, public=False,
                description=f"Liked songs from {month}"
            )
            pid = pl["id"]
            
            for chunk in _chunked(uris, 100):
                sp.playlist_add_items(pid, chunk)
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
    user_id = sp.current_user()["id"]
    
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
                    for chunk in _chunked(to_add, 100):
                        sp.playlist_add_items(pid, chunk)
                    log(f"  {name}: +{len(to_add)} tracks")
            else:
                pl = sp.user_playlist_create(
                    user_id, name, public=False,
                    description=f"{genre} tracks from {month}"
                )
                pid = pl["id"]
                
                for chunk in _chunked(genre_uris, 100):
                    sp.playlist_add_items(pid, chunk)
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
    user_id = sp.current_user()["id"]
    
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
                for chunk in _chunked(to_add, 100):
                    sp.playlist_add_items(pid, chunk)
                log(f"  {name}: +{len(to_add)} tracks")
        else:
            pl = sp.user_playlist_create(
                user_id, name, public=False,
                description=f"All liked songs - {genre}"
            )
            pid = pl["id"]
            
            for chunk in _chunked(uris, 100):
                sp.playlist_add_items(pid, chunk)
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
        user = sp.current_user()
        log(f"Authenticated as: {user['display_name']} ({user['id']})")
    except Exception as e:
        log(f"ERROR: Authentication failed: {e}")
        sys.exit(1)
    
    try:
        # Data sync phase
        if not args.skip_sync:
            # Full library sync using spotim8
            sync_full_library()
            
            # Sync liked songs
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

