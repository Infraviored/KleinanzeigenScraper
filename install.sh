#!/bin/bash

# KleinanzeigenScraper Installer
# This script sets up the entire environment for the KleinanzeigenScraper

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting KleinanzeigenScraper installation...${NC}"

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

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo -e "${RED}Node.js is not installed. Please install Node.js and try again.${NC}"
    exit 1
fi

NODE_VERSION=$(node --version)
echo -e "Found Node.js version: ${NODE_VERSION}"

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo -e "${RED}npm is not installed. Please install npm and try again.${NC}"
    exit 1
fi

NPM_VERSION=$(npm --version)
echo -e "Found npm version: ${NPM_VERSION}"

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
pip install -r requirements.txt

# 3. Install Node.js dependencies
echo -e "${YELLOW}Installing Node.js dependencies...${NC}"
npm install

# 4. Create config.py if it doesn't exist
if [ ! -f "config.py" ]; then
    echo -e "${YELLOW}Creating config.py from template...${NC}"
    cp config_template.py config.py
    echo -e "${YELLOW}Please edit config.py to add your API key and other settings.${NC}"
fi

# 5. Create data directory if it doesn't exist
if [ ! -d "data" ]; then
    echo -e "${YELLOW}Creating data directory...${NC}"
    mkdir -p data
fi

# 6. Set up systemd service
echo -e "${YELLOW}Setting up systemd service...${NC}"

# Get current username and UID
CURRENT_USER=$(whoami)
CURRENT_UID=$(id -u)

# Remove existing start-service.sh if it exists
if [ -f "start-service.sh" ]; then
    rm -f start-service.sh
fi

# Create a startup script for the service
echo -e "${YELLOW}Creating startup script...${NC}"
cat > start-service.sh << EOL
#!/bin/bash
source ${INSTALL_DIR}/kleinanzeigenScraper/bin/activate
cd ${INSTALL_DIR}
exec node ${INSTALL_DIR}/server.js
EOL

# Make the startup script executable
chmod +x start-service.sh

# Create temporary service file with correct paths
cat > kleinanzeigen-scraper.service.tmp << EOL
[Unit]
Description=KleinanzeigenScraper Service
After=network.target

[Service]
Type=simple
# Use direct UID instead of username to avoid user lookup issues
User=${CURRENT_UID}
Group=$(id -g)
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/start-service.sh
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kleinanzeigen-scraper

[Install]
WantedBy=multi-user.target
EOL

# 7. Test the server manually
echo -e "${YELLOW}Testing the server...${NC}"
echo -e "${BLUE}Starting the server in test mode...${NC}"

# Run the server in the background
(source kleinanzeigenScraper/bin/activate && node server.js > server_test.log 2>&1) &
SERVER_PID=$!

# Wait a few seconds for the server to start
sleep 5

# Check if the server is running
if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}Server process is running (PID: $SERVER_PID).${NC}"
    
    # Check if the server is accessible
    if curl -s http://localhost:3030 > /dev/null; then
        echo -e "${GREEN}Server is accessible at http://localhost:3030${NC}"
    else
        echo -e "${RED}Server process is running but not accessible at http://localhost:3030${NC}"
        echo -e "${YELLOW}Checking server logs:${NC}"
        tail -n 20 server_test.log
    fi
else
    echo -e "${RED}Server process failed to start.${NC}"
    echo -e "${YELLOW}Checking server logs:${NC}"
    cat server_test.log
fi

# Kill the test server
kill $SERVER_PID 2>/dev/null || true
rm server_test.log 2>/dev/null || true

echo -e "${YELLOW}Service file created. To install as a system service, run:${NC}"
echo -e "${GREEN}sudo cp kleinanzeigen-scraper.service.tmp /etc/systemd/system/kleinanzeigen-scraper.service${NC}"
echo -e "${GREEN}sudo systemctl daemon-reload${NC}"
echo -e "${GREEN}sudo systemctl enable kleinanzeigen-scraper.service${NC}"
echo -e "${GREEN}sudo systemctl start kleinanzeigen-scraper.service${NC}"

# Ask if user wants to install the service now
echo -e "${YELLOW}Do you want to install and start the service now? (y/n)${NC}"
read -r install_service

if [[ "$install_service" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Installing service...${NC}"
    sudo cp kleinanzeigen-scraper.service.tmp /etc/systemd/system/kleinanzeigen-scraper.service
    sudo systemctl daemon-reload
    sudo systemctl enable kleinanzeigen-scraper.service
    sudo systemctl start kleinanzeigen-scraper.service
    
    # Check service status
    echo -e "${YELLOW}Checking service status:${NC}"
    sudo systemctl status kleinanzeigen-scraper.service
    
    # Check if the service is accessible
    sleep 3
    if curl -s http://localhost:3030 > /dev/null; then
        echo -e "${GREEN}Service is running and accessible at http://localhost:3030${NC}"
    else
        echo -e "${RED}Service may be running but is not accessible at http://localhost:3030${NC}"
        echo -e "${YELLOW}Checking service logs:${NC}"
        sudo journalctl -u kleinanzeigen-scraper.service -n 20 --no-pager
    fi
fi

echo -e "${GREEN}Installation completed!${NC}"
echo -e "${YELLOW}Don't forget to edit config.py to add your API key and other settings.${NC}"
echo -e "${YELLOW}The server will be available at http://localhost:3030 once started.${NC}"

# Deactivate virtual environment
deactivate

echo -e "${GREEN}You can now run the service manually with:${NC}"
echo -e "${GREEN}source kleinanzeigenScraper/bin/activate && node server.js${NC}"

# Provide troubleshooting information
echo -e "\n${YELLOW}Troubleshooting:${NC}"
echo -e "1. If the server doesn't start, check the logs with: ${GREEN}sudo journalctl -u kleinanzeigen-scraper.service -f${NC}"
echo -e "2. Make sure port 3030 is not in use by another application"
echo -e "3. Check if Node.js has permission to bind to port 3030"
echo -e "4. Verify that the config.py file has the correct API key and settings" 