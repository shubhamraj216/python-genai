#!/bin/bash

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Image Generation API - Startup Script${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found${NC}"
    echo -e "${YELLOW}   Creating .env from .env.example...${NC}"
    
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}✓ Created .env file from .env.example${NC}"
        echo -e "${YELLOW}   Please edit .env and add your API keys before continuing${NC}"
        echo ""
        exit 1
    else
        echo -e "${RED}✗ .env.example not found. Please create a .env file manually${NC}"
        echo ""
        exit 1
    fi
fi

echo -e "${GREEN}✓ Found .env file${NC}"

# Check if virtual environment exists
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found${NC}"
    echo -e "${BLUE}   Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
if [ -d "venv" ]; then
    echo -e "${BLUE}   Activating virtual environment (venv)...${NC}"
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo -e "${BLUE}   Activating virtual environment (.venv)...${NC}"
    source .venv/bin/activate
fi

echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Check if dependencies are installed
echo -e "${BLUE}   Checking dependencies...${NC}"
if ! python -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Dependencies not installed${NC}"
    echo -e "${BLUE}   Installing dependencies from requirements.txt...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Dependencies already installed${NC}"
fi

# Create necessary directories
echo -e "${BLUE}   Creating necessary directories...${NC}"
mkdir -p assets/generated
mkdir -p assets/db
mkdir -p logs
echo -e "${GREEN}✓ Directories ready${NC}"

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}🚀 Starting FastAPI Application${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${BLUE}   Host: ${HOST:-0.0.0.0}${NC}"
echo -e "${BLUE}   Port: ${PORT:-8000}${NC}"
echo -e "${BLUE}   Model: ${GEMINI_MODEL:-gemini-2.5-flash-image-preview}${NC}"
echo ""
echo -e "${YELLOW}   Press Ctrl+C to stop the server${NC}"
echo ""

# Run the application
python app.py

