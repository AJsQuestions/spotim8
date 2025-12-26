#!/usr/bin/env python3
"""
Get Spotify Refresh Token for Automated Runs

Run this script locally ONCE to get your refresh token,
then add it to your .env file for automated/local runs without browser.

Usage:
    python scripts/get_token.py
"""

import os
import sys
from pathlib import Path

# Add project to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("Installing spotipy...")
    os.system("pip install spotipy")
    from spotipy.oauth2 import SpotifyOAuth


def main():
    print("=" * 60)
    print("Spotify Refresh Token Generator")
    print("=" * 60)
    print()
    
    # Check for credentials
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    
    if not client_id:
        client_id = input("Enter your Spotify Client ID: ").strip()
    if not client_secret:
        client_secret = input("Enter your Spotify Client Secret: ").strip()
    
    print()
    print(f"Client ID: {client_id[:8]}...")
    print(f"Redirect URI: {redirect_uri}")
    print()
    
    # Create auth manager
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="user-library-read playlist-modify-private playlist-modify-public playlist-read-private",
        open_browser=True
    )
    
    print("Opening browser for authorization...")
    print("(If browser doesn't open, copy the URL below)")
    print()
    
    # Get the auth URL
    auth_url = auth.get_authorize_url()
    print(f"Auth URL: {auth_url}")
    print()
    
    # Try to open browser
    try:
        import webbrowser
        webbrowser.open(auth_url)
    except:
        pass
    
    print("After authorizing, you'll be redirected to a URL.")
    print("Paste the FULL redirect URL here:")
    print()
    
    response_url = input("Redirect URL: ").strip()
    
    # Extract code from URL
    code = auth.parse_response_code(response_url)
    
    if not code:
        print("ERROR: Could not extract authorization code from URL")
        sys.exit(1)
    
    # Get tokens
    token_info = auth.get_access_token(code)
    
    refresh_token = token_info.get("refresh_token")
    
    if not refresh_token:
        print("ERROR: No refresh token received")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("SUCCESS! Here's your refresh token:")
    print("=" * 60)
    print()
    print(refresh_token)
    print()
    print("=" * 60)
    print()
    print("Add this to your .env file:")
    print("  SPOTIPY_CLIENT_ID=" + client_id)
    print("  SPOTIPY_CLIENT_SECRET=" + client_secret)
    print("  SPOTIPY_REDIRECT_URI=" + redirect_uri)
    print("  SPOTIPY_REFRESH_TOKEN=" + refresh_token)
    print()
    print("Or export these environment variables before running the sync script.")
    print()


if __name__ == "__main__":
    main()

