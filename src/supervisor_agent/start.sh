#!/bin/bash

# start.sh
# FastAPI Server Start Script with 4 Uvicorn Workers

PORT=8000
PORT_SSL=8443
API_WORKERS=4
BG_WORKERS=4
SSL_CERT_DIR="certs"

echo "======================================"
echo "Starting Smart Supervisor Agent..."
echo "Config: API Workers ($API_WORKERS), BG Workers ($BG_WORKERS)"
echo "======================================"

# Ensure virtual environment is activated
if [ -d "../../.venv" ]; then
    source "../../.venv/bin/activate"
else
    echo "Root virtual environment (../../.venv) not found! Please create one at the project root."
    exit 1
fi

# 1a. Run HTTP API Server with 4 workers
export EMBEDDED_WORKER_ENABLED=false
export PYTHONPATH=.
nohup uvicorn main:app --host 0.0.0.0 --port $PORT --workers $API_WORKERS > uvicorn.log 2>&1 &
PID=$!
echo $PID > server.pid
echo "API Server (HTTP) master started with PID: $PID"

# 1b. Run HTTPS API Server with 1 worker
nohup uvicorn main:app --host 0.0.0.0 --port $PORT_SSL --workers 1 --ssl-keyfile $SSL_CERT_DIR/localhost-key.pem --ssl-certfile $SSL_CERT_DIR/localhost.pem > uvicorn_ssl.log 2>&1 &
PID_SSL=$!
echo $PID_SSL >> server.pid
echo "API Server (HTTPS) master started with PID: $PID_SSL"

# 2. Run Standalone Background Workers
echo "Starting $BG_WORKERS standalone background workers..."
> worker.pid # Initialize/Clear PID file

for i in $(seq 1 $BG_WORKERS)
do
    nohup ../../.venv/bin/python3 worker.py > worker_$i.log 2>&1 &
    echo $! >> worker.pid
done

echo "Successfully started all processes."
echo "HTTP:  http://localhost:$PORT"
echo "HTTPS: https://localhost:$PORT_SSL"
echo "Logs: uvicorn.log, uvicorn_ssl.log, worker_1.log ... worker_$BG_WORKERS.log"
echo ""
echo "To stop everything, run: ./stop.sh"

