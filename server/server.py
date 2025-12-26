#!/usr/bin/env python3
"""
Simple HTTP server for iOS app to trigger sync automation and static analysis.

Run this server on your Mac/computer, then connect from your iPhone on the same network.

Usage:
    python server/server.py

The server will run on http://0.0.0.0:5000 (accessible from your iPhone on the same network)
"""

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from datetime import datetime

# Try to import flask, with helpful error message if missing
try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
except ImportError as e:
    print("=" * 60)
    print("ERROR: Missing required packages")
    print("=" * 60)
    print(f"Missing: {e.name}")
    print("\nPlease install dependencies:")
    print("  pip install flask flask-cors")
    print("\nOr use the project's virtual environment:")
    print("  source venv/bin/activate")
    print("  pip install flask flask-cors")
    print("=" * 60)
    sys.exit(1)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = Flask(__name__)
CORS(app)  # Allow requests from iOS app

# Global state for running tasks
running_tasks = {}
task_results = {}


def run_sync_task(task_id: str, skip_sync: bool = False, sync_only: bool = False, all_months: bool = False):
    """Run sync automation in background thread."""
    try:
        running_tasks[task_id] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "output": []
        }
        
        # Build command
        venv_python = None
        if (PROJECT_ROOT / "venv" / "bin" / "python").exists():
            venv_python = str(PROJECT_ROOT / "venv" / "bin" / "python")
        elif (PROJECT_ROOT / ".venv" / "bin" / "python").exists():
            venv_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
        else:
            venv_python = sys.executable
        
        cmd = [venv_python, str(PROJECT_ROOT / "scripts" / "sync.py")]
        if skip_sync:
            cmd.append("--skip-sync")
        if sync_only:
            cmd.append("--sync-only")
        if all_months:
            cmd.append("--all-months")
        
        # Run command and capture output
        process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        output_lines = []
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                running_tasks[task_id]["output"].append(line)
        
        return_code = process.wait()
        
        running_tasks[task_id]["status"] = "completed" if return_code == 0 else "failed"
        running_tasks[task_id]["return_code"] = return_code
        running_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        running_tasks[task_id]["output"] = output_lines
        
        # Move to results
        task_results[task_id] = running_tasks[task_id].copy()
        
    except Exception as e:
        running_tasks[task_id]["status"] = "error"
        running_tasks[task_id]["error"] = str(e)
        running_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        task_results[task_id] = running_tasks[task_id].copy()


def run_analysis_task(task_id: str):
    """Run static analysis in background thread."""
    started_at = datetime.now().isoformat()
    try:
        running_tasks[task_id] = {
            "status": "running",
            "started_at": started_at,
            "output": []
        }
        
        # Import analysis module
        from spotim8.analysis import LibraryAnalyzer
        
        data_dir = PROJECT_ROOT / "data"
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")
        
        analyzer = LibraryAnalyzer(data_dir).load()
        
        # Get stats
        stats = analyzer.stats()
        
        # Get monthly playlists
        monthly_playlists = analyzer.get_monthly_playlist_names()
        
        # Get followed playlists count
        followed = analyzer.get_followed_playlists()
        
        result = {
            "status": "completed",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "stats": {
                "total_tracks": int(stats.get("total_tracks", 0)),
                "total_artists": int(stats.get("total_artists", 0)),
                "total_playlists": int(stats.get("total_playlists", 0)),
                "total_hours": round(stats.get("total_hours", 0), 2),
                "avg_popularity": round(stats.get("avg_popularity", 0), 2),
            },
            "monthly_playlists_count": len(monthly_playlists),
            "followed_playlists_count": len(followed),
            "output": [f"Analysis complete: {stats.get('total_playlists', 0)} playlists, {stats.get('total_tracks', 0):,} tracks"]
        }
        
        running_tasks[task_id] = result
        task_results[task_id] = result.copy()
        
    except Exception as e:
        running_tasks[task_id] = {
            "status": "error",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "error": str(e),
            "output": [f"Error: {str(e)}"]
        }
        task_results[task_id] = running_tasks[task_id].copy()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "project_root": str(PROJECT_ROOT)})


@app.route("/sync", methods=["POST"])
def trigger_sync():
    """Trigger sync automation."""
    data = request.get_json() or {}
    skip_sync = data.get("skip_sync", False)
    sync_only = data.get("sync_only", False)
    all_months = data.get("all_months", False)
    
    task_id = f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Start background thread
    thread = threading.Thread(
        target=run_sync_task,
        args=(task_id, skip_sync, sync_only, all_months)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "task_id": task_id,
        "status": "started",
        "message": "Sync automation started"
    })


@app.route("/analysis", methods=["POST"])
def trigger_analysis():
    """Trigger static analysis."""
    task_id = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Start background thread
    thread = threading.Thread(target=run_analysis_task, args=(task_id,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "task_id": task_id,
        "status": "started",
        "message": "Static analysis started"
    })


@app.route("/status/<task_id>", methods=["GET"])
def get_status(task_id):
    """Get status of a running or completed task."""
    if task_id in running_tasks:
        return jsonify(running_tasks[task_id])
    elif task_id in task_results:
        return jsonify(task_results[task_id])
    else:
        return jsonify({"error": "Task not found"}), 404


@app.route("/tasks", methods=["GET"])
def list_tasks():
    """List all tasks."""
    all_tasks = {**running_tasks, **task_results}
    return jsonify({
        "tasks": all_tasks,
        "count": len(all_tasks)
    })


