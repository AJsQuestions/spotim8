"""
Spotim8 client - pandas-first interface to Spotify Web API.
"""

from __future__ import annotations

import os
import warnings
from typing import Optional, Callable

import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from tqdm import tqdm

from .catalog import CacheConfig, DataCatalog
from .ratelimit import rate_limited_call, DEFAULT_REQUEST_DELAY
from .utils import chunks
from .market import MarketFrames

DEFAULT_SCOPE = (
    "playlist-read-private playlist-read-collaborative "
    "user-library-read user-read-email user-read-private"
)

# Special playlist ID for Liked Songs (not a real Spotify playlist)
LIKED_SONGS_PLAYLIST_ID = "__liked_songs__"
LIKED_SONGS_PLAYLIST_NAME = "❤️ Liked Songs"


class Spotim8:
    """Pandas-first interface to Spotify Web API (library + market)."""

    def __init__(self, sp: spotipy.Spotify, cache: CacheConfig = CacheConfig(), 
                 progress: bool = False, request_delay: float = DEFAULT_REQUEST_DELAY):
        self.sp = sp
        self.catalog = DataCatalog(cache)
        self.progress = progress
        self._request_delay = request_delay
        self.market = MarketFrames(sp, progress=progress, request_delay=request_delay)

    # -------------------------
    # Constructors
    # -------------------------
    @classmethod
    def from_oauth(
        cls,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scope: str = DEFAULT_SCOPE,
        cache: CacheConfig = CacheConfig(),
        progress: bool = False,
    ) -> "Spotim8":
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            open_browser=True,
        )
        sp = spotipy.Spotify(auth_manager=auth, requests_timeout=30, retries=6, status_retries=6)
        return cls(sp=sp, cache=cache, progress=progress)

    @classmethod
    def from_env(
        cls,
        scope: str = DEFAULT_SCOPE,
        cache: CacheConfig = CacheConfig(),
        progress: bool = False,
    ) -> "Spotim8":
        cid = os.environ.get("SPOTIPY_CLIENT_ID")
        secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
        redir = os.environ.get("SPOTIPY_REDIRECT_URI")
        if not (cid and secret and redir):
            raise RuntimeError("Set SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI")
        return cls.from_oauth(cid, secret, redir, scope=scope, cache=cache, progress=progress)

    # -------------------------
    # Helpers
    # -------------------------
    def _paginate(self, first_page: dict, item_key: str) -> list[dict]:
        """Paginate through API results with rate limiting."""
        items = list(first_page.get(item_key, []))
        page = first_page
        while page.get("next"):
            page = rate_limited_call(self.sp.next, page, delay=self._request_delay)
            items.extend(page.get(item_key, []))
        return items
    
    def _rate_limited(self, func: Callable, *args, **kwargs):
        """Wrapper for rate-limited API calls."""
        return rate_limited_call(func, *args, delay=self._request_delay, **kwargs)

    def _me_id(self) -> str:
        meta = self.catalog.load_meta()
        if "me_id" in meta:
            return meta["me_id"]
        me = self._rate_limited(self.sp.current_user).get("id")
        meta["me_id"] = me
        self.catalog.save_meta(meta)
        return me
    
    def status(self) -> dict:
        """Show current state of cached data."""
        meta = self.catalog.load_meta()
        
        status = {
            "cache_dir": str(self.catalog.cache.dir),
            "last_sync": meta.get("last_sync_utc", "Never"),
            "user_id": meta.get("me_id", "Unknown"),
        }
        
        # Check each table (audio_features removed - deprecated by Spotify Nov 2024)
        tables = ["playlists", "playlist_tracks", "tracks", "track_artists", "artists", "library_wide"]
        for table in tables:
            df = self.catalog.load(table)
            if df is not None:
                status[f"{table}_count"] = len(df)
            else:
                status[f"{table}_count"] = 0
        
        return status
    
    def print_status(self) -> None:
        """Print current state of cached data."""
        s = self.status()
        print("\n" + "="*50)
        print("        SPOTIM8 DATA STATUS")
        print("="*50)
        print(f"📁 Cache directory: {s['cache_dir']}")
        print(f"👤 User: {s['user_id']}")
        print(f"🕐 Last sync: {s['last_sync']}")
        print("\n📊 Cached data:")
        print(f"   • Playlists: {s['playlists_count']:,}")
        print(f"   • Playlist tracks: {s['playlist_tracks_count']:,}")
        print(f"   • Unique tracks: {s['tracks_count']:,}")
        print(f"   • Track-artist links: {s['track_artists_count']:,}")
        print(f"   • Artists: {s['artists_count']:,}")
        print("="*50 + "\n")

    # -------------------------
    # Incremental refresh / sync
    # -------------------------
    def sync(self, force: bool = False, owned_only: bool = True, include_liked_songs: bool = True) -> dict:
        """Sync library data - pull new/changed playlists incrementally.
        
        This is the main method to keep your local data up to date.
        Call this periodically to pick up changes to your playlists.
        
        Args:
            force: If True, re-pull everything from scratch
            owned_only: If True, only sync playlists you own (default)
            include_liked_songs: If True, include Liked Songs as master playlist (default)
            
        Returns:
            dict with sync statistics
        """
        print("🔄 Starting library sync...")
        stats = {"playlists_checked": 0, "playlists_updated": 0, "tracks_added": 0, "liked_songs": 0}
        
        # Always refresh playlist list (includes Liked Songs)
        pls = self.playlists(force=True, include_liked_songs=include_liked_songs)
        
        # Filter to owned only
        if owned_only:
            pls = pls[pls["is_owned"].eq(True)].copy()
        
        stats["playlists_checked"] = len(pls)
        
        meta = self.catalog.load_meta()
        old_snapshots = meta.get("playlist_snapshots") or {}
        new_snapshots = {r["playlist_id"]: r.get("snapshot_id") for _, r in pls.iterrows()}

        # Find changed playlists
        changed = []
        if force or not old_snapshots:
            changed = list(new_snapshots.keys())
        else:
            for pid, snap in new_snapshots.items():
                if old_snapshots.get(pid) != snap:
                    changed.append(pid)
        
        stats["playlists_updated"] = len(changed)
        
        if changed:
            changed_names = pls[pls["playlist_id"].isin(changed)]["name"].tolist()
            print(f"📝 {len(changed)} playlist(s) changed: {', '.join(changed_names[:5])}{'...' if len(changed_names) > 5 else ''}")
            
            # Load existing or create new
            pt = self.catalog.load("playlist_tracks")
            if pt is None or force:
                    pt = pd.DataFrame(columns=["playlist_id", "track_id", "track_uri", "is_local", "added_at", "added_by", "position"])
            else:
                pt = pt[~pt["playlist_id"].isin(changed)].copy()

            rows = []
            
            # Handle Liked Songs separately (uses different API)
            if LIKED_SONGS_PLAYLIST_ID in changed:
                liked_rows = self._fetch_liked_songs_rows()
                rows.extend(liked_rows)
                stats["liked_songs"] = len(liked_rows)
                changed = [pid for pid in changed if pid != LIKED_SONGS_PLAYLIST_ID]
            
            # Fetch regular playlists
            iterator = changed
            if self.progress and changed:
                iterator = tqdm(iterator, desc="Syncing playlists", unit="pl")

            for pid in iterator:
                rows.extend(self._fetch_playlist_tracks_rows(pid))

            stats["tracks_added"] = len(rows)
            
            if rows:
                add = pd.DataFrame(rows)
                pt = pd.concat([pt, add], ignore_index=True)
                if "position" in pt.columns:
                    pt["position"] = pd.to_numeric(pt["position"], errors="coerce").astype("Int64")
                self.catalog.save("playlist_tracks", pt)

            # Invalidate downstream caches
            for key in ["tracks","track_artists","artists","library_wide","liked_songs"]:
                p = self.catalog.table_path(key)
                if p.exists():
                    p.unlink(missing_ok=True)
                self.catalog._memo.pop(key, None)
        else:
            print("✅ All playlists up to date!")

        # Update metadata
        meta["playlist_snapshots"] = new_snapshots
        meta["last_sync_utc"] = pd.Timestamp.utcnow().isoformat()
        meta["owned_only"] = owned_only
        meta["include_liked_songs"] = include_liked_songs
        self.catalog.save_meta(meta)
        
        print(f"✅ Sync complete! Checked {stats['playlists_checked']} playlists, updated {stats['playlists_updated']}, added {stats['tracks_added']} track entries")
        if stats["liked_songs"] > 0:
            print(f"❤️  Including {stats['liked_songs']:,} liked songs (master playlist)")
        return stats
    
    def refresh(self, force: bool = False, owned_only: bool = True) -> None:
        """Alias for sync() for backwards compatibility."""
        self.sync(force=force, owned_only=owned_only)

    def _fetch_playlist_tracks_rows(self, playlist_id: str) -> list[dict]:
        first = self._rate_limited(
            self.sp.playlist_items,
            playlist_id,
            limit=100,
            additional_types=("track",),
            fields="items(added_at,added_by.id,track(id,uri,is_local)),next"
        )
        items = self._paginate(first, "items")
        rows = []
        for pos, it in enumerate(items):
            t = it.get("track") or {}
            tid = t.get("id")
            if not tid:
                continue
            rows.append({
                "playlist_id": playlist_id,
                "track_id": tid,
                "track_uri": t.get("uri"),
                "is_local": t.get("is_local"),
                "added_at": it.get("added_at"),
                "added_by": (it.get("added_by") or {}).get("id"),
                "position": pos,
            })
        return rows
    
    def _fetch_liked_songs_rows(self) -> list[dict]:
        """Fetch all liked/saved tracks from user's library."""
        print("❤️  Fetching Liked Songs (your master playlist)...")
        
        all_items = []
        offset = 0
        limit = 50
        
        # First call to get total
        first = self._rate_limited(self.sp.current_user_saved_tracks, limit=limit, offset=0)
        total = first.get("total", 0)
        all_items.extend(first.get("items", []))
        offset += limit
        
        # Paginate through all liked songs
        if self.progress and total > limit:
            pbar = tqdm(total=total, initial=len(all_items), desc="Fetching Liked Songs", unit="track")
        else:
            pbar = None
            
        while offset < total:
            resp = self._rate_limited(self.sp.current_user_saved_tracks, limit=limit, offset=offset)
            items = resp.get("items", [])
            if not items:
                break
            all_items.extend(items)
            offset += len(items)
            if pbar:
                pbar.update(len(items))
        
        if pbar:
            pbar.close()
        
        # Convert to rows
        rows = []
        me = self._me_id()
        for pos, it in enumerate(all_items):
            t = it.get("track") or {}
            tid = t.get("id")
            if not tid:
                continue
            rows.append({
                "playlist_id": LIKED_SONGS_PLAYLIST_ID,
                "track_id": tid,
                "track_uri": t.get("uri"),
                "is_local": t.get("is_local", False),
                "added_at": it.get("added_at"),
                "added_by": me,
                "position": pos,
            })
        
        print(f"❤️  Found {len(rows):,} liked songs")
        return rows
    
    def liked_songs(self, force: bool = False) -> pd.DataFrame:
        """Get all liked/saved songs as a DataFrame."""
        key = "liked_songs"
        if not force:
            df = self.catalog.load(key)
            if df is not None:
                return df
        
        rows = self._fetch_liked_songs_rows()
        df = pd.DataFrame(rows)
        return self.catalog.save(key, df)

    # -------------------------
    # Core tables
    # -------------------------
    def playlists(self, force: bool = False, include_liked_songs: bool = True) -> pd.DataFrame:
        key = "playlists"
        if not force:
            df = self.catalog.load(key)
            if df is not None:
                return df

        first = self._rate_limited(self.sp.current_user_playlists, limit=50)
        items = self._paginate(first, "items")

        rows = []
        me = self._me_id()
        
        # Add Liked Songs as a special master playlist FIRST
        if include_liked_songs:
            # Get liked songs count
            liked_resp = self._rate_limited(self.sp.current_user_saved_tracks, limit=1, offset=0)
            liked_count = liked_resp.get("total", 0)
            
            rows.append({
                "playlist_id": LIKED_SONGS_PLAYLIST_ID,
                "name": LIKED_SONGS_PLAYLIST_NAME,
                "description": "Your liked songs - the master playlist",
                "public": False,
                "collaborative": False,
                "snapshot_id": f"liked_songs_{liked_count}",  # Use count as pseudo-snapshot
                "track_count": liked_count,
                "owner_id": me,
                "owner_name": "You",
                "is_owned": True,  # You own your liked songs!
                "is_liked_songs": True,  # Special flag
                "uri": None,
            })
        
        # Add regular playlists
        for p in items:
            owner = p.get("owner") or {}
            rows.append({
                "playlist_id": p["id"],
                "name": p.get("name"),
                "description": p.get("description"),
                "public": p.get("public"),
                "collaborative": p.get("collaborative"),
                "snapshot_id": p.get("snapshot_id"),
                "track_count": (p.get("tracks") or {}).get("total"),
                "owner_id": owner.get("id"),
                "owner_name": owner.get("display_name"),
                "is_owned": owner.get("id") == me,
                "is_liked_songs": False,
                "uri": p.get("uri"),
            })

        df = pd.DataFrame(rows)
        return self.catalog.save(key, df)

    def playlist_tracks(self, force: bool = False, owned_only: bool = True, include_liked_songs: bool = True) -> pd.DataFrame:
        key = "playlist_tracks"
        if not force:
            df = self.catalog.load(key)
            if df is not None:
                return df

        # full rebuild - filter to owned playlists only by default
        pls = self.playlists(force=force, include_liked_songs=include_liked_songs)
        
        if owned_only:
            pls_to_fetch = pls[pls["is_owned"].eq(True)].copy()
            print(f"📂 Fetching tracks from {len(pls_to_fetch)} owned playlists (skipping {len(pls) - len(pls_to_fetch)} followed playlists)")
        else:
            pls_to_fetch = pls.copy()
            print(f"📂 Fetching tracks from all {len(pls_to_fetch)} playlists")
        
        # Show expected track count
        expected_tracks = pls_to_fetch["track_count"].sum()
        print(f"📊 Expected total track entries: {expected_tracks:,}")
        
        rows = []
        
        # Fetch Liked Songs FIRST (the master playlist)
        if include_liked_songs and LIKED_SONGS_PLAYLIST_ID in pls_to_fetch["playlist_id"].values:
            liked_rows = self._fetch_liked_songs_rows()
            rows.extend(liked_rows)
            # Remove liked songs from the iterator
            pls_to_fetch = pls_to_fetch[pls_to_fetch["playlist_id"] != LIKED_SONGS_PLAYLIST_ID]
        
        # Fetch regular playlists
        iterator = list(pls_to_fetch["playlist_id"].tolist())
        
        if self.progress:
            iterator = tqdm(iterator, desc="Fetching playlist tracks", unit="pl")

        for pid in iterator:
            playlist_rows = self._fetch_playlist_tracks_rows(pid)
            rows.extend(playlist_rows)
            if self.progress and hasattr(iterator, 'set_postfix'):
                iterator.set_postfix(tracks=len(rows))

        df = pd.DataFrame(rows)
        
        # Verification
        actual_tracks = len(df)
        unique_tracks = df["track_id"].nunique() if len(df) > 0 else 0
        liked_count = len(df[df["playlist_id"] == LIKED_SONGS_PLAYLIST_ID]) if len(df) > 0 else 0
        
        print(f"✅ Pulled {actual_tracks:,} track entries ({unique_tracks:,} unique tracks)")
        print(f"❤️  Including {liked_count:,} liked songs (master playlist)")
        
        if actual_tracks < expected_tracks * 0.9:  # Allow 10% tolerance for local/unavailable tracks
            print("⚠️  Warning: Got fewer tracks than expected. Some may be local files or unavailable.")
        
        return self.catalog.save(key, df)

    def tracks(self, force: bool = False) -> pd.DataFrame:
        key = "tracks"
        if not force:
            df = self.catalog.load(key)
            if df is not None:
                return df

        pt = self.playlist_tracks(force=force)
        ids = pd.unique(pt["track_id"]).tolist()

        # Load existing tracks to preserve genres column if present
        existing_df = self.catalog.load(key)
        existing_genres = {}
        if existing_df is not None and "genres" in existing_df.columns:
            existing_genres = existing_df.set_index("track_id")["genres"].to_dict()

        rows = []
        iterator = list(chunks(ids, 50))
        if self.progress:
            iterator = tqdm(iterator, desc="Fetching tracks", unit="chunk")

        for chunk in iterator:
            resp = self._rate_limited(self.sp.tracks, chunk)
            for t in resp.get("tracks", []):
                if not t:
                    continue
                album = t.get("album") or {}
                ext = t.get("external_ids") or {}
                track_id = t.get("id")
                rows.append({
                    "track_id": track_id,
                    "name": t.get("name"),
                    "duration_ms": t.get("duration_ms"),
                    "explicit": t.get("explicit"),
                    "popularity": t.get("popularity"),
                    "album_id": album.get("id"),
                    "album_name": album.get("name"),
                    "release_date": album.get("release_date"),
                    "track_number": t.get("track_number"),
                    "isrc": ext.get("isrc"),
                    "uri": t.get("uri"),
                    # Preserve existing genres or initialize to None
                    "genres": existing_genres.get(track_id, None),
                })

        df = pd.DataFrame(rows).drop_duplicates("track_id")
        # Ensure genres column exists (in case no existing data)
        if "genres" not in df.columns:
            df["genres"] = None
        return self.catalog.save(key, df)

    def track_artists(self, force: bool = False) -> pd.DataFrame:
        key = "track_artists"
        if not force:
            df = self.catalog.load(key)
            if df is not None:
                return df

        # reuse tracks endpoint to get artist lists
        pt = self.playlist_tracks(force=force)
        ids = pd.unique(pt["track_id"]).tolist()

        rows = []
        iterator = list(chunks(ids, 50))
        if self.progress:
            iterator = tqdm(iterator, desc="Fetching track artists", unit="chunk")

        for chunk in iterator:
            resp = self._rate_limited(self.sp.tracks, chunk)
            for t in resp.get("tracks", []):
                if not t:
                    continue
                for i, a in enumerate(t.get("artists", [])):
                    if not a.get("id"):
                        continue
                    rows.append({
                        "track_id": t.get("id"),
                        "artist_id": a.get("id"),
                        "position": i,
                    })

        df = pd.DataFrame(rows).dropna(subset=["track_id","artist_id"])
        return self.catalog.save(key, df)

    def artists(self, force: bool = False) -> pd.DataFrame:
        key = "artists"
        if not force:
            df = self.catalog.load(key)
            if df is not None:
                return df

        ta = self.track_artists(force=force)
        ids = pd.unique(ta["artist_id"]).tolist()

        rows = []
        iterator = list(chunks(ids, 50))
        if self.progress:
            iterator = tqdm(iterator, desc="Fetching artists", unit="chunk")

        for chunk in iterator:
            resp = self._rate_limited(self.sp.artists, chunk)
            for a in resp.get("artists", []):
                if not a:
                    continue
                rows.append({
                    "artist_id": a.get("id"),
                    "name": a.get("name"),
                    "genres": a.get("genres"),
                    "popularity": a.get("popularity"),
                    "followers": (a.get("followers") or {}).get("total"),
                    "uri": a.get("uri"),
                })

        df = pd.DataFrame(rows).drop_duplicates("artist_id")
        return self.catalog.save(key, df)

    def audio_features(self, force: bool = False) -> pd.DataFrame:
        """
        DEPRECATED: Spotify removed the audio features endpoint in November 2024.
        
        This method now returns an empty DataFrame for backwards compatibility.
        New apps created after Nov 2024 cannot access audio features.
        """
        warnings.warn(
            "Spotify deprecated audio features API in November 2024. "
            "This method returns an empty DataFrame.",
            DeprecationWarning,
            stacklevel=2
        )
        return pd.DataFrame(columns=[
            "track_id", "danceability", "energy", "valence", "tempo", "loudness",
            "acousticness", "instrumentalness", "liveness", "speechiness",
            "key", "mode", "time_signature", "duration_ms"
        ])

    def library_wide(self, force: bool = False, owned_only: bool = True) -> pd.DataFrame:
        """Build a wide table joining playlists, tracks, and artists.
        
        Note: Audio features are no longer available (deprecated by Spotify Nov 2024).
        """
        key = "library_wide"
        if not force:
            df = self.catalog.load(key)
            if df is not None:
                return df

        pl = self.playlists(force=force)
        pt = self.playlist_tracks(force=force, owned_only=owned_only)
        tr = self.tracks(force=force)
        ta = self.track_artists(force=force)
        ar = self.artists(force=force)
        
        # Filter playlists to owned only for the join
        if owned_only:
            pl = pl[pl["is_owned"].eq(True)].copy()

        primary = ta[ta["position"].eq(0)].merge(ar, on="artist_id", how="left")
        primary = primary.rename(columns={
            "artist_id": "primary_artist_id",
            "name": "primary_artist",
            "genres": "primary_genres",
            "popularity": "primary_artist_popularity",
            "followers": "primary_artist_followers",
        })

        df = (
            pt.merge(pl, on="playlist_id", how="left")
              .merge(tr, on="track_id", how="left", suffixes=("","_track"))
              .merge(primary[["track_id","primary_artist_id","primary_artist","primary_genres",
                              "primary_artist_popularity","primary_artist_followers"]],
                     on="track_id", how="left")
        )

        return self.catalog.save(key, df)
