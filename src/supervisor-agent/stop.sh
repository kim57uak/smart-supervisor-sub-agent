#!/bin/bash

# stop.sh
# Stop the FastAPI Server

echo "======================================"
echo "Stopping Smart Supervisor Sub-Agent..."
echo "======================================"

if [ -f "server.pid" ]; then
    PID=$(cat server.pid)
    
    if ps -p $PID > /dev/null; then
        echo "Killing Uvicorn master process ($PID)..."
        kill $PID
        
        # Wait a moment for graceful shutdown
        sleep 2
        
        # Check if it's still running, force kill if necessary
        if ps -p $PID > /dev/null; then
            echo "Process didn't stop, forcing kill..."
            kill -9 $PID
        fi
        
        echo "Server stopped successfully."
        rm server.pid
    else
        echo "Process $PID is not running."
        rm server.pid
        
        # Fallback: kill all uvicorn processes started in this directory
        echo "Attempting to kill any orphaned uvicorn processes..."
        pkill -f "uvicorn app.main:app"
    fi
else
    echo "server.pid not found. Looking for running uvicorn instances..."
    if pgrep -f "uvicorn app.main:app" > /dev/null; then
        echo "Found running instances. Terminating..."
        pkill -f "uvicorn app.main:app"
        echo "Server stopped."
    else
        echo "No running server found."
    fi
fi
