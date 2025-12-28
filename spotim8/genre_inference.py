"""
Comprehensive genre inference system.

Infers track genres using multiple methods:
1. Artist genres (primary source)
2. Playlist patterns (learns from genre playlists)
3. Spotify search/recommendations (for missing artists)
4. Track/album name heuristics
5. Collaborative filtering from similar tracks

All genres are normalized to the master genre list.
"""

from typing import Optional, List, Dict, Set, Tuple
from collections import Counter
import pandas as pd

from .genres import (
    get_split_genre, get_broad_genre,
    get_all_split_genres, get_all_broad_genres,
    GENRE_RULES, GENRE_SPLIT_RULES,
    ALL_BROAD_GENRES
)


# Global log function (set by sync script)
_log_fn = None

def log(msg: str) -> None:
    """Log message if log function is available."""
    if _log_fn:
        _log_fn(msg)
    else:
        print(msg)


def _parse_genres(genre_data) -> list:
    """Parse genre data from various formats."""
    import ast
    if genre_data is None:
        return []
    if isinstance(genre_data, list):
        return genre_data
    if isinstance(genre_data, str):
        try:
            return ast.literal_eval(genre_data)
        except (ValueError, SyntaxError):
            return [genre_data] if genre_data else []
    return []


def infer_genres_from_playlist_patterns(
    track_id: str,
    playlist_tracks: pd.DataFrame,
    playlists: pd.DataFrame,
    mode: str = "split"  # "split" or "broad"
) -> List[str]:
    """Infer track genres from playlist membership patterns.
    
    If a track appears in playlists with genre-related names or descriptions
    (e.g., "HipHop", "Dance"), use that to infer genres. 
    
    Also analyzes ALL followed playlists (not just owned) by checking their
    names and descriptions for genre keywords to provide additional signal.
    
    Returns ALL matching genres.
    
    Args:
        track_id: Track ID to infer genre for
        playlist_tracks: DataFrame with playlist_id and track_id columns
        playlists: DataFrame with playlist_id, name, and optionally description columns
                   (includes both owned and followed playlists)
        mode: "split" for split genres, "broad" for broad genres
    
    Returns:
        List of inferred genre names (can be multiple)
    """
    matched = []
    seen = set()
    
    # Get all playlists containing this track (owned playlists)
    track_playlist_ids = set()
    if playlist_tracks is not None and not playlist_tracks.empty:
        track_playlists = playlist_tracks[playlist_tracks["track_id"] == track_id]
        if not track_playlists.empty:
            track_playlist_ids = set(track_playlists["playlist_id"].unique())
    
    # Build all Spotify genre keywords for matching
    all_genre_keywords = {}
    if mode == "split":
        for genre, keywords in GENRE_SPLIT_RULES.items():
            for kw in keywords:
                all_genre_keywords[kw.lower()] = genre
    else:
        for keywords, category in GENRE_RULES:
            for kw in keywords:
                if kw.lower() not in all_genre_keywords:  # Don't overwrite split genres
                    all_genre_keywords[kw.lower()] = category
    
    # Analyze playlists where track appears (owned playlists) - strong signal
    if track_playlist_ids:
        relevant_playlists = playlists[playlists["playlist_id"].isin(track_playlist_ids)]
        for _, pl_row in relevant_playlists.iterrows():
            # Check both name and description
            pl_text = " ".join([
                str(pl_row.get("name", "")),
                str(pl_row.get("description", ""))
            ]).lower()
            
            # Match genre keywords
            for keyword, genre in all_genre_keywords.items():
                if keyword in pl_text and genre not in seen:
                    matched.append(genre)
                    seen.add(genre)
    
    # Also check ALL followed playlists (even if track doesn't appear in them)
    # This helps infer genres from playlists the user follows with genre-related names/descriptions
    # Filter to followed playlists (not owned, if is_owned column exists)
    if "is_owned" in playlists.columns:
        followed_playlists = playlists[~playlists["is_owned"].fillna(False)]
    else:
        # If no is_owned column, skip this analysis to avoid noise
        followed_playlists = pd.DataFrame()
    
    for _, pl_row in followed_playlists.iterrows():
        # Skip if we already analyzed this playlist above
        pl_id = pl_row.get("playlist_id")
        if pl_id in track_playlist_ids:
            continue
        
        # Check both name and description for genre keywords
        pl_text = " ".join([
            str(pl_row.get("name", "")),
            str(pl_row.get("description", ""))
        ]).lower()
        
        # Match genre keywords (weaker signal since track doesn't appear in playlist)
        # Require keyword to appear multiple times or be a strong match
        for keyword, genre in all_genre_keywords.items():
            count = pl_text.count(keyword)
            # Stronger signal needed for followed playlists (keyword appears 2+ times)
            if count >= 2 and genre not in seen:
                matched.append(genre)
                seen.add(genre)
    
    return matched


