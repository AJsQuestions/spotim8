#!/usr/bin/env python3
"""
Sync & Update Script for GitHub Actions

This script:
1. Syncs liked songs from Spotify API
2. Updates all playlists (monthly, genre-split, master genre)

Uses refresh token for headless authentication in CI/CD.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import Counter

import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================================
# CONFIGURATION
# ============================================================================

OWNER_NAME = "AJ"
PREFIX = "Finds"

MONTHLY_NAME_TEMPLATE = "{owner}{prefix}{mon}{year}"
GENRE_MONTHLY_TEMPLATE = "{genre}{prefix}{mon}{year}"
GENRE_NAME_TEMPLATE = "{owner}am{genre}"

SPLIT_GENRES = ["HipHop", "Dance", "Other"]
MIN_TRACKS_FOR_GENRE = 20
MAX_GENRE_PLAYLISTS = 19

DATA_DIR = PROJECT_ROOT / "data"
LIKED_SONGS_PLAYLIST_ID = "liked_songs"

MONTH_NAMES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"
}

GENRE_SPLIT_RULES = {
    "HipHop": ["hip hop", "rap", "trap", "drill", "grime", "crunk", "phonk", 
               "boom bap", "dirty south", "gangsta", "uk drill", "melodic rap"],
    "Dance": ["electronic", "edm", "house", "techno", "trance", "dubstep", 
              "drum and bass", "ambient", "garage", "deep house", "minimal",
              "synthwave", "future bass", "electro", "dance", "electronica"]
}

GENRE_RULES = [
    (["hip hop", "rap", "trap", "drill", "grime", "phonk"], "Hip-Hop"),
    (["r&b", "rnb", "soul", "neo soul", "funk"], "R&B/Soul"),
    (["electronic", "edm", "house", "techno", "trance", "dubstep"], "Electronic"),
    (["rock", "alternative", "grunge", "punk", "emo"], "Rock"),
    (["metal", "heavy metal", "death metal"], "Metal"),
    (["indie", "indie rock", "indie pop", "lo-fi"], "Indie"),
    (["pop", "dance pop", "synth pop"], "Pop"),
    (["latin", "reggaeton", "salsa"], "Latin"),
    (["afrobeat", "k-pop", "reggae", "world"], "World"),
    (["jazz", "smooth jazz"], "Jazz"),
    (["classical", "orchestra"], "Classical"),
    (["country", "folk", "americana"], "Country/Folk"),
]


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def get_spotify_client():
    """Get authenticated Spotify client using refresh token."""
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    refresh_token = os.environ.get("SPOTIPY_REFRESH_TOKEN")
    
    if not all([client_id, client_secret]):
        raise ValueError("Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET")
    
    if refresh_token:
        # Use refresh token for headless auth
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-library-read playlist-modify-private playlist-modify-public playlist-read-private"
        )
        
        # Create token info from refresh token
        token_info = auth.refresh_access_token(refresh_token)
        return spotipy.Spotify(auth=token_info["access_token"])
    else:
        # Interactive auth (for local testing)
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-library-read playlist-modify-private playlist-modify-public playlist-read-private",
            cache_path=str(DATA_DIR / ".cache")
        )
        return spotipy.Spotify(auth_manager=auth)


def get_split_genre(genre_list):
    if not genre_list:
        return "Other"
    combined = " ".join(genre_list).lower()
    for genre_name, keywords in GENRE_SPLIT_RULES.items():
        if any(kw in combined for kw in keywords):
            return genre_name
    return "Other"


def get_broad_genre(genre_list):
    if not genre_list:
        return None
    combined = " ".join(genre_list).lower()
    for keywords, category in GENRE_RULES:
        if any(kw in combined for kw in keywords):
            return category
    return None


def _chunked(seq, n=100):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]


def get_existing_playlists(sp):
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


def get_playlist_tracks(sp, pid):
    uris = set()
    offset = 0
    while True:
        page = sp.playlist_items(pid, fields="items(track(uri)),next", limit=100, offset=offset)
        for it in page.get("items", []):
            if it.get("track", {}).get("uri"):
                uris.add(it["track"]["uri"])
        if not page.get("next"):
            break
        offset += 100
    return uris


def format_name(template, month_str, genre=None):
    parts = month_str.split("-")
    full_year = parts[0] if len(parts) >= 1 else ""
    month_num = parts[1] if len(parts) >= 2 else ""
    mon = MONTH_NAMES.get(month_num, month_num)
    year = full_year[2:] if len(full_year) == 4 else full_year
    return template.format(owner=OWNER_NAME, prefix=PREFIX, genre=genre or "", mon=mon, year=year)


def sync_liked_songs(sp):
    """Sync liked songs from Spotify API."""
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


def sync_artists(sp, track_ids):
    """Sync artist data for tracks."""
    log("Syncing artist data...")
    
    # Get all tracks to find artist IDs
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


def update_playlists(sp, liked_tracks, artists_df, track_artists_df):
    """Update all playlists."""
    
    # Build month -> tracks mapping
    df = pd.DataFrame(liked_tracks)
    df["added_at"] = pd.to_datetime(df["added_at"], utc=True)
    df["month"] = df["added_at"].dt.to_period("M").astype(str)
    
    month_to_tracks = {}
    for m, g in df.groupby("month"):
        uris = g["track_uri"].dropna().tolist()
        seen = set()
        unique = [u for u in uris if not (u in seen or seen.add(u))]
        month_to_tracks[m] = unique
    
    # Only process current month
    current = datetime.now().strftime("%Y-%m")
    filtered = {m: v for m, v in month_to_tracks.items() if m == current}
    
    if not filtered:
        log("No tracks for current month")
        return
    
    log(f"Processing {len(filtered)} month(s)...")
    
    existing = get_existing_playlists(sp)
    user_id = sp.current_user()["id"]
    
    # Build genre mappings
    import ast
    import numpy as np
    
    artist_genres_map = artists_df.set_index("artist_id")["genres"].to_dict()
    
    all_uris = set(u for uris in filtered.values() for u in uris)
    track_ids = {u.split(":")[-1] for u in all_uris if u.startswith("spotify:track:")}
    
    track_to_split_genre = {}
    track_to_broad_genre = {}
    
    for _, row in track_artists_df[track_artists_df["track_id"].isin(track_ids)].iterrows():
        tid = row["track_id"]
        uri = f"spotify:track:{tid}"
        
        if uri not in track_to_split_genre:
            artist_genres = artist_genres_map.get(row["artist_id"], [])
            if isinstance(artist_genres, str):
                try:
                    artist_genres = ast.literal_eval(artist_genres)
                except:
                    artist_genres = [artist_genres]
            if isinstance(artist_genres, np.ndarray):
                artist_genres = list(artist_genres)
            
            track_to_split_genre[uri] = get_split_genre(artist_genres or [])
            broad = get_broad_genre(artist_genres or [])
            if broad:
                track_to_broad_genre[uri] = broad
    
    # 1. Monthly playlists
    log("\n--- Monthly Playlists ---")
    for month, uris in sorted(filtered.items()):
        if not uris:
            continue
        name = format_name(MONTHLY_NAME_TEMPLATE, month)
        
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
            pl = sp.user_playlist_create(user_id, name, public=False)
            for chunk in _chunked(uris, 100):
                sp.playlist_add_items(pl["id"], chunk)
            log(f"  {name}: created with {len(uris)} tracks")
    
    # 2. Genre-split playlists
    log("\n--- Genre-Split Playlists ---")
    for month, uris in sorted(filtered.items()):
        for genre in SPLIT_GENRES:
            genre_uris = [u for u in uris if track_to_split_genre.get(u) == genre]
            if not genre_uris:
                continue
            
            name = format_name(GENRE_MONTHLY_TEMPLATE, month, genre)
            
            if name in existing:
                pid = existing[name]
                already = get_playlist_tracks(sp, pid)
                to_add = [u for u in genre_uris if u not in already]
                if to_add:
                    for chunk in _chunked(to_add, 100):
                        sp.playlist_add_items(pid, chunk)
                    log(f"  {name}: +{len(to_add)} tracks")
            else:
                pl = sp.user_playlist_create(user_id, name, public=False)
                for chunk in _chunked(genre_uris, 100):
                    sp.playlist_add_items(pl["id"], chunk)
                log(f"  {name}: created with {len(genre_uris)} tracks")
    
    # 3. Master genre playlists
    log("\n--- Master Genre Playlists ---")
    all_liked_uris = [t["track_uri"] for t in liked_tracks if t.get("track_uri")]
    
    genre_counts = Counter(track_to_broad_genre.values())
    selected = [g for g, n in genre_counts.most_common(MAX_GENRE_PLAYLISTS) if n >= MIN_TRACKS_FOR_GENRE]
    
    for genre in selected:
        uris = [u for u in all_liked_uris if track_to_broad_genre.get(u) == genre]
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
            pl = sp.user_playlist_create(user_id, name, public=False)
            for chunk in _chunked(uris, 100):
                sp.playlist_add_items(pl["id"], chunk)
            log(f"  {name}: created with {len(uris)} tracks")


def main():
    log("=" * 60)
    log("Spotify Playlist Sync & Update")
    log("=" * 60)
    
    try:
        sp = get_spotify_client()
        user = sp.current_user()
        log(f"Authenticated as: {user['display_name']} ({user['id']})")
    except Exception as e:
        log(f"ERROR: Authentication failed: {e}")
        sys.exit(1)
    
    try:
        # 1. Sync liked songs
        liked_tracks = sync_liked_songs(sp)
        
        if not liked_tracks:
            log("No liked songs found!")
            return
        
        # 2. Sync artists
        track_ids = [t["track_id"] for t in liked_tracks]
        artists_df, track_artists_df = sync_artists(sp, track_ids)
        
        # 3. Update playlists
        update_playlists(sp, liked_tracks, artists_df, track_artists_df)
        
        log("\n" + "=" * 60)
        log("Complete!")
        log("=" * 60)
        
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

