"""
Library analysis utilities for Spotify data.

Provides LibraryAnalyzer and PlaylistSimilarityEngine for analyzing
and filtering Spotify library data.
"""

import re
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter
from typing import Optional, List, Set, Dict

from spotim8.genres import (
    GENRE_SPLIT_RULES,
    SPLIT_GENRES,
    GENRE_RULES,
    get_split_genre,
    get_broad_genre,
)


class LibraryAnalyzer:
    """Modular library analyzer with configurable filters.
    
    Usage:
        analyzer = LibraryAnalyzer(DATA_DIR).load()
        analyzer.filter(
            exclude_liked=True,
            exclude_monthly=True,
            include_only=["Playlist1", "Playlist2"],
            exclude_names=["Test"]
        )
        
        # Access filtered data
        playlists = analyzer.playlists
        tracks = analyzer.tracks
    """
    
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._loaded = False
        
        # Raw data (all)
        self.playlists_all: Optional[pd.DataFrame] = None
        self.tracks_all: Optional[pd.DataFrame] = None
        self.artists_all: Optional[pd.DataFrame] = None
        self.playlist_tracks_all: Optional[pd.DataFrame] = None
        self.track_artists_all: Optional[pd.DataFrame] = None
        
        # Filtered data
        self.playlists: Optional[pd.DataFrame] = None
        self.tracks: Optional[pd.DataFrame] = None
        self.artists: Optional[pd.DataFrame] = None
        self.playlist_tracks: Optional[pd.DataFrame] = None
        self.track_artists: Optional[pd.DataFrame] = None
        
        # Metadata
        self.liked_songs_id: Optional[str] = None
        self.monthly_playlist_ids: Set[str] = set()
        
    def load(self) -> "LibraryAnalyzer":
        """Load all data from parquet files."""
        try:
            self.playlists_all = pd.read_parquet(self.data_dir / "playlists.parquet")
            self.tracks_all = pd.read_parquet(self.data_dir / "tracks.parquet")
            self.artists_all = pd.read_parquet(self.data_dir / "artists.parquet")
            self.playlist_tracks_all = pd.read_parquet(self.data_dir / "playlist_tracks.parquet")
            self.track_artists_all = pd.read_parquet(self.data_dir / "track_artists.parquet")
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Data not found in {self.data_dir}. Run sync first!"
            ) from e
        
        # Detect special playlists
        liked = self.playlists_all[self.playlists_all.get('is_liked_songs', False) == True]
        self.liked_songs_id = liked['playlist_id'].iloc[0] if len(liked) > 0 else None
        self.monthly_playlist_ids = self._detect_monthly_playlists()
        
        self._loaded = True
        print(f"✅ Loaded {len(self.playlists_all)} playlists, {len(self.tracks_all):,} tracks")
        return self
    
    def _detect_monthly_playlists(self) -> Set[str]:
        """Detect playlists representing months (Jan'25, Dec'24, 2024-01, etc.)."""
        monthly_ids = set()
        patterns = [
            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)['\"']?\s?\d{2,4}$",
            r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s*\d{4}$",
            r"^\d{4}[-/]\d{2}$",
            r"^\d{2}[-/]\d{4}$",
        ]
        owned = self.playlists_all[self.playlists_all['is_owned'] == True]
        for _, row in owned.iterrows():
            name = str(row.get('name', '')).strip()
            for pattern in patterns:
                if re.match(pattern, name, re.IGNORECASE):
                    monthly_ids.add(row['playlist_id'])
                    break
        return monthly_ids
    
    def filter(
        self,
        exclude_liked: bool = False,
        exclude_monthly: bool = False,
        include_only: Optional[List[str]] = None,
        exclude_names: Optional[List[str]] = None
    ) -> "LibraryAnalyzer":
        """Apply filters to the data.
        
        Args:
            exclude_liked: Exclude Liked Songs from analysis
            exclude_monthly: Exclude monthly playlists (Jan'25, etc.)
            include_only: Only include playlists with these names (None = all)
            exclude_names: Exclude playlists with these names
            
        Returns:
            self for chaining
        """
        if not self._loaded:
            raise ValueError("Call load() first!")
        
        # Start with owned playlists
        self.playlists = self.playlists_all[self.playlists_all['is_owned'] == True].copy()
        
        if exclude_liked and self.liked_songs_id:
            self.playlists = self.playlists[self.playlists['playlist_id'] != self.liked_songs_id]
            print(f"   ✗ Excluded Liked Songs")
        
        if exclude_monthly and self.monthly_playlist_ids:
            before = len(self.playlists)
            self.playlists = self.playlists[~self.playlists['playlist_id'].isin(self.monthly_playlist_ids)]
            print(f"   ✗ Excluded {before - len(self.playlists)} monthly playlists")
        
        if include_only:
            self.playlists = self.playlists[self.playlists['name'].isin(include_only)]
            print(f"   ✓ Included only: {include_only}")
        
        if exclude_names:
            self.playlists = self.playlists[~self.playlists['name'].isin(exclude_names)]
            print(f"   ✗ Excluded: {exclude_names}")
        
        # Filter downstream data
        playlist_ids = set(self.playlists['playlist_id'])
        self.playlist_tracks = self.playlist_tracks_all[
            self.playlist_tracks_all['playlist_id'].isin(playlist_ids)
        ].copy()
        
        track_ids = set(self.playlist_tracks['track_id'])
        self.tracks = self.tracks_all[self.tracks_all['track_id'].isin(track_ids)].copy()
        
        self.track_artists = self.track_artists_all[
            self.track_artists_all['track_id'].isin(track_ids)
        ].copy()
        
        artist_ids = set(self.track_artists['artist_id'])
        self.artists = self.artists_all[self.artists_all['artist_id'].isin(artist_ids)].copy()
        
        print(f"\n📊 Analysis scope:")
        print(f"   {len(self.playlists)} playlists | {len(self.tracks):,} tracks | {len(self.artists):,} artists")
        return self
    
    def get_monthly_playlist_names(self) -> List[str]:
        """Get names of detected monthly playlists."""
        df = self.playlists_all[self.playlists_all['playlist_id'].isin(self.monthly_playlist_ids)]
        return sorted(df['name'].tolist())
    
    def get_followed_playlists(self) -> pd.DataFrame:
        """Get followed (not owned) playlists."""
        return self.playlists_all[self.playlists_all['is_owned'] == False].copy()
    
    def stats(self) -> Dict:
        """Get summary statistics for filtered data."""
        if self.playlists is None:
            return {}
        return {
            'total_tracks': len(self.tracks) if self.tracks is not None else 0,
            'total_artists': len(self.artists) if self.artists is not None else 0,
            'total_playlists': len(self.playlists),
            'total_hours': self.tracks['duration_ms'].sum() / 3600000 if self.tracks is not None and 'duration_ms' in self.tracks else 0,
            'avg_popularity': self.tracks['popularity'].mean() if self.tracks is not None and 'popularity' in self.tracks else 0,
        }


