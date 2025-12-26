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
# Run: python scripts/get_token.py
SPOTIPY_REFRESH_TOKEN=your_refresh_token_here

# Optional: Customize playlist naming
PLAYLIST_OWNER_NAME=AJ
PLAYLIST_PREFIX=Finds

# Optional: Email notifications (sends email after each cron run)
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=your_email@gmail.com
EMAIL_SMTP_PASSWORD=your_app_password
EMAIL_TO=recipient@example.com
EMAIL_FROM=your_email@gmail.com  # Optional, defaults to EMAIL_SMTP_USER
EMAIL_SUBJECT_PREFIX=[Spotify Sync]  # Optional prefix for email subject
```

### Get Refresh Token (Recommended for Automation)

For automated runs without browser interaction:

```bash
source venv/bin/activate
python scripts/get_token.py
```

This will:
- Open your browser for Spotify authorization
- Generate a refresh token
- Show you the token to add to your `.env` file

### First Run

```bash
# Sync your library (first time can take 1-2+ hours for large libraries)
python scripts/sync.py
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

# Or manually edit crontab:
crontab -e
# Add: 0 2 * * * cd /path/to/spotim8 && /path/to/venv/bin/python scripts/runner.py >> logs/sync.log 2>&1
```

The cron job runs daily at 2:00 AM and logs to `logs/sync.log`.

### Email Notifications

Get email notifications after each sync run (success or failure). Configure in your `.env` file:

**Gmail Setup:**
1. Enable 2-factor authentication on your Gmail account
2. Generate an [App Password](https://myaccount.google.com/apppasswords):
   - Go to Google Account → Security → 2-Step Verification → App passwords
   - Select "Mail" and "Other (Custom name)" → Enter "Spotify Sync"
   - Copy the generated 16-character password
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

**Email Features:**
- ✅ Success/failure status
- ✅ Summary statistics (tracks added, playlists updated, etc.)
- ✅ Full log output
- ✅ Error details if sync fails
- ✅ HTML-formatted emails

**Note:** Email failures won't break the sync - notifications are non-blocking.

### Why Local Execution?

- ✅ **No timeouts** - Large libraries can sync for hours without interruption
- ✅ **Faster** - No CI/CD overhead, direct API access
- ✅ **Resumable** - Script supports checkpointing for interrupted syncs
- ✅ **Cost-free** - Uses your own machine, no CI minutes
- ✅ **Better debugging** - Direct access to logs and data files

## 📱 iOS App (Personal Use)

A simple iOS app to trigger sync automation and static analysis from your iPhone.

### Quick Setup

1. **Start the server** (on your Mac/computer):
   ```bash
   source venv/bin/activate
   python server/server.py
   ```
   Note the IP address and port shown (e.g., `http://192.168.1.252:5001`)
   
   **Note:** Port 5000 is often used by AirPlay on macOS, so the server defaults to port 5001.

2. **Build the iOS app:**
   - Create a new Xcode project and add source files from `apps/ios/Spotim8/`
   - See [apps/ios/README.md](apps/ios/README.md) for detailed step-by-step instructions
   - Connect your iPhone
   - Build and run (⌘R)

3. **Configure the app:**
   - Open Settings (gear icon)
   - Enter your server IP address
   - Test connection and save

4. **Use the app:**
   - Tap "Run Sync Automation" to trigger sync
   - Tap "Run Static Analysis" to analyze your library

**📖 For complete step-by-step setup instructions, see [apps/ios/README.md](apps/ios/README.md)**

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
├── scripts/                      # Automation and utility scripts
│   ├── sync.py                   # Main sync & playlist update
│   ├── runner.py                 # Local sync runner (cron wrapper)
│   ├── setup.py                  # Initial setup helper
│   ├── get_token.py              # Get refresh token for automation
│   ├── email_notify.py           # Email notification service
│   └── cron.sh                   # Cron job setup
├── server/                       # HTTP server for iOS app
│   ├── server.py                 # Flask server
│   ├── requirements.txt          # Server dependencies
│   ├── start_server.sh           # Convenience script
│   └── README.md                 # Server documentation
├── apps/                         # Client applications
│   └── ios/                      # iOS app (SwiftUI)
│       ├── Spotim8/              # Swift source files
│       │   ├── Spotim8App.swift  # App entry point
│       │   ├── Views/            # UI views
│       │   ├── Services/         # API services
│       │   └── Models/           # Data models
│       └── Spotim8app/           # Xcode project
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
