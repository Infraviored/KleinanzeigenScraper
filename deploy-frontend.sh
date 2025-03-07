#!/bin/bash

# KleinanzeigenScraper Frontend Deployment Script
# This script copies the frontend files to the Nginx webroot

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting KleinanzeigenScraper Frontend deployment...${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run this script as root or with sudo${NC}"
  exit 1
fi

# Get the current directory
INSTALL_DIR=$(pwd)
echo -e "Installing from: ${INSTALL_DIR}"

# Define the Nginx webroot directory
WEBROOT_DIR="/var/www/html/kleinanzeigenScraper"

# Create the webroot directory if it doesn't exist
if [ ! -d "$WEBROOT_DIR" ]; then
    echo -e "${YELLOW}Creating webroot directory: ${WEBROOT_DIR}${NC}"
    mkdir -p "$WEBROOT_DIR"
fi

# Copy the frontend files to the webroot
echo -e "${YELLOW}Copying frontend files to webroot...${NC}"
cp -r frontend/* "$WEBROOT_DIR/"

# Set proper permissions
echo -e "${YELLOW}Setting proper permissions...${NC}"
chown -R www-data:www-data "$WEBROOT_DIR"
chmod -R 755 "$WEBROOT_DIR"

# Copy the Nginx configuration file
echo -e "${YELLOW}Copying Nginx configuration file...${NC}"
cp kleinanzeigenScraper.infraviored.lol.conf /etc/nginx/sites-available/

# Create a symbolic link in sites-enabled if it doesn't exist
if [ ! -f "/etc/nginx/sites-enabled/kleinanzeigenScraper.infraviored.lol.conf" ]; then
    echo -e "${YELLOW}Creating symbolic link in sites-enabled...${NC}"
    ln -s /etc/nginx/sites-available/kleinanzeigenScraper.infraviored.lol.conf /etc/nginx/sites-enabled/
fi

# Test the Nginx configuration
echo -e "${YELLOW}Testing Nginx configuration...${NC}"
nginx -t

# Reload Nginx
echo -e "${YELLOW}Reloading Nginx...${NC}"
systemctl reload nginx

echo -e "${GREEN}Frontend deployment completed!${NC}"
echo -e "${YELLOW}The frontend is now available at https://kleinanzeigenScraper.infraviored.lol${NC}" 