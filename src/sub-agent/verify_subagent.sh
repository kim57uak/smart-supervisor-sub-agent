#!/bin/bash

# =================================================================
# Sub-agent Regression Test Script
# =================================================================

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "🚀 Starting Sub-agent Regression Tests..."

# 1. 환경 확인
if [ ! -d "../../.venv" ]; then
    echo -e "${RED}❌ Virtual environment (.venv) not found at root.${NC}"
    exit 1
fi

VENV_PYTHON="../../.venv/bin/python"
VENV_PYTEST="../../.venv/bin/pytest"

# 2. 컴파일 테스트 (Syntax Check)
echo "🔍 Step 1: Compiling Python files..."
$VENV_PYTHON -m compileall app main.py worker.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Compilation successful.${NC}"
else
    echo -e "${RED}❌ Compilation failed.${NC}"
    exit 1
fi

# 3. 통합 테스트 실행 (Logic Check)
echo "🧪 Step 2: Running Integration Tests via Pytest..."
export PYTHONPATH=$PYTHONPATH:.
$VENV_PYTEST tests/integration_test.py -v
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed.${NC}"
else
    echo -e "${RED}❌ Some tests failed.${NC}"
    exit 1
fi

echo -e "\n${GREEN}===========================================${NC}"
echo -e "${GREEN}🎉 Sub-agent is Enterprise Ready!${NC}"
echo -e "${GREEN}===========================================${NC}"
