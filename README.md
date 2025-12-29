# 🎵 Spotim8

**Personal Spotify analytics platform** with **automated playlist management**.

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

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/AJsQuestions/spotim8.git
cd spotim8

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -e .
```

### 2. Spotify API Setup

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

### 3. Environment Configuration

Create a `.env` file in the project root:

```bash
cp env.example .env
```

Edit `.env` and add your credentials:

```bash
# Required
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

# Optional: Get refresh token for automated runs (no browser needed)
# Run: python scripts/get_token.py
SPOTIPY_REFRESH_TOKEN=your_refresh_token_here

# Optional: Customize playlist naming
PLAYLIST_OWNER_NAME=AJ
PLAYLIST_PREFIX=Finds

# Optional: Email notifications
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=your_email@gmail.com
EMAIL_SMTP_PASSWORD=your_app_password
EMAIL_TO=recipient@example.com
```

### 4. Get Refresh Token (Recommended)

For automated runs without browser interaction:

```bash
source venv/bin/activate
python scripts/get_token.py
```

This will open your browser for Spotify authorization and generate a refresh token.

### 5. First Sync

```bash
# Sync your library (first time can take 1-2+ hours for large libraries)
python scripts/sync.py
```

---

## 🔧 Python API

```python
from spotim8 import Spotim8

# Initialize client
sf = Spotim8.from_env(progress=True)

# Sync your library
sf.sync(owned_only=True, include_liked_songs=True)

# Access your data
playlists = sf.playlists()      # All playlists
tracks = sf.tracks()            # All tracks
artists = sf.artists()          # Artists with genres
wide = sf.library_wide()        # Everything joined
```

See [examples/01_quickstart.py](examples/01_quickstart.py) for a complete example.

---

## 📓 Notebooks

| Notebook | Description |
|----------|-------------|
| `01_sync_data.ipynb` | Download and cache your Spotify library |
| `02_analyze_library.ipynb` | Visualize your listening habits |
| `03_playlist_analysis.ipynb` | Genre analysis and playlist clustering |
| `04_liked_songs_monthly_playlists.ipynb` | **Create all automated playlists** |
| `05_identify_redundant_playlists.ipynb` | Find and consolidate similar playlists |

### Playlist Generation

Notebook `04_liked_songs_monthly_playlists.ipynb` creates automated playlists:

```
📅 Monthly Playlists:
   {Owner}{Prefix}{Mon}{Year} → e.g., FindsDec25

🎸 Genre-Split Monthly:
   {Genre}{Prefix}{Mon}{Year} → e.g., HipHopFindsDec25, DanceFindsDec25

🎵 Master Genre Playlists:
   {Owner}am{Genre} → e.g., amHip-Hop, amElectronic
```

---

## 🤖 Automation

### Sync Options

```bash
# Full sync + playlist update (default)
python scripts/sync.py

# Or use the helper script (handles environment variables)
python scripts/runner.py

# Skip sync, only update playlists (fast, uses existing data)
python scripts/sync.py --skip-sync

# Sync only, don't update playlists
python scripts/sync.py --sync-only

