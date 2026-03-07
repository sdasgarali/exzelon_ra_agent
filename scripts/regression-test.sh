#!/usr/bin/env bash
# Regression Test Runner — runs backend and frontend tests with coverage
# Usage:
#   bash scripts/regression-test.sh                 # full suite
#   bash scripts/regression-test.sh --backend-only  # backend only
#   bash scripts/regression-test.sh --frontend-only # frontend only
#   bash scripts/regression-test.sh --quick         # unit tests only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BACKEND_ONLY=false
FRONTEND_ONLY=false
QUICK=false
BACKEND_EXIT=0
FRONTEND_EXIT=0

# Parse flags
for arg in "$@"; do
  case $arg in
    --backend-only) BACKEND_ONLY=true ;;
    --frontend-only) FRONTEND_ONLY=true ;;
    --quick) QUICK=true ;;
    *) echo -e "${RED}Unknown flag: $arg${NC}"; exit 1 ;;
  esac
done

START_TIME=$(date +%s)

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Regression Test Runner${NC}"
echo -e "${BLUE}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ---- Backend Tests ----
if [ "$FRONTEND_ONLY" = false ]; then
  echo -e "${YELLOW}--- Backend Tests ---${NC}"
  cd "$PROJECT_ROOT/backend"

  PYTEST_ARGS="--cov=app --cov-report=term-missing --cov-report=html:htmlcov"

  if [ "$QUICK" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -m unit"
    echo -e "Running: ${BLUE}pytest $PYTEST_ARGS${NC} (unit tests only)"
  else
    echo -e "Running: ${BLUE}pytest $PYTEST_ARGS${NC}"
  fi

  if pytest $PYTEST_ARGS; then
    echo -e "${GREEN}Backend tests: PASSED${NC}"
  else
    BACKEND_EXIT=$?
    echo -e "${RED}Backend tests: FAILED (exit code $BACKEND_EXIT)${NC}"
  fi
  echo ""
fi

# ---- Frontend Tests ----
if [ "$BACKEND_ONLY" = false ]; then
  echo -e "${YELLOW}--- Frontend Tests ---${NC}"
  cd "$PROJECT_ROOT/frontend"

  JEST_ARGS="--coverage --ci"

  echo -e "Running: ${BLUE}npx jest $JEST_ARGS${NC}"

  if npx jest $JEST_ARGS; then
    echo -e "${GREEN}Frontend tests: PASSED${NC}"
  else
    FRONTEND_EXIT=$?
    echo -e "${RED}Frontend tests: FAILED (exit code $FRONTEND_EXIT)${NC}"
  fi
  echo ""
fi

# ---- Summary ----
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Summary${NC}"
echo -e "${BLUE}========================================${NC}"

if [ "$FRONTEND_ONLY" = false ]; then
  if [ $BACKEND_EXIT -eq 0 ]; then
    echo -e "  Backend:  ${GREEN}PASSED${NC}"
  else
    echo -e "  Backend:  ${RED}FAILED${NC}"
  fi
fi

if [ "$BACKEND_ONLY" = false ]; then
  if [ $FRONTEND_EXIT -eq 0 ]; then
    echo -e "  Frontend: ${GREEN}PASSED${NC}"
  else
    echo -e "  Frontend: ${RED}FAILED${NC}"
  fi
fi

echo -e "  Duration: ${DURATION}s"
echo -e "${BLUE}========================================${NC}"

# Coverage report locations
if [ "$FRONTEND_ONLY" = false ]; then
  echo -e "  Backend coverage:  ${BLUE}backend/htmlcov/index.html${NC}"
fi
if [ "$BACKEND_ONLY" = false ]; then
  echo -e "  Frontend coverage: ${BLUE}frontend/coverage/lcov-report/index.html${NC}"
fi

# Exit with failure if any suite failed
if [ $BACKEND_EXIT -ne 0 ] || [ $FRONTEND_EXIT -ne 0 ]; then
  exit 1
fi

exit 0
