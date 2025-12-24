# 🎵 Spotim8

Your **personal Spotify analytics platform** with **automated playlist management**.

Turn your Spotify library into tidy DataFrames, analyze your listening habits, and automatically organize your music into smart playlists.

## ✨ Features

- 📊 **Pandas DataFrames** - Your library as tidy, mergeable tables
- 📅 **Monthly Playlists** - Auto-create playlists like `FindsDec25`
- 🎸 **Genre-Split Playlists** - Separate by HipHop, Dance, Other
- 🎵 **Master Genre Playlists** - All-time playlists by genre
- 🤖 **Daily Automation** - Local cron job updates playlists automatically
- 💾 **Local Cache** - Parquet files for fast offline access
- 🔄 **No Duplicates** - Smart deduplication on every run

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/AJsQuestions/spotim8.git
cd spotim8

# Install
pip install -e .

# Set credentials
export SPOTIPY_CLIENT_ID="your_client_id"
export SPOTIPY_CLIENT_SECRET="your_client_secret"
export SPOTIPY_REDIRECT_URI="http://127.0.0.1:8888/callback"
```

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

## 🤖 Local Automation

Run the sync script locally for better reliability and no timeout issues. Large libraries can take hours to sync, which often exceeds CI/CD time limits.

### Quick Start

```bash
# Run sync + playlist updates (first time setup - can take 1-2+ hours for large libraries)
python scripts/spotify_sync.py

# Or use the helper script (handles environment variables)
./scripts/run_sync_local.sh
```

### Environment Setup

Create a `.env` file in the project root (or export variables):

```bash
SPOTIPY_CLIENT_ID=your_client_id
SPOTIPY_CLIENT_SECRET=your_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
PLAYLIST_OWNER_NAME=""        # Optional: prefix for playlists
PLAYLIST_PREFIX="Finds"        # Optional: month playlist prefix
```

**Note:** On first run, you'll authenticate via browser. For automated runs, get a refresh token:
```bash
python scripts/get_refresh_token.py
# Then add to .env: SPOTIPY_REFRESH_TOKEN=your_refresh_token
```

### Scheduled Automation (Cron)

Set up daily sync on Linux/Mac:

```bash
# Easy setup (recommended):
./scripts/setup_cron.sh

# Or manually edit crontab:
crontab -e
# Add: 0 2 * * * cd /path/to/spotim8 && ./scripts/run_sync_local.sh >> logs/sync.log 2>&1
```

The cron job runs daily at 2:00 AM and logs to `logs/sync.log`.

### Sync Options

```bash
# Full sync + playlist update (default)
python scripts/spotify_sync.py

# Skip sync, only update playlists (fast, uses existing data)
python scripts/spotify_sync.py --skip-sync

# Sync only, don't update playlists
python scripts/spotify_sync.py --sync-only

# Process all months, not just current month
python scripts/spotify_sync.py --all-months
```

### Why Local Execution?

- ✅ **No timeouts** - Large libraries can sync for hours without interruption
- ✅ **Faster** - No CI/CD overhead, direct API access
- ✅ **Resumable** - Script supports checkpointing for interrupted syncs
- ✅ **Cost-free** - Uses your own machine, no CI minutes
- ✅ **Better debugging** - Direct access to logs and data files

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
├── spotim8/                      # Core Python library
│   ├── client.py                 # Main Spotim8 class
│   ├── catalog.py                # Data caching layer
│   ├── cli.py                    # Command line interface
│   └── features.py               # Feature engineering
├── notebooks/
│   ├── 01_sync_data.ipynb
│   ├── 02_analyze_library.ipynb
│   ├── 03_playlist_analysis.ipynb
│   ├── 04_liked_songs_monthly_playlists.ipynb
│   └── lib.py                    # Shared utilities
├── scripts/
│   ├── spotify_sync.py           # Unified sync & playlist update
│   └── get_refresh_token.py      # Get token for CI/CD
├── .github/workflows/
│   └── spotify_sync.yml          # Daily sync & playlist update
├── examples/
│   └── 01_quickstart.py          # Quick start example
└── data/                         # Cached parquet files (gitignored)
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

MIT - See [LICENSE](LICENSE) for details.

---

🎓 **Open Source Academic Project** - Built for learning and personal use.