# Process all months, not just current month
python scripts/sync.py --all-months
```

### Scheduled Automation (Cron)

Set up daily sync on Linux/Mac:

```bash
# Easy setup (recommended):
./scripts/cron.sh
```

The cron job runs daily at 2:00 AM and logs to `logs/sync.log`.

**Features:**
- ✅ Automatic log rotation (keeps last 3 backups)
- ✅ Prevents concurrent runs with lock file mechanism
- ✅ Dependency verification before execution
- ✅ Automatic cleanup on errors
- ✅ macOS permission handling

**Manual setup** (if needed):
```bash
crontab -e
# Add: 0 2 * * * /bin/bash /path/to/spotim8/scripts/cron_wrapper.sh
```

**Test the wrapper manually:**
```bash
/bin/bash scripts/cron_wrapper.sh --skip-sync
```

### Email Notifications

Get email notifications after each sync run. Configure in your `.env` file:

**Gmail Setup:**
1. Enable 2-factor authentication on your Gmail account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Add to `.env`:
   ```bash
   EMAIL_ENABLED=true
   EMAIL_SMTP_HOST=smtp.gmail.com
   EMAIL_SMTP_PORT=587
   EMAIL_SMTP_USER=your_email@gmail.com
   EMAIL_SMTP_PASSWORD=your_16_char_app_password
   EMAIL_TO=recipient@example.com
   ```

**Other Email Providers:**
- **Outlook/Hotmail**: `smtp-mail.outlook.com`, port `587`
- **Yahoo**: `smtp.mail.yahoo.com`, port `587`
- **Custom SMTP**: Use your provider's SMTP settings

**Note:** Email failures won't break the sync - notifications are non-blocking.

### Why Local Execution?

- ✅ **No timeouts** - Large libraries can sync for hours without interruption
- ✅ **Faster** - No CI/CD overhead, direct API access
- ✅ **Resumable** - Script supports checkpointing for interrupted syncs
- ✅ **Cost-free** - Uses your own machine, no CI minutes
- ✅ **Better debugging** - Direct access to logs and data files

---


## 📁 Data Tables

| Table | Description |
|-------|-------------|
| `playlists()` | Your playlists (including ❤️ Liked Songs) |
| `playlist_tracks()` | Track-playlist relationships with `added_at` |
| `tracks()` | Track metadata (name, duration, popularity) |
| `track_artists()` | Track-artist relationships |
| `artists()` | Artist info with genres |
| `library_wide()` | Everything joined together |

---

## 🎛️ CLI

```bash
# Sync library
spotim8 refresh

# Check status
spotim8 status

# Export data
spotim8 export --table tracks --out tracks.parquet

# Market data (browse/search)
spotim8 market --kind new_releases --country US --limit 50 --out releases.parquet
```

---

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
│   ├── market.py                 # Market data (browse/search)
│   ├── export.py                 # Data export utilities
│   ├── ratelimit.py              # Rate limiting utilities
│   └── utils.py                  # Helper functions
├── notebooks/                    # Jupyter notebooks for analysis
│   ├── 01_sync_data.ipynb        # Sync library data
│   ├── 02_analyze_library.ipynb  # Visualize listening habits
│   ├── 03_playlist_analysis.ipynb # Genre analysis & clustering
│   ├── 04_liked_songs_monthly_playlists.ipynb # Create playlists
│   └── 05_identify_redundant_playlists.ipynb # Find similar playlists
├── scripts/                      # Automation and utility scripts
│   ├── sync.py                   # Main sync & playlist update
│   ├── runner.py                 # Local sync runner (cron wrapper)
│   ├── setup.py                  # Initial setup helper
│   ├── get_token.py              # Get refresh token for automation
│   ├── email_notify.py           # Email notification service
│   └── cron.sh                   # Cron job setup
├── examples/
│   └── 01_quickstart.py          # Quick start example
├── tests/                        # Test suite
├── data/                         # Cached parquet files (gitignored)
└── logs/                         # Log files (gitignored)
```

---

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
2. Get a fresh refresh token: `python scripts/get_token.py`
3. Check that your Spotify app is not in "Development Mode" with restricted users (if using a free account)

### Sync Takes Too Long

- First sync always takes longest (hours for large libraries)
- Use `--skip-sync` to only update playlists without re-syncing:
  ```bash
  python scripts/runner.py --skip-sync
  ```

### Check Logs

```bash
tail -f logs/sync.log
```

---

## 🔒 Security & Secrets

**Do NOT commit secrets** (client IDs, client secrets, refresh tokens) to this repository.

- Keep local credentials in a `.env` file and never commit it
- This repository already ignores `.env` and common secret files via `.gitignore`
- If you accidentally commit a secret, rotate it immediately (revoke the secret in the provider) and remove it from git history

---

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

---

## 📝 Spotify API Notes

Spotify deprecated these endpoints for new apps (Nov 2024):
- ❌ Audio features (danceability, energy, etc.)
- ❌ Audio analysis
- ⚠️ Recommendations (may work for older apps)

This library focuses on what's still available.

---

## 📄 License

MIT - See [LICENSE](LICENSE) for details.

---

🎓 **Open Source Academic Project** - Built for learning and personal use.
