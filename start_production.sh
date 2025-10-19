#!/bin/bash

# Production startup script
# This script is for running the application in production mode

set -e  # Exit on error

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Production Startup - Python GenAI API${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ ERROR: .env file not found${NC}"
    echo -e "${YELLOW}   Production requires environment variables to be set${NC}"
    echo -e "${YELLOW}   Create .env file or set environment variables directly${NC}"
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

echo -e "${GREEN}✓ Environment variables loaded${NC}"

# Validate required environment variables
MISSING_VARS=()

if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "dev-secret-key-change-in-prod" ]; then
    MISSING_VARS+=("SECRET_KEY")
fi

if [ -z "$GEMINI_API_KEY" ]; then
    MISSING_VARS+=("GEMINI_API_KEY")
fi

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}❌ ERROR: Missing required environment variables:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo -e "${RED}   - $var${NC}"
    done
    exit 1
fi

echo -e "${GREEN}✓ Required environment variables validated${NC}"

# Create necessary directories
echo -e "${BLUE}   Creating directories...${NC}"
mkdir -p assets/generated/videos
mkdir -p assets/avatars
mkdir -p assets/db
mkdir -p logs
echo -e "${GREEN}✓ Directories ready${NC}"

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}🚀 Starting Production Server${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${BLUE}   Host: ${HOST:-0.0.0.0}${NC}"
echo -e "${BLUE}   Port: ${PORT:-8000}${NC}"
echo -e "${BLUE}   Workers: ${WORKERS:-1}${NC}"
echo ""
echo -e "${YELLOW}   Press Ctrl+C to stop the server${NC}"
echo ""

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠️  Warning: Not in a virtual environment${NC}"
    echo -e "${YELLOW}   Attempting to activate venv...${NC}"
    if [ -d "venv" ]; then
        source venv/bin/activate
        echo -e "${GREEN}✓ Virtual environment activated${NC}"
    elif [ -d ".venv" ]; then
        source .venv/bin/activate
        echo -e "${GREEN}✓ Virtual environment activated${NC}"
    else
        echo -e "${YELLOW}   No venv found, continuing anyway...${NC}"
    fi
fi

# Run with uvicorn in production mode
# - No reload (production)
# - Multiple workers (if specified)
# - Proper logging
exec uvicorn app:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-1}" \
    --log-level info \
    --no-access-log \
    --proxy-headers \
    --forwarded-allow-ips='*'

