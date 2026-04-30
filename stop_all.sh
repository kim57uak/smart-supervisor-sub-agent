#!/bin/bash

# stop_all.sh
# Integrated stop script for Sub-Agent and Supervisor-Agent

echo "======================================"
echo "Stopping All Agents (Sub & Supervisor)"
echo "======================================"

# 1. Stop Supervisor-Agent
echo ">>> [1/2] Stopping Supervisor-Agent..."
(cd src/supervisor-agent && ./stop.sh)

echo ""

# 2. Stop Sub-Agent
echo ">>> [2/2] Stopping Sub-Agent..."
(cd src/sub-agent && ./stop.sh)

echo ""
echo "======================================"
echo "All agents have been stopped."
echo "======================================"
