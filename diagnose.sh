#!/bin/bash

# KleinanzeigenScraper Diagnostic Tool
# This script helps diagnose issues with the KleinanzeigenScraper installation

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}KleinanzeigenScraper Diagnostic Tool${NC}"
echo -e "${BLUE}====================================${NC}"

# Get the current directory
INSTALL_DIR=$(pwd)
echo -e "Current directory: ${INSTALL_DIR}"

# Check system resources
echo -e "\n${YELLOW}System Resources:${NC}"
echo -e "CPU Usage:"
top -bn1 | head -n 5
echo -e "\nMemory Usage:"
free -h
echo -e "\nDisk Space:"
df -h | grep -E "Filesystem|/$"

# Check if required files exist
echo -e "\n${YELLOW}Checking Required Files:${NC}"
required_files=("server.js" "main.py" "scraper.py" "process_listings.py" "config.py" "requirements.txt" "package.json")
for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file exists${NC}"
    else
        echo -e "${RED}✗ $file does not exist${NC}"
    fi
done

# Check virtual environment
echo -e "\n${YELLOW}Checking Python Virtual Environment:${NC}"
if [ -d "kleinanzeigenScraper" ]; then
    echo -e "${GREEN}✓ Virtual environment directory exists${NC}"
    if [ -f "kleinanzeigenScraper/bin/activate" ]; then
        echo -e "${GREEN}✓ Activation script exists${NC}"
        
        # Check Python version in venv
        if [ -f "kleinanzeigenScraper/bin/python" ]; then
            VENV_PYTHON_VERSION=$(kleinanzeigenScraper/bin/python --version 2>&1)
            echo -e "${GREEN}✓ Virtual environment Python: $VENV_PYTHON_VERSION${NC}"
        else
            echo -e "${RED}✗ Python executable not found in virtual environment${NC}"
        fi
    else
        echo -e "${RED}✗ Activation script does not exist${NC}"
    fi
else
    echo -e "${RED}✗ Virtual environment directory does not exist${NC}"
fi

# Check Node.js and npm
echo -e "\n${YELLOW}Checking Node.js and npm:${NC}"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✓ Node.js is installed: $NODE_VERSION${NC}"
else
    echo -e "${RED}✗ Node.js is not installed${NC}"
fi

if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    echo -e "${GREEN}✓ npm is installed: $NPM_VERSION${NC}"
else
    echo -e "${RED}✗ npm is not installed${NC}"
fi

# Check if node_modules exists
if [ -d "node_modules" ]; then
    echo -e "${GREEN}✓ node_modules directory exists${NC}"
    NODE_MODULES_COUNT=$(find node_modules -type d | wc -l)
    echo -e "${GREEN}  Found approximately $NODE_MODULES_COUNT modules${NC}"
else
    echo -e "${RED}✗ node_modules directory does not exist${NC}"
fi

# Check network and port
echo -e "\n${YELLOW}Checking Network and Port:${NC}"
echo -e "Checking if port 3030 is in use:"
if command -v lsof &> /dev/null; then
    PORT_CHECK=$(lsof -i :3030 2>/dev/null)
    if [ -n "$PORT_CHECK" ]; then
        echo -e "${RED}Port 3030 is already in use:${NC}"
        echo "$PORT_CHECK"
    else
        echo -e "${GREEN}✓ Port 3030 is available${NC}"
    fi
else
    echo -e "${YELLOW}lsof command not available, skipping port check${NC}"
    
    # Alternative check using netstat
    if command -v netstat &> /dev/null; then
        PORT_CHECK=$(netstat -tuln | grep ":3030 ")
        if [ -n "$PORT_CHECK" ]; then
            echo -e "${RED}Port 3030 is already in use:${NC}"
            echo "$PORT_CHECK"
        else
            echo -e "${GREEN}✓ Port 3030 is available${NC}"
        fi
    fi
fi

# Check if the service is installed
echo -e "\n${YELLOW}Checking Service Status:${NC}"
if [ -f "/etc/systemd/system/kleinanzeigen-scraper.service" ]; then
    echo -e "${GREEN}✓ Service is installed${NC}"
    
    # Check if service is enabled
    if systemctl is-enabled kleinanzeigen-scraper.service &> /dev/null; then
        echo -e "${GREEN}✓ Service is enabled${NC}"
    else
        echo -e "${YELLOW}⚠ Service is not enabled${NC}"
    fi
    
    # Check if service is active
    if systemctl is-active kleinanzeigen-scraper.service &> /dev/null; then
        echo -e "${GREEN}✓ Service is active${NC}"
    else
        echo -e "${RED}✗ Service is not active${NC}"
    fi
    
    # Show service status
    echo -e "\n${YELLOW}Service Status:${NC}"
    systemctl status kleinanzeigen-scraper.service --no-pager
    
    # Show recent logs
    echo -e "\n${YELLOW}Recent Service Logs:${NC}"
    journalctl -u kleinanzeigen-scraper.service -n 20 --no-pager
else
    echo -e "${YELLOW}⚠ Service is not installed${NC}"
fi

# Test server manually
echo -e "\n${YELLOW}Testing Server Manually:${NC}"
echo -e "Starting server in test mode..."

# Source the virtual environment and start the server in the background
(source kleinanzeigenScraper/bin/activate 2>/dev/null && node server.js > server_test.log 2>&1) &
SERVER_PID=$!

# Wait a few seconds for the server to start
sleep 5

# Check if the server is running
if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}✓ Server process started successfully (PID: $SERVER_PID)${NC}"
    
    # Check if the server is accessible
    if curl -s http://localhost:3030 > /dev/null; then
        echo -e "${GREEN}✓ Server is accessible at http://localhost:3030${NC}"
        CURL_OUTPUT=$(curl -s http://localhost:3030 | head -n 20)
        echo -e "${GREEN}First 20 lines of server response:${NC}"
        echo "$CURL_OUTPUT"
    else
        echo -e "${RED}✗ Server process is running but not accessible at http://localhost:3030${NC}"
        echo -e "${YELLOW}Server Log:${NC}"
        cat server_test.log
    fi
else
    echo -e "${RED}✗ Server process failed to start${NC}"
    echo -e "${YELLOW}Server Log:${NC}"
    cat server_test.log
fi

# Kill the test server
kill $SERVER_PID 2>/dev/null || true

# Clean up
rm server_test.log 2>/dev/null || true

echo -e "\n${BLUE}Diagnostic Complete${NC}"
echo -e "${YELLOW}If you're experiencing issues, please check the logs and error messages above.${NC}"
echo -e "${YELLOW}You can also try running the server manually with:${NC}"
echo -e "${GREEN}source kleinanzeigenScraper/bin/activate && node server.js${NC}" 