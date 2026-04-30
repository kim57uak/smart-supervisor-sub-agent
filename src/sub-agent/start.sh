#!/bin/bash

# start.sh
# FastAPI Server Start Script for Sub-Agent

PORT=8082 # Synchronized with Supervisor
API_WORKERS=1
BG_WORKERS=2

echo "======================================"
echo "Starting Smart Sub-Agent..."
echo "Config: API Workers ($API_WORKERS), BG Workers ($BG_WORKERS)"
echo "======================================"

# Ensure virtual environment is activated
if [ -d "../../.venv" ]; then
    source "../../.venv/bin/activate"
else
    echo "Root virtual environment (../../.venv) not found! Please create one at the project root."
    exit 1
fi

# 1. Run API Server
# Ensure source independence by setting PYTHONPATH to current directory
export PYTHONPATH=.
nohup uvicorn main:app --host 0.0.0.0 --port $PORT --workers $API_WORKERS > uvicorn.log 2>&1 &
PID=$!
echo $PID > server.pid
echo "API Server master started with PID: $PID"

# 2. Run Standalone Background Workers
echo "Starting $BG_WORKERS standalone background workers..."
> worker.pid # Initialize/Clear PID file

for i in $(seq 1 $BG_WORKERS)
do
    nohup ../../.venv/bin/python3 worker.py > worker_$i.log 2>&1 &
    echo $! >> worker.pid
done

echo "Successfully started all processes."
echo "Listening on http://localhost:$PORT"
echo "Logs: uvicorn.log, worker_1.log ... worker_$BG_WORKERS.log"
echo ""
echo "To stop everything, run: ./stop.sh"
