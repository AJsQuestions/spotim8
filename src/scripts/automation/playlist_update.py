"""
Playlist update utilities.

Functions for updating monthly, genre-split, and master genre playlists.

This module is extracted from sync.py and uses late imports to access
utilities from sync.py to avoid circular dependencies.
"""

import spotipy
import pandas as pd
from datetime import datetime

from .formatting import format_playlist_name, format_playlist_description
from src.features.genres import get_all_split_genres, get_all_broad_genres, SPLIT_GENRES

def update_monthly_playlists(sp: spotipy.Spotify, keep_last_n_months: int = 3) -> dict:
    """Update monthly playlists for all types (Finds, Discover).
    
    Only creates/updates monthly playlists for the last N months (default: 3).
    Older months are automatically consolidated into yearly playlists.
    
    Data Sources:
    - "Finds" playlists: Use API data (liked songs) - always up-to-date
    - Top and Discovery playlists: Use streaming history from exports (Vibes/OnRepeat removed)
      - Streaming history is updated periodically and may lag behind API data
      - Recent months may be incomplete if export is outdated
      - Missing history results in empty playlists for those types
    
    Args:
        keep_last_n_months: Number of recent months to keep as monthly playlists (default: 3)
    
    Note: This function only ADDS tracks to playlists. It never removes tracks.
    Manually added tracks are preserved and will remain in the playlists.
    """
    # Late imports from sync.py
    from .sync import (
        log, verbose_log, DATA_DIR, ENABLE_MONTHLY, ENABLE_MOST_PLAYED, ENABLE_DISCOVERY,
        LIKED_SONGS_PLAYLIST_ID, MONTHLY_NAME_TEMPLATE, get_existing_playlists, get_user_info, get_playlist_tracks, api_call,
        _chunked, _update_playlist_description_with_genres, _playlist_tracks_cache
    )
    log(f"\n--- Monthly Playlists (Last {keep_last_n_months} Months Only) ---")
    
    # Log enabled playlist types
    # NOTE: Only "Finds" playlists are created monthly. Top/Dscvr are yearly only.
    enabled_types = []
    if ENABLE_MONTHLY:
        enabled_types.append("Finds (monthly)")
    if ENABLE_MOST_PLAYED:
        enabled_types.append("Top (yearly only)")
    # Vbz/Rpt removed - only Top and Discovery kept for yearly
    # if ENABLE_TIME_BASED:
    #     enabled_types.append("Vbz (yearly only)")
    # if ENABLE_REPEAT:
    #     enabled_types.append("Rpt (yearly only)")
    if ENABLE_DISCOVERY:
        enabled_types.append("Dscvr (yearly only)")
    
    if enabled_types:
        log(f"  Enabled playlist types: {', '.join(enabled_types)}")
        log(f"  📌 Note: Top/Dscvr are created as yearly playlists only (no monthly). Vbz/Rpt removed.")
    else:
        log("  ⚠️  No playlist types enabled - check .env file")
        return {}
    
    # Load streaming history for Top/Vibes/OnRepeat/Discover playlists
    # NOTE: Streaming history comes from periodic Spotify exports and may lag behind API data.
    # API data (liked songs) is always more up-to-date than streaming history exports.
    # If streaming history is missing or incomplete, these playlist types will be empty or incomplete.
    from src.analysis.streaming_history import load_streaming_history
    history_df = load_streaming_history(DATA_DIR)
    if history_df is not None and not history_df.empty:
        # Ensure timestamp is datetime
        if 'timestamp' in history_df.columns:
            history_df['timestamp'] = pd.to_datetime(history_df['timestamp'], errors='coerce', utc=True)
        
        # Check data freshness - warn if streaming history is significantly behind
        # Streaming history comes from periodic exports, so it may lag behind API data
        if 'timestamp' in history_df.columns:
            try:
                latest_history = history_df['timestamp'].max()
                if pd.notna(latest_history):
                    # Convert to naive datetime for comparison if needed
                    if latest_history.tzinfo:
                        latest_naive = latest_history.replace(tzinfo=None)
                        now = datetime.now()
                    else:
                        latest_naive = latest_history
                        now = datetime.now()
                    
                    days_behind = (now - latest_naive).days
                    if days_behind > 30:
                        latest_str = latest_history.strftime('%Y-%m-%d') if hasattr(latest_history, 'strftime') else str(latest_history)
                        log(f"  ⚠️  Streaming history is {days_behind} days old (latest: {latest_str})")
                        log(f"      Recent months may be incomplete. Export new data for up-to-date playlists.")
            except Exception:
                pass  # Skip freshness check if there's an error
        
        log(f"  Loaded streaming history: {len(history_df):,} records")
    else:
        log("  ⚠️  No streaming history found - Discovery playlists will be empty")
        log("      Export streaming history data to enable these playlist types")
    
    # Load liked songs data for "Finds" playlists (API data only - never uses streaming history)
    playlist_tracks_path = DATA_DIR / "playlist_tracks.parquet"
    all_month_to_tracks = {}
    
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
                liked["month"] = liked[added_col].dt.to_period("M").astype(str)
                
                # Handle both track_uri and track_id columns
                if "track_uri" in liked.columns:
                    liked["_uri"] = liked["track_uri"]
                else:
                    liked["_uri"] = liked["track_id"].map(_to_uri)
                
                # Build month -> tracks mapping for "Finds" playlists (API data only)
                for month, group in liked.groupby("month"):
                    uris = group["_uri"].dropna().tolist()
                    seen = set()
                    unique = [u for u in uris if not (u in seen or seen.add(u))]
                    all_month_to_tracks[month] = {"monthly": unique}
                
                log(f"  Loaded liked songs (API data) for 'Finds' playlists: {len(all_month_to_tracks)} month(s)")
        else:
            log("  ⚠️  No liked songs found in library data - 'Finds' playlists will be empty")
    else:
        log("  ⚠️  Library data not found - 'Finds' playlists will be empty (run full sync first)")
    
    # Get months for "Finds" playlists (API data only - liked songs)
    finds_months = set(all_month_to_tracks.keys())
    
    # Get months for other playlist types (streaming history)
    history_months = set()
    if history_df is not None and not history_df.empty:
        history_df['month'] = history_df['timestamp'].dt.to_period('M').astype(str)
        history_months = set(history_df['month'].unique())
    
    # For "Finds" playlists, only use months from API data (liked songs)
    # For Discovery playlists, use months from streaming history (Top/Vibes removed)
    # Combine for processing, but "Finds" will only use API data
    all_months = finds_months | history_months
    
    # Filter to only the last N months
    if all_months:
        sorted_months = sorted(all_months)
        recent_months = sorted_months[-keep_last_n_months:]
        older_months = [m for m in sorted_months if m not in recent_months]
        if older_months:
            log(f"📅 Keeping {len(recent_months)} recent months as monthly playlists: {', '.join(recent_months)}")
            log(f"📦 {len(older_months)} older months will be consolidated into yearly playlists")
            if finds_months:
                finds_recent = [m for m in recent_months if m in finds_months]
                log(f"   📌 'Finds' playlists will use API data (liked songs) for {len(finds_recent)} month(s)")
    else:
        recent_months = []
    
    if not recent_months:
        log("No months to process")
        return {}
    
    log(f"Processing {len(recent_months)} month(s) for all playlist types...")
    
    # Get existing playlists (cached)
    existing = get_existing_playlists(sp)
    user = get_user_info(sp)
    user_id = user["id"]
    
    # Define playlist types and their configurations
    # "Finds" playlists use API data (liked songs) only - never streaming history
    # Other playlists use streaming history data
    # Only include playlist types that are enabled in .env
    # NOTE: Dscvr is created as yearly playlists only (no monthly). Top/Vbz/Rpt removed.
    # Only "Finds" playlists are created monthly
    playlist_configs = []
    
    if ENABLE_MONTHLY:
        playlist_configs.append((
            "monthly", MONTHLY_NAME_TEMPLATE, "Liked songs", 
            lambda m: all_month_to_tracks.get(m, {}).get("monthly", [])  # API data only
        ))
    
    # Top/Vbz/Rpt/Dscvr are NOT created as monthly playlists - only yearly
    # They are created in consolidate_old_monthly_playlists() for all years with streaming history
    
    if not playlist_configs:
        log("⚠️  All playlist types are disabled in .env file. No playlists will be created.")
        return {}
    
    month_to_tracks = {}
    
    for month in sorted(recent_months):
        month_to_tracks[month] = {}
        
        for playlist_type, template, description, get_tracks_fn in playlist_configs:
            # Get tracks for this playlist type and month
            track_uris = get_tracks_fn(month)
            
            if not track_uris:
                continue
            
            month_to_tracks[month][playlist_type] = track_uris
            
            # Format playlist name (all types use monthly format for monthly playlists)
            name = format_playlist_name(template, month, playlist_type=playlist_type)
            
            # Check for duplicate
            if name in existing:
                pid = existing[name]
                already = get_playlist_tracks(sp, pid)
                to_add = [u for u in track_uris if u not in already]
                
                if to_add:
                    for chunk in _chunked(to_add, 50):
                        api_call(sp.playlist_add_items, pid, chunk)
                    if pid in _playlist_tracks_cache:
                        del _playlist_tracks_cache[pid]
                    log(f"  {name}: +{len(to_add)} tracks ({len(track_uris)} total)")
                    # Update description with genre tags
                    _update_playlist_description_with_genres(sp, user_id, pid, track_uris)
                else:
                    log(f"  {name}: up to date ({len(track_uris)} tracks)")
                    # Still update genre tags even if no new tracks (genres might have changed in data)
                    _update_playlist_description_with_genres(sp, user_id, pid, track_uris)
            else:
                # Calculate last date of the month for creation date reference
                from calendar import monthrange
                year, month_num = map(int, month.split("-"))
                last_day = monthrange(year, month_num)[1]
                created_at = datetime(year, month_num, last_day, 23, 59, 59)
                
                # Create playlist
                verbose_log(f"Creating new playlist '{name}' for {month} (type={playlist_type})...")
                pl = api_call(
                    sp.user_playlist_create,
                    user_id,
                    name,
                    public=False,
                    description=format_playlist_description(description, period=month, playlist_type=playlist_type),
                )
                pid = pl["id"]
                verbose_log(f"  Created playlist '{name}' with id {pid}")
                
                # Add tracks
                verbose_log(f"  Adding {len(track_uris)} tracks in chunks...")
                chunk_count = 0
                for chunk in _chunked(track_uris, 50):
                    chunk_count += 1
                    verbose_log(f"    Adding chunk {chunk_count} ({len(chunk)} tracks)...")
                    api_call(sp.playlist_add_items, pid, chunk)
                
                # Update description with genre tags
                _update_playlist_description_with_genres(sp, user_id, pid, track_uris)
                
                _invalidate_playlist_cache()
                verbose_log(f"  Invalidated playlist cache after creating new playlist")
                log(f"  {name}: created with {len(track_uris)} tracks")
    
    return month_to_tracks




