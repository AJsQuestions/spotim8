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

## 📋 Requirements

- Python 3.10+
- Spotify Developer Account (free)
- Spotify Premium (for some features)

## 🚀 Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/AJsQuestions/spotim8.git
cd spotim8

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -e .
```

### Spotify API Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Log in with your Spotify account
3. Click **"Create app"**
4. Fill in:
   - **App name**: Spotim8 (or any name)
   - **App description**: Personal Spotify analytics
   - **Redirect URI**: `http://127.0.0.1:8888/callback` ⚠️ **Must match exactly**
   - Check **"I understand and agree..."**
5. Click **"Save"**
6. Copy your **Client ID** and **Client Secret** from Settings

### Environment Configuration

Create a `.env` file in the project root:

```bash
cp env.example .env
```

Edit `.env` and add your credentials:

```bash
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

# Optional: Get refresh token for automated runs (no browser needed)
# Run: python scripts/get_refresh_token.py
SPOTIPY_REFRESH_TOKEN=your_refresh_token_here

# Optional: Customize playlist naming
PLAYLIST_OWNER_NAME=AJ
PLAYLIST_PREFIX=Finds
```

### Get Refresh Token (Recommended for Automation)

For automated runs without browser interaction:

```bash
source venv/bin/activate
python scripts/get_refresh_token.py
```

This will:
- Open your browser for Spotify authorization
- Generate a refresh token
- Show you the token to add to your `.env` file

### First Run

```bash
# Sync your library (first time can take 1-2+ hours for large libraries)
python scripts/spotify_sync.py
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

## 🤖 Local Automation

Run the sync script locally for better reliability and no timeout issues. Large libraries can take hours to sync, which often exceeds CI/CD time limits.

### Sync Options

```bash
# Full sync + playlist update (default)
python scripts/spotify_sync.py

# Or use the helper script (handles environment variables)
python scripts/run_sync_local.py

# Skip sync, only update playlists (fast, uses existing data)
python scripts/spotify_sync.py --skip-sync

# Sync only, don't update playlists
python scripts/spotify_sync.py --sync-only

# Process all months, not just current month
python scripts/spotify_sync.py --all-months
```

### Scheduled Automation (Cron)

Set up daily sync on Linux/Mac:

```bash
# Easy setup (recommended):
./scripts/setup_cron.sh

# Or manually edit crontab:
crontab -e
# Add: 0 2 * * * cd /path/to/spotim8 && /path/to/venv/bin/python scripts/run_sync_local.py >> logs/sync.log 2>&1
```

The cron job runs daily at 2:00 AM and logs to `logs/sync.log`.

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
│   ├── features.py               # Feature engineering
│   ├── genres.py                 # Genre classification
│   ├── analysis.py               # Library analysis utilities
│   └── ...                       # Other utilities
├── notebooks/                    # Jupyter notebooks for analysis
│   ├── 01_sync_data.ipynb        # Sync library data
│   ├── 02_analyze_library.ipynb  # Visualize listening habits
│   ├── 03_playlist_analysis.ipynb # Genre analysis & clustering
│   └── 04_liked_songs_monthly_playlists.ipynb # Create playlists
├── scripts/                      # Automation scripts
│   ├── spotify_sync.py           # Unified sync & playlist update
│   ├── run_sync_local.py         # Local sync runner (cron wrapper)
│   ├── setup_local.py            # Initial setup helper
│   ├── get_refresh_token.py      # Get token for automation
│   └── setup_cron.sh             # Cron job setup
├── examples/
│   └── 01_quickstart.py          # Quick start example
├── tests/                        # Test suite
└── data/                         # Cached parquet files (gitignored)
```

## 🔒 Security & Secrets

**Do NOT commit secrets** (client IDs, client secrets, refresh tokens) to this repository.

- Keep local credentials in a `.env` file and never commit it
- This repository already ignores `.env` and common secret files via `.gitignore`
- If you accidentally commit a secret, rotate it immediately (revoke the secret in the provider) and remove it from git history

## 🐛 Troubleshooting

### Virtual Environment Not Found

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### Missing Credentials Error

Make sure your `.env` file exists and has:
- `SPOTIPY_CLIENT_ID`
- `SPOTIPY_CLIENT_SECRET`

### Authentication Issues

1. Make sure your redirect URI matches exactly: `http://127.0.0.1:8888/callback`
2. Get a fresh refresh token: `python scripts/get_refresh_token.py`
3. Check that your Spotify app is not in "Development Mode" with restricted users (if using a free account)

### Sync Takes Too Long

- First sync always takes longest (hours for large libraries)
- Use `--skip-sync` to only update playlists without re-syncing:
  ```bash
  python scripts/run_sync_local.py --skip-sync
  ```

### Check Logs

```bash
tail -f logs/sync.log
```

## 🤝 Contributing

Thank you for your interest in contributing to Spotim8!

### Development Setup

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Format code
black spotim8/
ruff check spotim8/
```

### Code Style

- **Python**: Follow PEP 8, use `black` for formatting, `ruff` for linting
- **Commits**: Use clear, descriptive commit messages

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear commits
3. Test your changes locally
4. Update documentation if needed
5. Submit a pull request with a clear description

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