@app.route("/library/stats", methods=["GET"])
def get_library_stats():
    """Get library statistics."""
    try:
        from spotim8.analysis import LibraryAnalyzer
        
        data_dir = PROJECT_ROOT / "data"
        if not data_dir.exists():
            return jsonify({"error": "Data directory not found"}), 404
        
        analyzer = LibraryAnalyzer(data_dir).load()
        stats = analyzer.stats()
        
        return jsonify({
            "total_tracks": int(stats.get("total_tracks", 0)),
            "total_artists": int(stats.get("total_artists", 0)),
            "total_playlists": int(stats.get("total_playlists", 0)),
            "total_hours": round(stats.get("total_hours", 0), 2),
            "avg_popularity": round(stats.get("avg_popularity", 0), 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/library/playlists", methods=["GET"])
def get_playlists():
    """Get list of playlists."""
    try:
        import pandas as pd
        
        data_dir = PROJECT_ROOT / "data"
        playlists_path = data_dir / "playlists.parquet"
        
        if not playlists_path.exists():
            return jsonify({"error": "Playlists data not found"}), 404
        
        df = pd.read_parquet(playlists_path)
        
        # Filter to owned playlists only
        owned = df[df.get("is_owned", False) == True].copy()
        
        # Convert to list of dicts
        playlists = []
        for _, row in owned.iterrows():
            playlists.append({
                "playlist_id": str(row.get("playlist_id", "")),
                "name": str(row.get("name", "Unknown")),
                "track_count": int(row.get("track_count", 0)),
                "is_owned": bool(row.get("is_owned", False)),
            })
        
        # Sort by name
        playlists.sort(key=lambda x: x["name"])
        
        return jsonify({"playlists": playlists, "count": len(playlists)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/library/playlist/<playlist_id>/tracks", methods=["GET"])
def get_playlist_tracks(playlist_id):
    """Get tracks in a playlist."""
    try:
        import pandas as pd
        
        data_dir = PROJECT_ROOT / "data"
        playlist_tracks_path = data_dir / "playlist_tracks.parquet"
        tracks_path = data_dir / "tracks.parquet"
        
        if not playlist_tracks_path.exists() or not tracks_path.exists():
            return jsonify({"error": "Data not found"}), 404
        
        playlist_tracks = pd.read_parquet(playlist_tracks_path)
        tracks = pd.read_parquet(tracks_path)
        
        # Get tracks for this playlist
        playlist_tracks_filtered = playlist_tracks[
            playlist_tracks["playlist_id"].astype(str) == str(playlist_id)
        ]
        
        if playlist_tracks_filtered.empty:
            return jsonify({"tracks": [], "count": 0})
        
        # Merge with track details
        merged = playlist_tracks_filtered.merge(
            tracks,
            on="track_id",
            how="left"
        )
        
        # Convert to list
        track_list = []
        for _, row in merged.iterrows():
            track_list.append({
                "track_id": str(row.get("track_id", "")),
                "name": str(row.get("name", "Unknown")),
                "artist": str(row.get("artist_name", "Unknown")),
                "duration_ms": int(row.get("duration_ms", 0)),
                "popularity": int(row.get("popularity", 0)),
            })
        
        return jsonify({"tracks": track_list, "count": len(track_list)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/library/artists", methods=["GET"])
def get_artists():
    """Get list of artists."""
    try:
        import pandas as pd
        
        data_dir = PROJECT_ROOT / "data"
        artists_path = data_dir / "artists.parquet"
        
        if not artists_path.exists():
            return jsonify({"error": "Artists data not found"}), 404
        
        df = pd.read_parquet(artists_path)
        
        # Convert to list
        artists = []
        for _, row in df.iterrows():
            artists.append({
                "artist_id": str(row.get("artist_id", "")),
                "name": str(row.get("name", "Unknown")),
                "popularity": int(row.get("popularity", 0)),
                "genres": row.get("genres", []),
            })
        
        # Sort by name
        artists.sort(key=lambda x: x["name"])
        
        return jsonify({"artists": artists, "count": len(artists)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import socket
    import sys
    
    # Get port from environment variable or use 5001 (5000 is often used by AirPlay on macOS)
    port = int(os.environ.get("SPOTIM8_SERVER_PORT", 5001))
    
    # Find local IP address
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        # Fallback: try to get IP from network interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except:
            local_ip = "127.0.0.1"
        finally:
            s.close()
    
    print("=" * 60)
    print("Spotim8 iOS Server")
    print("=" * 60)
    print(f"Server starting on http://0.0.0.0:{port}")
    print(f"Local IP: http://{local_ip}:{port}")
    print(f"Project root: {PROJECT_ROOT}")
    print("=" * 60)
    print("\nConnect your iPhone to the same network and use the local IP address.")
    print("Press Ctrl+C to stop the server.\n")
    
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n❌ ERROR: Port {port} is already in use.")
            print(f"\nTry one of these solutions:")
            print(f"1. Use a different port: SPOTIM8_SERVER_PORT=5002 python server/server.py")
            print(f"2. On macOS, disable AirPlay Receiver:")
            print(f"   System Settings → General → AirDrop & Handoff → AirPlay Receiver → Off")
            print(f"3. Find what's using the port: lsof -i :{port}")
            sys.exit(1)
        else:
            raise

