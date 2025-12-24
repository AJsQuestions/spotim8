#!/usr/bin/env python3
"""
Setup Local Development Environment

This script sets up a virtual environment and guides you through
configuring your Spotify API credentials.

Usage:
    python scripts/setup_local.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

os.chdir(PROJECT_ROOT)

def run_command(cmd, check=True):
    """Run a shell command."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: Command failed: {cmd}")
        print(result.stderr)
        sys.exit(1)
    return result

def main():
    print("=" * 60)
    print("Spotim8 Local Setup")
    print("=" * 60)
    print()

    # Step 1: Create virtual environment
    print("📦 Step 1: Setting up virtual environment...")
    venv_dir = PROJECT_ROOT / "venv"
    
    if venv_dir.exists() or (PROJECT_ROOT / ".venv").exists():
        print("   ✅ Virtual environment already exists")
        if (PROJECT_ROOT / ".venv").exists():
            venv_dir = PROJECT_ROOT / ".venv"
    else:
        print("   Creating virtual environment...")
        run_command(f"python3 -m venv {venv_dir}")
        print("   ✅ Virtual environment created")

    # Determine Python executable
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
        venv_pip = venv_dir / "Scripts" / "pip.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
        venv_pip = venv_dir / "bin" / "pip"

    # Step 2: Install dependencies
    print()
    print("📦 Step 2: Installing dependencies...")
    run_command(f'"{venv_python}" -m pip install --upgrade pip setuptools wheel')
    run_command(f'"{venv_pip}" install -e .')
    print("   ✅ Dependencies installed")

    # Step 3: Check for .env file
    print()
    print("🔑 Step 3: Checking for API credentials...")
    env_path = PROJECT_ROOT / ".env"
    
    if env_path.exists():
        print("   ✅ .env file found")
        print()
        print("   Current .env contents:")
        print("   ────────────────────────")
        with open(env_path) as f:
            for line in f:
                if any(key in line for key in ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", 
                                                "SPOTIPY_REDIRECT_URI", "SPOTIPY_REFRESH_TOKEN", 
                                                "PLAYLIST_"]):
                    print(f"   {line.rstrip()}")
        print("   ────────────────────────")
        print()
        response = input("   Do you want to update the .env file? (y/n) ").strip().lower()
        update_env = response == 'y'
    else:
        print("   ⚠️  No .env file found")
        update_env = True

    # Step 4: Guide user through API setup
    if update_env:
        print()
        print("🔑 Step 4: Setting up Spotify API credentials")
        print()
        print("   To get your Spotify API credentials:")
        print("   1. Go to https://developer.spotify.com/dashboard")
        print("   2. Log in with your Spotify account")
        print("   3. Click 'Create app'")
        print("   4. Fill in app details (name, description, etc.)")
        print("   5. Add redirect URI: http://127.0.0.1:8888/callback")
        print("   6. Click 'Save'")
        print("   7. Copy your 'Client ID' and 'Client Secret'")
        print()

        # Create or update .env file
        if not env_path.exists():
            example_path = PROJECT_ROOT / "env.example"
            if example_path.exists():
                shutil.copy(example_path, env_path)
                print("   ✅ Created .env file from env.example")
            else:
                # Create basic .env file
                with open(env_path, 'w') as f:
                    f.write("# Spotify API Credentials\n")
                    f.write("SPOTIPY_CLIENT_ID=your_client_id_here\n")
                    f.write("SPOTIPY_CLIENT_SECRET=your_client_secret_here\n")
                    f.write("SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback\n")
                    f.write("SPOTIPY_REFRESH_TOKEN=your_refresh_token_here\n")
                    f.write("PLAYLIST_OWNER_NAME=AJ\n")
                    f.write("PLAYLIST_PREFIX=Finds\n")
                print("   ✅ Created .env file")

        print()
        print("   Enter your credentials (press Enter to skip updating a value):")
        print()

        # Read existing .env file
        env_vars = {}
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()

        # Get Client ID
        client_id = input("   Spotify Client ID: ").strip()
        if client_id:
            env_vars["SPOTIPY_CLIENT_ID"] = client_id

        # Get Client Secret
        client_secret = input("   Spotify Client Secret: ").strip()
        if client_secret:
            env_vars["SPOTIPY_CLIENT_SECRET"] = client_secret

        # Optional: Playlist owner name
        owner_name = input("   Playlist Owner Name (optional, press Enter to skip): ").strip()
        if owner_name:
            env_vars["PLAYLIST_OWNER_NAME"] = owner_name

        # Optional: Playlist prefix
        prefix = input("   Playlist Prefix (optional, default: Finds, press Enter to skip): ").strip()
        if prefix:
            env_vars["PLAYLIST_PREFIX"] = prefix

        # Write .env file
        with open(env_path, 'w') as f:
            f.write("# Spotify API Credentials\n")
            f.write("# Get these from https://developer.spotify.com/dashboard\n")
            f.write(f"SPOTIPY_CLIENT_ID={env_vars.get('SPOTIPY_CLIENT_ID', 'your_client_id_here')}\n")
            f.write(f"SPOTIPY_CLIENT_SECRET={env_vars.get('SPOTIPY_CLIENT_SECRET', 'your_client_secret_here')}\n")
            f.write(f"SPOTIPY_REDIRECT_URI={env_vars.get('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')}\n")
            f.write("\n")
            f.write("# For automated/local runs without browser (get via scripts/get_refresh_token.py)\n")
            f.write(f"SPOTIPY_REFRESH_TOKEN={env_vars.get('SPOTIPY_REFRESH_TOKEN', 'your_refresh_token_here')}\n")
            f.write("\n")
            f.write("# Optional: Customize playlist naming\n")
            f.write(f"PLAYLIST_OWNER_NAME={env_vars.get('PLAYLIST_OWNER_NAME', 'AJ')}\n")
            f.write(f"PLAYLIST_PREFIX={env_vars.get('PLAYLIST_PREFIX', 'Finds')}\n")

        print()
        print("   ✅ .env file updated")
        print()
        print("   🔐 To get a refresh token for automated runs (optional but recommended):")
        print("      python scripts/get_refresh_token.py")
        print("      Then add SPOTIPY_REFRESH_TOKEN to your .env file")

    print()
    print("=" * 60)
    print("✅ Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Activate the virtual environment:")
    if sys.platform == "win32":
        print("     venv\\Scripts\\activate")
    else:
        print("     source venv/bin/activate")
    print()
    print("  2. (Optional) Get refresh token for automated runs:")
    print("     python scripts/get_refresh_token.py")
    print()
    print("  3. Test the sync:")
    print("     python scripts/run_sync_local.py")
    print()
    print("  4. The cron job is already set up to run daily at 2:00 AM")
    print()

if __name__ == "__main__":
    main()

