#!/bin/bash

# KleinanzeigenScraper Python Backend Installer
# This script sets up the Python backend environment

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting KleinanzeigenScraper Python Backend installation...${NC}"

# Get the current directory
INSTALL_DIR=$(pwd)
echo -e "Installing in: ${INSTALL_DIR}"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3 and try again.${NC}"
    exit 1
fi

# Get Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "Found Python version: ${PYTHON_VERSION}"

# 1. Create Python virtual environment
echo -e "${YELLOW}Creating Python virtual environment...${NC}"

# Check if python3-venv is installed
if ! python3 -m venv --help &> /dev/null; then
    echo -e "${RED}The 'venv' module is not available. You need to install the python3-venv package.${NC}"
    echo -e "${YELLOW}On Debian/Ubuntu systems, run:${NC}"
    echo -e "${GREEN}sudo apt install python3-venv${NC}"
    echo -e "${YELLOW}After installing python3-venv, run this script again.${NC}"
    exit 1
fi

# Try to create the virtual environment
if ! python3 -m venv kleinanzeigenScraper; then
    echo -e "${RED}Failed to create virtual environment.${NC}"
    echo -e "${YELLOW}On Debian/Ubuntu systems, you might need to install:${NC}"
    echo -e "${GREEN}sudo apt install python3-venv${NC}"
    exit 1
fi

source kleinanzeigenScraper/bin/activate

# 2. Install Python requirements
echo -e "${YELLOW}Installing Python requirements...${NC}"
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install flask flask-cors psutil

# 3. Create data directory if it doesn't exist
if [ ! -d "data" ]; then
    echo -e "${YELLOW}Creating data directory...${NC}"
    mkdir -p data
fi

# 4. Create config.py if it doesn't exist
if [ ! -f "backend/config.py" ]; then
    echo -e "${YELLOW}Creating config.py from template...${NC}"
    cp backend/config_template.py backend/config.py
    echo -e "${YELLOW}Please edit backend/config.py to add your API key and other settings.${NC}"
fi

# 5. Set up systemd service
echo -e "${YELLOW}Setting up systemd service...${NC}"

# Get current username and UID
CURRENT_USER=$(whoami)
CURRENT_UID=$(id -u)

# Create systemd service file
cat > kleinanzeigen-scraper-api.service << EOL
[Unit]
Description=KleinanzeigenScraper Python API Server
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/kleinanzeigenScraper/bin/python ${INSTALL_DIR}/backend/api_server.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kleinanzeigen-scraper-api

[Install]
WantedBy=multi-user.target
EOL

# 6. Test the Python API server
echo -e "${YELLOW}Testing the Python API server...${NC}"
echo -e "${BLUE}Starting the server in test mode...${NC}"

# Run the server in the background
(source kleinanzeigenScraper/bin/activate && python backend/api_server.py > api_server_test.log 2>&1) &
SERVER_PID=$!

# Wait a few seconds for the server to start
sleep 5

# Check if the server is running
if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}Server process is running (PID: $SERVER_PID).${NC}"
    
    # Check if the server is accessible
    if curl -s http://localhost:3030/api/status > /dev/null; then
        echo -e "${GREEN}Server is accessible at http://localhost:3030/api/status${NC}"
        CURL_OUTPUT=$(curl -s http://localhost:3030/api/status)
        echo -e "${GREEN}Server status: ${CURL_OUTPUT}${NC}"
    else
        echo -e "${RED}Server process is running but not accessible at http://localhost:3030/api/status${NC}"
        echo -e "${YELLOW}Checking server logs:${NC}"
        tail -n 20 api_server_test.log
    fi
else
    echo -e "${RED}Server process failed to start.${NC}"
    echo -e "${YELLOW}Checking server logs:${NC}"
    cat api_server_test.log
fi

# Kill the test server
kill $SERVER_PID 2>/dev/null || true
rm api_server_test.log 2>/dev/null || true

echo -e "${YELLOW}Service file created. To install as a system service, run:${NC}"
echo -e "${GREEN}sudo cp kleinanzeigen-scraper-api.service /etc/systemd/system/${NC}"
echo -e "${GREEN}sudo systemctl daemon-reload${NC}"
echo -e "${GREEN}sudo systemctl enable kleinanzeigen-scraper-api.service${NC}"
echo -e "${GREEN}sudo systemctl start kleinanzeigen-scraper-api.service${NC}"

# Ask if user wants to install the service now
echo -e "${YELLOW}Do you want to install and start the service now? (y/n)${NC}"
read -r install_service

if [[ "$install_service" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Installing service...${NC}"
    sudo cp kleinanzeigen-scraper-api.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable kleinanzeigen-scraper-api.service
    sudo systemctl start kleinanzeigen-scraper-api.service
    
    # Check service status
    echo -e "${YELLOW}Checking service status:${NC}"
    sudo systemctl status kleinanzeigen-scraper-api.service
    
    # Check if the service is accessible
    sleep 3
    if curl -s http://localhost:3030/api/status > /dev/null; then
        echo -e "${GREEN}Service is running and accessible at http://localhost:3030/api/status${NC}"
        CURL_OUTPUT=$(curl -s http://localhost:3030/api/status)
        echo -e "${GREEN}Server status: ${CURL_OUTPUT}${NC}"
    else
        echo -e "${RED}Service may be running but is not accessible at http://localhost:3030/api/status${NC}"
        echo -e "${YELLOW}Checking service logs:${NC}"
        sudo journalctl -u kleinanzeigen-scraper-api.service -n 20 --no-pager
    fi
fi

echo -e "${GREEN}Installation completed!${NC}"
echo -e "${YELLOW}Don't forget to edit backend/config.py to add your API key and other settings.${NC}"
echo -e "${YELLOW}The API server will be available at http://localhost:3030/api/ once started.${NC}"

# Deactivate virtual environment
deactivate

echo -e "${GREEN}You can now run the API server manually with:${NC}"
echo -e "${GREEN}source kleinanzeigenScraper/bin/activate && python backend/api_server.py${NC}"

# Provide troubleshooting information
echo -e "\n${YELLOW}Troubleshooting:${NC}"
echo -e "1. If the server doesn't start, check the logs with: ${GREEN}sudo journalctl -u kleinanzeigen-scraper-api.service -f${NC}"
echo -e "2. Make sure port 3030 is not in use by another application"
echo -e "3. Check if Python has permission to bind to port 3030"
echo -e "4. Verify that the backend/config.py file has the correct API key and settings" 