#!/bin/bash
# Start the iOS server for Spotim8

cd "$(dirname "$0")/.."

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "Warning: No virtual environment found. Using system Python."
    echo "Consider creating one: python3 -m venv venv"
fi

# Install server dependencies if needed
echo "Checking server dependencies..."
python -c "import flask, flask_cors" 2>/dev/null || {
    echo "Installing flask and flask-cors..."
    pip install flask flask-cors
}

# Start the server
echo "Starting server..."
python server/server.py

