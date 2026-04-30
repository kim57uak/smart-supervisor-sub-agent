#!/bin/bash

# start_all.sh
# Integrated start script for Sub-Agent and Supervisor-Agent

echo "======================================"
echo "Starting All Agents (Sub & Supervisor)"
echo "======================================"

# 1. Start Sub-Agent (Port 8082)
echo ">>> [1/2] Starting Sub-Agent..."
(cd src/sub-agent && ./start.sh)

echo ""

# 2. Start Supervisor-Agent (Port 8000)
echo ">>> [2/2] Starting Supervisor-Agent..."
(cd src/supervisor-agent && ./start.sh)

echo ""
echo "======================================"
echo "All agents have been initiated."
# Rationale (Why): Synchronized with src/sub-agent/start.sh (8082) 
# and supervisor's routing config.
echo "Sub-Agent: http://localhost:8082"
echo "Supervisor-Agent: http://localhost:8000"
echo "======================================"
