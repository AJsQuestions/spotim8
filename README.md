# 🎵 Spotim8

Your **personal Spotify analytics platform** with **automated playlist management**.

Turn your Spotify library into tidy DataFrames, analyze your listening habits, and automatically organize your music into smart playlists.

## ✨ Features

- 📊 **Pandas DataFrames** - Your library as tidy, mergeable tables
- 📅 **Monthly Playlists** - Auto-create playlists like `FindsDec25`
- 🎸 **Genre-Split Playlists** - Separate by HipHop, Dance, Other
- 🎵 **Master Genre Playlists** - All-time playlists by genre
- 🤖 **Daily Automation** - GitHub Actions updates playlists automatically
- 💾 **Local Cache** - Parquet files for fast offline access
- 🔄 **No Duplicates** - Smart deduplication on every run
- 🌐 **Web Dashboard** - Beautiful React UI for analysis (see `spotim8_app/`)

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/yourusername/spotim8.git
cd spotim8

# Install
pip install -e .

# Set credentials
export SPOTIPY_CLIENT_ID="your_client_id"
export SPOTIPY_CLIENT_SECRET="your_client_secret"
export SPOTIPY_REDIRECT_URI="http://127.0.0.1:8888/callback"
```

## 📓 Notebooks

| Notebook | Description |
|----------|-------------|
| `01_sync_data.ipynb` | Download and cache your Spotify library |
| `02_analyze_library.ipynb` | Visualize your listening habits |
| `03_playlist_analysis.ipynb` | Genre analysis and playlist clustering |
| `04_liked_songs_monthly_playlists.ipynb` | **Create all automated playlists** |

### Notebook 04: Playlist Generator

Creates **monthly and genre playlists** automatically:

```
📅 Monthly Playlists:
   {Owner}{Prefix}{Mon}{Year} → e.g., FindsDec25

🎸 Genre-Split Monthly:
   {Genre}{Prefix}{Mon}{Year} → e.g., HipHopFindsDec25, DanceFindsDec25

🎵 Master Genre Playlists:
   {Owner}am{Genre} → e.g., amHip-Hop, amElectronic
```

**Configuration (via environment variables):**
```bash
export PLAYLIST_OWNER_NAME=""      # Your prefix (optional)
export PLAYLIST_PREFIX="Finds"     # Month playlist prefix
```

## 🤖 Daily Automation (GitHub Actions)

Playlists update automatically every day at 2am UTC.

### Setup:
1. Fork this repo or push to your own GitHub
2. Run `python scripts/get_refresh_token.py` locally to get your refresh token
3. Add these **secrets** to your repo (Settings → Secrets → Actions):

| Secret | Required | Description |
|--------|----------|-------------|
| `SPOTIPY_CLIENT_ID` | ✅ | Your Spotify app client ID |
| `SPOTIPY_CLIENT_SECRET` | ✅ | Your Spotify app client secret |
| `SPOTIPY_REDIRECT_URI` | ✅ | `http://127.0.0.1:8888/callback` |
| `SPOTIPY_REFRESH_TOKEN` | ✅ | Get via `get_refresh_token.py` |
| `PLAYLIST_OWNER_NAME` | ❌ | Your name for playlists (default: "") |
| `PLAYLIST_PREFIX` | ❌ | Prefix like "Finds" (default: "Finds") |

### Manual trigger:
Actions → Daily Spotify Playlist Update → Run workflow

## 🌐 Web App

A modern React-based Spotify analytics dashboard:

```bash
cd spotim8_app
npm install
npm run dev
```

**Features:**
- Privacy-first (all data processed in browser)
- Interactive charts and visualizations
- Playlist clusters and hidden gems
- Genre breakdown and artist treemaps
- Release timeline analysis

## 🔧 Python API

```python
from spotim8 import Spotim8, build_all_features

sf = Spotim8.from_env(progress=True)

# Sync your library
sf.sync(owned_only=True, include_liked_songs=True)

# Access your data
playlists = sf.playlists()      # All playlists
tracks = sf.tracks()            # All tracks
artists = sf.artists()          # Artists with genres
wide = sf.library_wide()        # Everything joined
```

## 📁 Data Tables

| Table | Description |
|-------|-------------|
| `playlists()` | Your playlists (including ❤️ Liked Songs) |
| `playlist_tracks()` | Track-playlist relationships with `added_at` |
| `tracks()` | Track metadata (name, duration, popularity) |
| `track_artists()` | Track-artist relationships |
| `artists()` | Artist info with genres |
| `library_wide()` | Everything joined together |

## 🎛️ CLI

```bash
# Sync library
spotim8 refresh

# Check status
spotim8 status

# Export data
spotim8 export --table tracks --out tracks.parquet
```

## 📂 Project Structure

```
spotim8/
├── notebooks/
│   ├── 01_sync_data.ipynb
│   ├── 02_analyze_library.ipynb
│   ├── 03_playlist_analysis.ipynb
│   ├── 04_liked_songs_monthly_playlists.ipynb
│   └── lib.py                    # Shared utilities
├── spotim8_app/                  # React web app
│   ├── src/
│   └── package.json
├── scripts/
│   ├── spotify_sync.py           # Unified sync & playlist update
│   └── get_refresh_token.py      # Get token for CI/CD
├── .github/workflows/
│   └── daily_update.yml          # GitHub Actions workflow
├── spotim8/                      # Core Python library
└── data/                         # Cached parquet files
```

## 📋 Requirements

- Python 3.10+
- Spotify Developer Account
- Spotify Premium (for some features)

## 🔒 Spotify API Notes

Spotify deprecated these endpoints for new apps (Nov 2024):
- ❌ Audio features (danceability, energy, etc.)
- ❌ Audio analysis
- ⚠️ Recommendations (may work for older apps)

This library focuses on what's still available.

## 📄 License

MIT

---

🎓 **Open Source Academic Project** - Built for learning and personal use.