def infer_genres_from_track_name(track_name: str, album_name: Optional[str] = None) -> List[str]:
    """Heuristically infer genres from track/album name patterns.
    
    This is a last resort method and should be used carefully.
    Returns ALL matching genres (a track name could match multiple).
    
    Args:
        track_name: Track name
        album_name: Optional album name
    
    Returns:
        List of inferred genres (can be multiple)
    """
    if not track_name:
        return []
    
    text = track_name.lower()
    if album_name:
        text += " " + album_name.lower()
    
    matched = []
    
    # Simple keyword matching (expandable)
    if any(kw in text for kw in ["rap", "hip hop", "trap", "drill", "freestyle"]):
        matched.append("HipHop")
    if any(kw in text for kw in ["house", "techno", "trance", "edm", "dubstep", "dance"]):
        matched.append("Dance")
    if any(kw in text for kw in ["jazz", "bebop", "swing"]):
        matched.append("Jazz")
    if any(kw in text for kw in ["rock", "punk", "metal", "grunge"]):
        matched.append("Rock")
    
    return matched


def get_all_artist_genres_for_track(
    track_id: str,
    track_artists: pd.DataFrame,
    artists: pd.DataFrame
) -> List[str]:
    """Get all genres from all artists on a track.
    
    Args:
        track_id: Track ID
        track_artists: DataFrame with track_id and artist_id columns
        artists: DataFrame with artist_id and genres columns
    
    Returns:
        Combined list of unique genres from all artists
    """
    # Get all artists for this track
    track_artist_rows = track_artists[track_artists["track_id"] == track_id]
    if track_artist_rows.empty:
        return []
    
    artist_ids = track_artist_rows["artist_id"].tolist()
    artist_genres_map = artists[artists["artist_id"].isin(artist_ids)].set_index("artist_id")["genres"].to_dict()
    
    # Collect all genres
    all_genres = []
    for artist_id in artist_ids:
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


def infer_genres_comprehensive(
    track_id: str,
    track_name: Optional[str] = None,
    album_name: Optional[str] = None,
    track_artists: Optional[pd.DataFrame] = None,
    artists: Optional[pd.DataFrame] = None,
    playlist_tracks: Optional[pd.DataFrame] = None,
    playlists: Optional[pd.DataFrame] = None,
    mode: str = "split"  # "split" or "broad"
) -> List[str]:
    """Comprehensive genre inference using multiple methods.
    
    Tries methods in order of reliability:
    1. Artist genres (most reliable)
    2. Playlist patterns (learns from genre playlists)
    3. Track/album name heuristics (least reliable)
    
    Returns ALL matching genres (tracks can have multiple).
    
    Args:
        track_id: Track ID
        track_name: Track name (optional, for heuristics)
        album_name: Album name (optional, for heuristics)
        track_artists: DataFrame with track_id and artist_id columns
        artists: DataFrame with artist_id and genres columns
        playlist_tracks: DataFrame with playlist_id and track_id columns
        playlists: DataFrame with playlist_id and name columns
        mode: "split" for HipHop/Dance/Other, "broad" for broad categories
    
    Returns:
        List of inferred genres (can be multiple, e.g., ["HipHop", "Dance"])
    """
    all_genres = set()
    
    # Method 1: Artist genres (most reliable)
    if track_artists is not None and artists is not None:
        artist_genres = get_all_artist_genres_for_track(track_id, track_artists, artists)
        if artist_genres:
            if mode == "split":
                inferred = get_all_split_genres(artist_genres)
            else:
                inferred = get_all_broad_genres(artist_genres)
            all_genres.update(inferred)
    
    # Method 2: Playlist patterns (learns from genre playlists)
    if playlist_tracks is not None and playlists is not None:
        inferred = infer_genres_from_playlist_patterns(
            track_id, playlist_tracks, playlists, mode
        )
        all_genres.update(inferred)
    
    # Method 3: Track/album name heuristics (last resort, only if no other matches)
    if not all_genres and track_name:
        inferred = infer_genres_from_track_name(track_name, album_name)
        all_genres.update(inferred)
    
    # For split mode, if we have HipHop or Dance, don't include Other
    # Other is only added if we have no HipHop/Dance matches
    if mode == "split":
        if "HipHop" in all_genres or "Dance" in all_genres:
            all_genres.discard("Other")
    
    return sorted(list(all_genres))  # Return sorted for consistency


def infer_track_genres_batch(
    tracks: pd.DataFrame,
    track_artists: pd.DataFrame,
    artists: pd.DataFrame,
    playlist_tracks: pd.DataFrame,
    playlists: pd.DataFrame,
    mode: str = "split"
) -> pd.Series:
    """Infer genres for a batch of tracks.
    
    Args:
        tracks: DataFrame with track_id, name, album_name columns
        track_artists: DataFrame with track_id and artist_id columns
        artists: DataFrame with artist_id and genres columns
        playlist_tracks: DataFrame with playlist_id and track_id columns
        playlists: DataFrame with playlist_id and name columns
        mode: "split" or "broad"
    
    Returns:
        Series mapping track_id to list of inferred genres
    """
    track_genres = {}
    
    for _, track_row in tracks.iterrows():
        track_id = track_row["track_id"]
        track_name = track_row.get("name")
        album_name = track_row.get("album_name")
        
        genres = infer_genres_comprehensive(
            track_id=track_id,
            track_name=track_name,
            album_name=album_name,
            track_artists=track_artists,
            artists=artists,
            playlist_tracks=playlist_tracks,
            playlists=playlists,
            mode=mode
        )
        
        track_genres[track_id] = genres
    
    return pd.Series(track_genres, name="inferred_genre")


