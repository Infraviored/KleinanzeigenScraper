#!/bin/bash

# Debug script for the KleinanzeigenScraper API Server

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}KleinanzeigenScraper API Server Debug Script${NC}"
echo -e "${BLUE}=========================================${NC}"

# Activate the virtual environment
source kleinanzeigenScraper/bin/activate

# Set the PYTHONPATH to include the project root
export PYTHONPATH=$(pwd)

# Run the API server with verbose output
echo -e "${YELLOW}Starting API server in debug mode...${NC}"
echo -e "${YELLOW}PYTHONPATH: ${PYTHONPATH}${NC}"
echo -e "${YELLOW}Current directory: $(pwd)${NC}"
echo -e "${YELLOW}Python executable: $(which python)${NC}"

# List all Python modules in the backend directory
echo -e "${YELLOW}Python modules in backend directory:${NC}"
ls -la backend/*.py

# Run the API server with verbose output
python -v backend/api_server.py

# Deactivate the virtual environment
deactivate 