def get_genres_list(x) -> List[str]:
    """Convert genres column to a Python list, handling various formats."""
    if x is None:
        return []
    if isinstance(x, np.ndarray):
        return list(x)
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        if x == '[]' or x == '' or x.lower() == 'nan':
            return []
        try:
            import ast
            val = ast.literal_eval(x)
            if isinstance(val, (list, tuple, set)):
                return list(val)
            return [val]
        except:
            if ',' in x:
                return [t.strip() for t in x.split(',') if t.strip()]
            return [x]
    return []


def build_playlist_genre_profiles(
    playlists: pd.DataFrame,
    playlist_tracks: pd.DataFrame,
    track_artists: pd.DataFrame,
    artists: pd.DataFrame
) -> Dict[str, Counter]:
    """Build genre count profiles for each playlist.
    
    Returns:
        Dict mapping playlist_id -> Counter of genre counts
    """
    # Build track -> genres mapping via primary artist
    primary_artists = track_artists[track_artists["position"] == 0].copy()
    track_genres = primary_artists.merge(artists[["artist_id", "genres"]], on="artist_id")
    track_genres["genres_list"] = track_genres["genres"].apply(get_genres_list)
    track_genres_map = track_genres.set_index("track_id")["genres_list"].to_dict()
    
    profiles = {}
    for _, row in playlists.iterrows():
        pid = row["playlist_id"]
        pt = playlist_tracks[playlist_tracks["playlist_id"] == pid]
        genres = Counter()
        for tid in pt["track_id"]:
            genres.update(track_genres_map.get(tid, []))
        profiles[pid] = genres
    
    return profiles


