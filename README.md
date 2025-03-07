# KleinanzeigenScraper

A tool for scraping laptop listings from Kleinanzeigen.de and analyzing them with ChatGPT.

## Features

- Scrapes laptop listings from Kleinanzeigen.de
- Analyzes listings using OpenAI's GPT models to extract key information
- Web interface to view and manage listings
- Systemd service for continuous operation

## Prerequisites

- Python 3.6 or newer
- Node.js and npm
- Python venv module (on Debian/Ubuntu: `sudo apt install python3-venv`)

## Installation

### Automatic Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/KleinanzeigenScraper.git
   cd KleinanzeigenScraper
   ```

2. Make the installer executable:
   ```bash
   chmod +x install.sh
   ```

3. Run the installer:
   ```bash
   ./install.sh
   ```

4. Follow the on-screen instructions to complete the installation.

5. Edit the `config.py` file to add your OpenAI API key and customize settings.

6. Install the systemd service (optional):
   ```bash
   sudo cp kleinanzeigen-scraper.service.tmp /etc/systemd/system/kleinanzeigen-scraper.service
   sudo systemctl daemon-reload
   sudo systemctl enable kleinanzeigen-scraper.service
   sudo systemctl start kleinanzeigen-scraper.service
   ```

### Manual Installation

If you prefer to install manually:

1. Create a Python virtual environment:
   ```bash
   python3 -m venv kleinanzeigenScraper
   source kleinanzeigenScraper/bin/activate
   ```

2. Install Python dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Install Node.js dependencies:
   ```bash
   npm install
   ```

4. Create a configuration file:
   ```bash
   cp config_template.py config.py
   ```

5. Edit `config.py` to add your OpenAI API key and customize settings.

## Usage

### Running the Web Interface

```bash
source kleinanzeigenScraper/bin/activate
node server.js
```

The web interface will be available at http://localhost:3030

### Running the Scraper Directly

```bash
source kleinanzeigenScraper/bin/activate
python main.py --mode both
```

Command line options:
- `--mode`: Choose between `scrape`, `process`, or `both` (default: `both`)
- `--urls`: Specify URLs to scrape (optional)
- `--max-listings`: Maximum number of listings to scrape per URL (optional)

## Architecture

The system consists of two main components:

1. **Node.js Server (server.js)**: Provides a web interface for viewing and managing scraped listings
2. **Python Scraper (main.py)**: Handles the actual scraping and processing of listings

The Node.js server can trigger the Python scraper through the `child_process.spawn()` method, allowing users to initiate scraping jobs through the web interface.

## Troubleshooting

### Virtual Environment Creation Fails

If you see an error like:
```
The virtual environment was not created successfully because ensurepip is not available.
```

Install the Python venv package:
```bash
# For Debian/Ubuntu
sudo apt install python3-venv

# For Fedora
sudo dnf install python3-venv

# For Arch Linux
sudo pacman -S python-virtualenv
```

## License

[MIT License](LICENSE)

## Accessing the Application

Once the service is running, open your web browser and navigate to:
```
http://localhost:3030
```

If accessing from another device on your network, replace "localhost" with your server's IP address:
```
http://YOUR_SERVER_IP:3030
```

## Managing the Service

- View logs:
  ```bash
  sudo journalctl -u kleinanzeigen-scraper.service -f
  ```

- Restart the service:
  ```bash
  sudo systemctl restart kleinanzeigen-scraper.service
  ```

- Stop the service:
  ```bash
  sudo systemctl stop kleinanzeigen-scraper.service
  ```