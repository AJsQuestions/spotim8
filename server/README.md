# Spotim8 iOS Server

Simple HTTP server for the iOS app to trigger sync automation and static analysis.

## Setup

1. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate  # or .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   cd server
   pip install -r requirements.txt
   ```
   
   Or install from project root:
   ```bash
   pip install flask flask-cors
   ```

3. **Make sure your `.env` file is configured** in the project root.

4. **Run the server:**
   ```bash
   # From project root:
   source venv/bin/activate
   python server/server.py
   
   # Or use the convenience script:
   ./server/start_server.sh
   
   # Use a custom port if needed:
   SPOTIM8_SERVER_PORT=5002 python server/server.py
   ```

The server will display your local IP address and port. Use this in the iOS app settings (e.g., `http://192.168.1.252:5001`).

## Endpoints

- `GET /health` - Health check
- `POST /sync` - Trigger sync automation
  - Body: `{"skip_sync": false, "sync_only": false, "all_months": false}`
- `POST /analysis` - Trigger static analysis
- `GET /status/<task_id>` - Get status of a task
- `GET /tasks` - List all tasks

## Network Setup

1. Make sure your Mac/computer and iPhone are on the same Wi-Fi network
2. Find your Mac's local IP address (shown when server starts)
3. Enter this IP and port in the iOS app settings (e.g., `http://192.168.1.252:5001`)
4. The server runs on port 5001 by default (5000 is often used by AirPlay on macOS)

**Note:** If port 5001 is also in use, you can change it:
```bash
SPOTIM8_SERVER_PORT=5002 python server/server.py
```
Then update the iOS app settings with the new port.

## Security Note

This server is for personal use only. It has no authentication and should only be run on a trusted local network.