def canonical_core_genre(genres: List[str]) -> Optional[str]:
    """Map a list of specific genres to a broad category.
    
    Uses exhaustive genre rules from spotim8.genres module.
    
    Returns one of: Hip-Hop, R&B/Soul, Electronic, Rock, Pop, Indie,
    Latin, World, Jazz, Classical, Country/Folk, Metal, Blues, or None.
    """
    return get_broad_genre(genres)


class PlaylistSimilarityEngine:
    """Engine for finding similar playlists based on genre profiles."""
    
    def __init__(self, analyzer: LibraryAnalyzer):
        self.analyzer = analyzer
        self._profiles: Dict[str, Counter] = {}
        self._all_genres: List[str] = []
        self._vectors: Optional[np.ndarray] = None
        self._playlist_ids: List[str] = []
        self._built = False
    
    def build(self, include_followed: bool = True) -> "PlaylistSimilarityEngine":
        """Build similarity index for playlists.
        
        Args:
            include_followed: If True, includes followed playlists in the index
        """
        if include_followed:
            playlists = self.analyzer.playlists_all
            playlist_tracks = self.analyzer.playlist_tracks_all
        else:
            playlists = self.analyzer.playlists
            playlist_tracks = self.analyzer.playlist_tracks
        
        # Build profiles
        self._profiles = build_playlist_genre_profiles(
            playlists,
            playlist_tracks,
            self.analyzer.track_artists_all,
            self.analyzer.artists_all
        )
        
        # Get all unique genres
        all_genres_set = set()
        for genres in self._profiles.values():
            all_genres_set.update(genres.keys())
        self._all_genres = sorted(list(all_genres_set))
        
        # Build vectors
        self._playlist_ids = list(self._profiles.keys())
        vectors = []
        for pid in self._playlist_ids:
            genres = self._profiles.get(pid, Counter())
            total = sum(genres.values()) or 1
            vec = [genres.get(g, 0) / total for g in self._all_genres]
            vectors.append(vec)
        
        self._vectors = np.array(vectors)
        self._built = True
        return self
    
    def find_similar(
        self,
        playlist_id: str,
        top_n: int = 10,
        only_followed: bool = False,
        only_owned: bool = False
    ) -> List[Dict]:
        """Find playlists similar to the given playlist.
        
        Args:
            playlist_id: ID of the source playlist
            top_n: Number of results to return
            only_followed: Only return followed (not owned) playlists
            only_owned: Only return owned playlists
            
        Returns:
            List of dicts with playlist_id, name, similarity, is_owned
        """
        if not self._built:
            raise ValueError("Call build() first!")
        
        if playlist_id not in self._playlist_ids:
            return []
        
        try:
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            raise ImportError("scikit-learn is required for playlist similarity. Install with: pip install scikit-learn")
        
        idx = self._playlist_ids.index(playlist_id)
        source_vec = self._vectors[idx:idx+1]
        
        similarities = cosine_similarity(source_vec, self._vectors)[0]
        
        # Get playlist metadata
        playlist_info = self.analyzer.playlists_all.set_index('playlist_id')
        
        results = []
        sorted_indices = np.argsort(similarities)[::-1]
        
        for i in sorted_indices:
            pid = self._playlist_ids[i]
            if pid == playlist_id:
                continue  # Skip self
            
            if pid not in playlist_info.index:
                continue
            
            info = playlist_info.loc[pid]
            # playlist_info.loc[pid] returns a Series, use direct indexing
            is_owned = bool(info['is_owned']) if 'is_owned' in info.index else False
            name = str(info['name']) if 'name' in info.index else 'Unknown'
            track_count = int(info['track_count']) if 'track_count' in info.index else 0
            
            # Apply filters
            if only_followed and is_owned:
                continue
            if only_owned and not is_owned:
                continue
            
            results.append({
                'playlist_id': pid,
                'name': name,
                'similarity': float(similarities[i]),
                'is_owned': is_owned,
                'track_count': track_count,
            })
            
            if len(results) >= top_n:
                break
        
        return results
    
    def get_playlist_genres(self, playlist_id: str, top_n: int = 10) -> List[tuple]:
        """Get top genres for a playlist."""
        if playlist_id not in self._profiles:
            return []
        return self._profiles[playlist_id].most_common(top_n)

