"""
Spotim8 - Pandas-first interface to Spotify Web API.

Turns Spotify into tidy DataFrames you can merge().

Usage:
    from spotim8 import Spotim8
    
    sf = Spotim8.from_env(progress=True)
    sf.sync()
    
    playlists = sf.playlists()
    tracks = sf.tracks()
    artists = sf.artists()
"""

from .client import (
    Spotim8,
    LIKED_SONGS_PLAYLIST_ID,
    LIKED_SONGS_PLAYLIST_NAME,
    DEFAULT_SCOPE,
)
from .catalog import CacheConfig, DataCatalog
from .ratelimit import set_response_cache
from .export import export_table
from .features import (
    playlist_profile_features,
    artist_concentration_features,
    time_features,
    release_year_features,
    popularity_tier_features,
    build_all_features,
)
from .genres import (
    GENRE_SPLIT_RULES,
    SPLIT_GENRES,
    GENRE_RULES,
    ALL_BROAD_GENRES,
    get_split_genre,
    get_broad_genre,
)
from .analysis import (
    LibraryAnalyzer,
    PlaylistSimilarityEngine,
    get_genres_list,
    build_playlist_genre_profiles,
    canonical_core_genre,
)

__version__ = "1.0.0"

__all__ = [
    # Main client
    "Spotim8",
    # Constants
    "LIKED_SONGS_PLAYLIST_ID",
    "LIKED_SONGS_PLAYLIST_NAME",
    "DEFAULT_SCOPE",
    # Configuration
    "CacheConfig",
    "DataCatalog",
    "set_response_cache",
    # Utilities
    "export_table",
    # Feature engineering
    "playlist_profile_features",
    "artist_concentration_features",
    "time_features",
    "release_year_features",
    "popularity_tier_features",
    "build_all_features",
    # Genre classification
    "GENRE_SPLIT_RULES",
    "SPLIT_GENRES",
    "GENRE_RULES",
    "ALL_BROAD_GENRES",
    "get_split_genre",
    "get_broad_genre",
    # Analysis utilities
    "LibraryAnalyzer",
    "PlaylistSimilarityEngine",
    "get_genres_list",
    "build_playlist_genre_profiles",
    "canonical_core_genre",
]
