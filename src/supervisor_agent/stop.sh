#!/bin/bash

# stop.sh
# Stop the FastAPI Server

echo "======================================"
echo "Stopping Smart Supervisor Sub-Agent..."
echo "======================================"

# Stop API Server
if [ -f "server.pid" ]; then
    PID=$(cat server.pid)
    echo "Stopping API Server (PID: $PID)..."
    kill $PID 2>/dev/null
    rm server.pid
fi

# Stop Background Workers
if [ -f "worker.pid" ]; then
    echo "Stopping Background Workers..."
    while read W_PID; do
        echo "Killing worker PID: $W_PID"
        kill $W_PID 2>/dev/null
    done < worker.pid
    rm worker.pid
fi

# Fallback: Clean up any remaining processes
echo "Cleaning up any remaining processes..."

# 1. Kill by Port (Most reliable)
PORT=8000
echo "Cleaning up processes on port $PORT..."
lsof -ti :$PORT | xargs kill -9 2>/dev/null

# 2. Kill by Pattern
pkill -9 -f "uvicorn main:app.*--port $PORT"
pkill -9 -f "uvicorn main:app"
pkill -9 -f "python worker.py"

echo "All processes stopped."