def update_genre_split_playlists(sp: spotipy.Spotify, month_to_tracks: dict) -> None:
    """Update genre-split monthly playlists (HipHop, Dance, Other).
    
    Note: This function only ADDS tracks from liked songs. It never removes tracks.
    Manually added tracks are preserved and will remain in the playlists.
    """
    # Late imports from sync.py
    from .sync import (
        log, verbose_log, DATA_DIR, ENABLE_MONTHLY, ENABLE_MOST_PLAYED, ENABLE_DISCOVERY,
        LIKED_SONGS_PLAYLIST_ID, GENRE_MONTHLY_TEMPLATE, get_existing_playlists, get_user_info, get_playlist_tracks, api_call,
        _chunked, _update_playlist_description_with_genres, _playlist_tracks_cache,
        _parse_genres, _get_all_track_genres
    )
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
            
            name = format_playlist_name(GENRE_MONTHLY_TEMPLATE, month, genre, playlist_type="genre_monthly")
            
            if name in existing:
                pid = existing[name]
                # Get existing tracks (includes both auto-added and manually added tracks)
                already = get_playlist_tracks(sp, pid)
                # Only add tracks that aren't already present (preserves manual additions)
                to_add = [u for u in genre_uris if u not in already]

                if to_add:
                    verbose_log(f"Adding {len(to_add)} tracks to playlist '{name}' (playlist_id={pid})")
                    chunk_count = 0
                    for chunk in _chunked(to_add, 50):
                        chunk_count += 1
                        verbose_log(f"  Adding chunk {chunk_count} ({len(chunk)} tracks)...")
                        api_call(sp.playlist_add_items, pid, chunk)
                    # Invalidate cache for this playlist since we added tracks
                    if pid in _playlist_tracks_cache:
                        del _playlist_tracks_cache[pid]
                        verbose_log(f"  Invalidated cache for playlist {pid}")
                    log(f"  {name}: +{len(to_add)} tracks (manually added tracks preserved)")
                    # Update description with genre tags (use all tracks in playlist)
                    _update_playlist_description_with_genres(sp, user_id, pid, None)
            else:
                pl = api_call(
                    sp.user_playlist_create,
                    user_id,
                    name,
                    public=False,
                    description=format_playlist_description(f"{genre} tracks", period=month, genre=genre, playlist_type="genre_monthly"),
                )
                pid = pl["id"]

                for chunk in _chunked(genre_uris, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                # Update description with genre tags
                _update_playlist_description_with_genres(sp, user_id, pid, genre_uris)
                # Invalidate playlist cache since we created a new playlist
                _invalidate_playlist_cache()
                log(f"  {name}: created with {len(genre_uris)} tracks")




def _remove_genre_from_track(tracks_df: pd.DataFrame, track_uri: str, genre_to_remove: str) -> bool:
    """Remove a genre tag from a track's stored genres.
    
    Args:
        tracks_df: DataFrame with tracks data (will be modified in place)
        track_uri: Track URI (e.g., "spotify:track:abc123")
        genre_to_remove: Genre name to remove from track
    
    Returns:
        True if genre was removed, False otherwise
    """
    from .sync import (
        log, verbose_log, DATA_DIR, ENABLE_MONTHLY, ENABLE_MOST_PLAYED, ENABLE_DISCOVERY,
        LIKED_SONGS_PLAYLIST_ID, get_playlist_tracks, api_call,
        _chunked, _update_playlist_description_with_genres, _playlist_tracks_cache
    )
    
    # Extract track_id from URI
    if not track_uri.startswith("spotify:track:"):
        return False
    track_id = track_uri.split(":")[-1]
    
    # Find the track in the dataframe
    track_mask = tracks_df["track_id"] == track_id
    if not track_mask.any():
        return False
    
    track_idx = tracks_df[track_mask].index[0]
    current_genres = _parse_genres(tracks_df.at[track_idx, "genres"])
    
    if not current_genres:
        return False
    
    # Remove the genre (case-insensitive comparison)
    genre_to_remove_lower = genre_to_remove.lower()
    updated_genres = [g for g in current_genres if g.lower() != genre_to_remove_lower]
    
    # Only update if something changed
    if len(updated_genres) != len(current_genres):
        tracks_df.at[track_idx, "genres"] = updated_genres if updated_genres else []
        return True
    
    return False


def update_master_genre_playlists(sp: spotipy.Spotify) -> None:
    """Update master genre playlists with all liked songs by genre.
    
    When tracks are manually removed from genre master playlists, removes
    the corresponding genre tags from the track's stored genres.
    """
    # Late imports from sync.py
    from .sync import (
        log, verbose_log, DATA_DIR, ENABLE_MONTHLY, ENABLE_MOST_PLAYED, ENABLE_DISCOVERY,
        LIKED_SONGS_PLAYLIST_ID, GENRE_NAME_TEMPLATE, MAX_GENRE_PLAYLISTS, MIN_TRACKS_FOR_GENRE,
        get_existing_playlists, get_user_info, get_playlist_tracks, api_call,
        _chunked, _update_playlist_description_with_genres, _playlist_tracks_cache,
        _parse_genres, _get_all_track_genres
    )
    from collections import Counter
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
    # Use ONLY artist genres (most reliable) - avoid playlist pattern inference which is too noisy
    uri_to_genres = {}  # Map URI to list of broad genres
    tracks_df = pd.read_parquet(DATA_DIR / "tracks.parquet")
    
    # Build artist genres map for fast lookup
    artist_genres_map = artists.set_index("artist_id")["genres"].to_dict()
    
    verbose_log(f"  Classifying genres for {len(liked_ids)} liked tracks using artist genres only...")
    
    # Use ONLY artist genres (most reliable source)
    # Playlist pattern inference is disabled because it's too noisy and causes false positives
    for track_id in liked_ids:
        uri = f"spotify:track:{track_id}"
        
        # Get all genres from all artists on this track
        all_track_genres = _get_all_track_genres(track_id, track_artists, artist_genres_map)
        
        # Convert to broad genres - this is the ONLY source we trust
        broad_genres = get_all_broad_genres(all_track_genres)
        
        if broad_genres:
            uri_to_genres[uri] = broad_genres
    
    verbose_log(f"  Classified genres for {len(uri_to_genres)}/{len(liked_ids)} tracks ({len(uri_to_genres)/len(liked_ids)*100:.1f}%)")
    
    # Count tracks per genre (tracks can contribute to multiple genres)
    genre_counts = Counter()
    for genres_list in uri_to_genres.values():
        for genre in genres_list:
            genre_counts[genre] += 1
    
    # Log genre distribution for debugging
    if verbose_log:
        verbose_log(f"  Genre distribution (top 15): {dict(genre_counts.most_common(15))}")
        verbose_log(f"  Total liked tracks: {len(liked_uris)}, tracks with genres: {len(uri_to_genres)}")
        verbose_log(f"  Genre coverage: {len(uri_to_genres)/len(liked_uris)*100:.1f}% of tracks have genres")
        
        # Show breakdown by genre count
        genre_size_distribution = Counter()
        for genres_list in uri_to_genres.values():
            genre_size_distribution[len(genres_list)] += 1
        verbose_log(f"  Tracks by genre count: {dict(sorted(genre_size_distribution.items()))}")
    
    # Adaptive threshold: use percentage-based threshold if absolute threshold is too restrictive
    total_tracks_with_genres = len(uri_to_genres)
    if total_tracks_with_genres > 0:
        # Use 1% of tracks as minimum, but not less than 10 tracks
        adaptive_threshold = max(MIN_TRACKS_FOR_GENRE, int(total_tracks_with_genres * 0.01))
        adaptive_threshold = min(adaptive_threshold, 50)  # Cap at 50 to avoid too many small playlists
    else:
        adaptive_threshold = MIN_TRACKS_FOR_GENRE
    
    # Select genres: use adaptive threshold, but also include top genres even if below threshold
    # This ensures we capture diverse genres even if they're smaller
    top_genres_all = genre_counts.most_common(MAX_GENRE_PLAYLISTS)
    
    # First, get all genres that meet the threshold
    selected = [g for g, n in top_genres_all if n >= adaptive_threshold]
    
    # If we have very few genres, also include top genres even if below threshold (but at least 5 tracks)
    if len(selected) < 3 and len(top_genres_all) > 0:
        min_fallback = max(5, int(adaptive_threshold * 0.3))  # At least 30% of threshold, minimum 5
        additional = [g for g, n in top_genres_all[:5] if n >= min_fallback and g not in selected]
        selected.extend(additional)
        verbose_log(f"  Added {len(additional)} genre(s) below threshold to ensure diversity (min {min_fallback} tracks)")
    
    if total_tracks_with_genres > 0:
        threshold_pct = (adaptive_threshold / total_tracks_with_genres * 100)
        log(f"  Found {len(selected)} genre(s) (threshold: {adaptive_threshold} tracks, {threshold_pct:.1f}% of library)")
    else:
        log(f"  Found {len(selected)} genre(s) (threshold: {adaptive_threshold} tracks)")
    if selected:
        for genre in selected:
            count = genre_counts[genre]
            pct = (count / total_tracks_with_genres * 100) if total_tracks_with_genres > 0 else 0
            log(f"    • {genre}: {count} tracks ({pct:.1f}%)")
    else:
        verbose_log(f"  No genres meet the minimum threshold of {adaptive_threshold} tracks")
        verbose_log(f"  Top genres: {dict(genre_counts.most_common(10))}")
        verbose_log(f"  Consider lowering MIN_TRACKS_FOR_GENRE or improving genre classification")
    
    # Get existing playlists (cached)
    existing = get_existing_playlists(sp)
    user = get_user_info(sp)
    user_id = user["id"]
    
    # Track if we need to save tracks_df at the end
    tracks_modified = False
    
    # Load previous playlist tracks from cache to detect removals
    # This allows us to compare what was in the playlist before vs now
    previous_playlist_tracks = {}  # {playlist_id: set of track URIs}
    if "playlist_id" in library.columns and "track_uri" in library.columns:
        for genre in selected:
            name = format_playlist_name(GENRE_NAME_TEMPLATE, genre=genre, playlist_type="genre_master")
            if name in existing:
                pid = existing[name]
                # Get tracks that were in this playlist from previous sync
                playlist_tracks_data = library[library["playlist_id"] == pid]
                if not playlist_tracks_data.empty and "track_uri" in playlist_tracks_data.columns:
                    previous_tracks = set(playlist_tracks_data["track_uri"].dropna().tolist())
                    previous_playlist_tracks[pid] = previous_tracks
    
    for genre in selected:
        # Get all tracks that match this genre (tracks can match multiple genres)
        uris_should_be_in_playlist = set([u for u in liked_uris if genre in uri_to_genres.get(u, [])])
        if not uris_should_be_in_playlist:
            continue
        
        name = format_playlist_name(GENRE_NAME_TEMPLATE, genre=genre, playlist_type="genre_master")
        
        if name in existing:
            pid = existing[name]
            # Get existing tracks (includes both auto-added and manually added tracks)
            already_in_playlist = get_playlist_tracks(sp, pid)
            
            # Remove tracks that don't match the genre (only for liked songs, preserve manually added non-liked tracks)
            tracks_to_remove = []
            for track_uri in already_in_playlist:
                # Only remove if it's a liked song and doesn't match the genre
                if track_uri in liked_uris and track_uri not in uris_should_be_in_playlist:
                    tracks_to_remove.append(track_uri)
            
            if tracks_to_remove:
                log(f"  {name}: Removing {len(tracks_to_remove)} track(s) that don't match genre...")
                # Use safe removal with backup and validation
                from .data_protection import safe_remove_tracks_from_playlist
                success, backup_file = safe_remove_tracks_from_playlist(
                    sp, pid, name, tracks_to_remove,
                    create_backup=True,
                    validate_after=True
                )
                if not success:
                    log(f"  ⚠️  Warning: Track removal validation failed for {name}")
                    if backup_file:
                        log(f"  💾 Backup available: {backup_file.name}")
                else:
                    # Invalidate cache
                    if pid in _playlist_tracks_cache:
                        del _playlist_tracks_cache[pid]
                    # Re-fetch to get updated list
                    already_in_playlist = get_playlist_tracks(sp, pid, force_refresh=True)
            
            # Only add tracks that aren't already present (preserves manual additions)
            to_add = [u for u in uris_should_be_in_playlist if u not in already_in_playlist]

            # Check for removed tracks: tracks that were in playlist before but aren't now
            # These were manually removed, so remove the genre tag
            if pid in previous_playlist_tracks:
                previous_tracks = previous_playlist_tracks[pid]
                removed_tracks = previous_tracks - already_in_playlist
                
                if removed_tracks:
                    # Only remove genre tags for tracks that should have that genre based on current state
                    # This avoids removing genres from manually added tracks that don't match the genre
                    tracks_to_remove_genre = []
                    for removed_uri in removed_tracks:
                        # Only remove genre if the track currently has this genre in its stored tags
                        # or if it's a liked song (meaning it should match the genre)
                        if removed_uri in liked_uris:
                            tracks_to_remove_genre.append(removed_uri)
                    
                    if tracks_to_remove_genre:
                        log(f"  {name}: Detected {len(tracks_to_remove_genre)} manually removed track(s), removing genre tags...")
                        for removed_uri in tracks_to_remove_genre:
                            if _remove_genre_from_track(tracks_df, removed_uri, genre):
                                tracks_modified = True
                                # Also update uri_to_genres to reflect the change
                                if removed_uri in uri_to_genres:
                                    uri_to_genres[removed_uri] = [g for g in uri_to_genres[removed_uri] if g != genre]

            if to_add:
                for chunk in _chunked(to_add, 50):
                    api_call(sp.playlist_add_items, pid, chunk)
                # Invalidate cache for this playlist since we added tracks
                if pid in _playlist_tracks_cache:
                    del _playlist_tracks_cache[pid]
                log(f"  {name}: +{len(to_add)} tracks (manually added tracks preserved)")
                # Update description with genre tags (use all tracks in playlist)
                _update_playlist_description_with_genres(sp, user_id, pid, None)
        else:
            verbose_log(f"Creating new playlist '{name}' for genre '{genre}'...")
            pl = api_call(
                sp.user_playlist_create,
                user_id,
                name,
                public=False,
                description=format_playlist_description("All liked songs", genre=genre, playlist_type="genre_master"),
            )
            pid = pl["id"]
            verbose_log(f"  Created playlist '{name}' with id {pid}, adding {len(uris_should_be_in_playlist)} tracks...")

            chunk_count = 0
            for chunk in _chunked(list(uris_should_be_in_playlist), 50):
                chunk_count += 1
                verbose_log(f"  Adding chunk {chunk_count} ({len(chunk)} tracks) to new playlist...")
                api_call(sp.playlist_add_items, pid, chunk)
            # Update description with genre tags
            _update_playlist_description_with_genres(sp, user_id, pid, list(uris_should_be_in_playlist))
            # Invalidate playlist cache since we created a new playlist
            _invalidate_playlist_cache()
            log(f"  {name}: created with {len(uris_should_be_in_playlist)} tracks")
    
    # Save tracks_df if it was modified
    if tracks_modified:
        tracks_path = DATA_DIR / "tracks.parquet"
        try:
            tracks_df.to_parquet(tracks_path, index=False, engine='pyarrow')
        except Exception:
            tracks_df.to_parquet(tracks_path, index=False)
        log(f"  ✅ Updated track genres after removals")


# ============================================================================
# DUPLICATE PLAYLIST DETECTION & DELETION
# ============================================================================


