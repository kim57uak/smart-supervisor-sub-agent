#!/bin/bash

# start.sh
# FastAPI Server Start Script with 4 Uvicorn Workers

PORT=8000
WORKERS=4

echo "======================================"
echo "Starting Smart Supervisor Sub-Agent..."
echo "======================================"

# Ensure virtual environment is activated
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Virtual environment (.venv) not found! Please create one and install dependencies."
    exit 1
fi

# Run Uvicorn with 4 workers in the background
# We save the PID to a file so we can easily stop it later
nohup uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers $WORKERS > uvicorn.log 2>&1 &
PID=$!

echo $PID > server.pid

echo "Server started with PID: $PID"
echo "Listening on http://localhost:$PORT"
echo "Logs are being written to uvicorn.log"
echo ""
echo "To stop the server, run: ./stop.sh"