def enhance_artist_genres_from_playlists(
    artists: pd.DataFrame,
    track_artists: pd.DataFrame,
    playlist_tracks: pd.DataFrame,
    playlists: pd.DataFrame
) -> pd.DataFrame:
    """Enhance artist genres by learning from playlist patterns.
    
    Learns from ALL playlists (not just genre playlists) to infer missing artist genres.
    If an artist's tracks frequently appear in playlists with genre-related names,
    add those genres to the artist.
    
    Args:
        artists: DataFrame with artist_id and genres columns
        track_artists: DataFrame with track_id and artist_id columns
        playlist_tracks: DataFrame with playlist_id and track_id columns
        playlists: DataFrame with playlist_id and name columns
    
    Returns:
        Enhanced artists DataFrame with additional inferred genres
    """
    artists = artists.copy()
    
    # Build artist -> tracks mapping
    artist_tracks = track_artists.groupby("artist_id")["track_id"].apply(set).to_dict()
    
    # Build all Spotify genre keywords for matching
    all_genre_keywords = {}
    for genre, keywords in GENRE_SPLIT_RULES.items():
        for kw in keywords:
            all_genre_keywords[kw.lower()] = genre
    
    # Also check broad genres
    for keywords, category in GENRE_RULES:
        for kw in keywords:
            if kw.lower() not in all_genre_keywords:  # Don't overwrite split genres
                all_genre_keywords[kw.lower()] = category
    
    # Analyze playlist patterns for each artist
    artists_needing_genres = []
    for artist_id, track_set in artist_tracks.items():
        # Get all playlists containing tracks by this artist
        artist_playlist_tracks = playlist_tracks[
            playlist_tracks["track_id"].isin(track_set)
        ]
        
        if artist_playlist_tracks.empty:
            continue
        
        playlist_ids = set(artist_playlist_tracks["playlist_id"].unique())
        relevant_playlists = playlists[playlists["playlist_id"].isin(playlist_ids)]
        
        # Build text from both names and descriptions
        playlist_text_parts = []
        for _, pl_row in relevant_playlists.iterrows():
            name = str(pl_row.get("name", ""))
            desc = str(pl_row.get("description", ""))
            if name:
                playlist_text_parts.append(name)
            if desc:
                playlist_text_parts.append(desc)
        
        playlist_text = " ".join(playlist_text_parts).lower()
        
        # Also analyze ALL followed playlists for additional signal
        if "is_owned" in playlists.columns:
            followed_playlists = playlists[~playlists["is_owned"].fillna(False)]
        else:
            followed_playlists = playlists
        
        for _, pl_row in followed_playlists.iterrows():
            # Skip if already analyzed
            if pl_row.get("playlist_id") in playlist_ids:
                continue
            
            name = str(pl_row.get("name", ""))
            desc = str(pl_row.get("description", ""))
            pl_text = f"{name} {desc}".lower()
            
            # Add to playlist_text for analysis (with lower weight by duplicating less)
            if pl_text.strip():
                playlist_text += " " + pl_text  # Append for keyword counting
        
        # Count genre keywords in playlist names and descriptions
        genre_counts = Counter()
        
        # Match all genre keywords in playlist names
        for keyword, genre in all_genre_keywords.items():
            if keyword in playlist_text:
                genre_counts[genre] += playlist_text.count(keyword)
        
        artist_mask = artists["artist_id"] == artist_id
        artist_rows = artists[artist_mask]
        if len(artist_rows) == 0:
            continue
        
        # Get the first matching row's index
        artist_idx_val = artist_rows.index[0]
        existing_genres = _parse_genres(artists.at[artist_idx_val, "genres"])
        existing_lower = {g.lower() for g in existing_genres}
        
        # If artist has no genres, try to infer from playlists
        if not existing_genres and genre_counts:
            # Add genres that appear frequently in playlists
            # Threshold: genre must appear in at least 2 different playlists
            frequent_genres = [
                genre for genre, count in genre_counts.items()
                if count >= 2
            ]
            if frequent_genres:
                # Use the most common genre or first few
                new_genres = [g for g, _ in genre_counts.most_common(3) if g in frequent_genres]
                artists.at[artist_idx_val, "genres"] = new_genres
                artists_needing_genres.append((artist_id, new_genres))
        elif existing_genres and genre_counts:
            # Add genres that appear frequently but aren't already present
            new_genres = []
            for genre, count in genre_counts.most_common(5):
                if count >= 2 and genre.lower() not in existing_lower:
                    new_genres.append(genre)
            if new_genres:
                combined = existing_genres + new_genres[:2]  # Limit additions
                artists.at[artist_idx_val, "genres"] = combined
    
    if artists_needing_genres:
        log(f"  ✨ Enhanced {len(artists_needing_genres)} artists with genres from playlist patterns")
    
    return artists

