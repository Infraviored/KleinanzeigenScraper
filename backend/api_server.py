from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
import logging
import threading
import time
import sys

# Add the parent directory to the Python path to allow imports from the backend directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Now import the modules
from backend.scraper import scrape_listings
from backend.process_listings import update_listings_with_chatgpt

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Path configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # Go up one level to the project root
DATA_DIR = os.path.join(PROJECT_ROOT, "data")  # Data is at the project root
LISTINGS_FILE = os.path.join(DATA_DIR, "listings.json")
SEARCH_URLS_FILE = os.path.join(DATA_DIR, "search_urls.json")
SCHEDULE_CONFIG_FILE = os.path.join(DATA_DIR, "schedule_config.json")

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

# Global variables for scheduling
scheduled_thread = None
stop_scheduled_thread = False

# API endpoint to get listings
@app.route('/api/listings', methods=['GET'])
def get_listings():
    try:
        if os.path.exists(LISTINGS_FILE):
            with open(LISTINGS_FILE, 'r') as f:
                listings = json.load(f)
            return jsonify(listings)
        else:
            return jsonify([])
    except Exception as e:
        logger.error(f"Error reading listings: {str(e)}")
        return jsonify({"error": "Failed to retrieve listings data"}), 500

# API endpoint to get search URLs
@app.route('/api/search-urls', methods=['GET'])
def get_search_urls():
    try:
        if os.path.exists(SEARCH_URLS_FILE):
            with open(SEARCH_URLS_FILE, 'r') as f:
                search_urls = json.load(f)
            return jsonify(search_urls)
        else:
            return jsonify([])
    except Exception as e:
        logger.error(f"Error reading search URLs: {str(e)}")
        return jsonify({"error": "Failed to retrieve search URLs"}), 500

# API endpoint to update search URLs
@app.route('/api/search-urls', methods=['POST'])
def update_search_urls():
    try:
        search_urls = request.json
        with open(SEARCH_URLS_FILE, 'w') as f:
            json.dump(search_urls, f, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error saving search URLs: {str(e)}")
        return jsonify({"error": "Failed to save search URLs"}), 500

# API endpoint to trigger scraping manually
@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    try:
        data = request.json
        mode = data.get('mode', 'both')
        urls = data.get('urls')
        max_listings = data.get('maxListings')
        
        # Start scraping in a separate thread to not block the API response
        thread = threading.Thread(
            target=run_scraper,
            args=(mode, urls, max_listings)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "Scraping process started",
            "thread_id": thread.ident
        })
    except Exception as e:
        logger.error(f"Error starting scraper: {str(e)}")
        return jsonify({"error": "Failed to start scraper"}), 500

# API endpoint to get scraping schedule
@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    try:
        if os.path.exists(SCHEDULE_CONFIG_FILE):
            with open(SCHEDULE_CONFIG_FILE, 'r') as f:
                config = json.load(f)
            return jsonify(config)
        else:
            default_config = {"interval": 60, "enabled": True}
            with open(SCHEDULE_CONFIG_FILE, 'w') as f:
                json.dump(default_config, f, indent=2)
            return jsonify(default_config)
    except Exception as e:
        logger.error(f"Error reading schedule config: {str(e)}")
        return jsonify({"error": "Failed to retrieve schedule config"}), 500

# API endpoint to update scraping schedule
@app.route('/api/schedule', methods=['POST'])
def update_schedule():
    try:
        config = request.json
        with open(SCHEDULE_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Restart the scheduling
        setup_scheduled_scraping()
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error saving schedule config: {str(e)}")
        return jsonify({"error": "Failed to save schedule config"}), 500

# API endpoint to get server status
@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        import psutil
        process = psutil.Process(os.getpid())
        
        return jsonify({
            "status": "running",
            "uptime": time.time() - process.create_time(),
            "memory": {
                "rss": f"{process.memory_info().rss / (1024 * 1024):.1f} MB",
                "vms": f"{process.memory_info().vms / (1024 * 1024):.1f} MB"
            },
            "cpu_percent": process.cpu_percent()
        })
    except Exception as e:
        logger.error(f"Error getting server status: {str(e)}")
        return jsonify({"error": "Failed to get server status"}), 500

# Function to run the scraper (called by API and scheduler)
def run_scraper(mode='both', urls=None, max_listings=None):
    try:
        logger.info(f"Starting scraper with mode={mode}")
        
        # If no URLs provided and mode requires URLs, load from file
        if urls is None and mode in ["scrape", "both"]:
            try:
                if os.path.exists(SEARCH_URLS_FILE):
                    with open(SEARCH_URLS_FILE, 'r') as f:
                        search_urls_data = json.load(f)
                        # Filter only enabled search URLs
                        urls = [item['url'] for item in search_urls_data if item.get('enabled', True)]
                        logger.info(f"Loaded {len(urls)} search URLs from {SEARCH_URLS_FILE}")
                
                # If still no URLs, use default
                if not urls:
                    urls = ["https://www.kleinanzeigen.de/s-notebooks/preis::1400/rtx4060/k0c278"]
                    logger.info(f"Using default search URL: {urls[0]}")
            except Exception as e:
                logger.error(f"Error loading search URLs: {str(e)}")
                urls = ["https://www.kleinanzeigen.de/s-notebooks/preis::1400/rtx4060/k0c278"]
        
        if mode in ["scrape", "both"]:
            logger.info("Starting scraping mode")
            from backend.scraper import scrape_listings
            scrape_listings(urls, LISTINGS_FILE, max_listings=max_listings, process_immediately=(mode == "both"))
        
        if mode in ["process", "both"]:
            logger.info("Starting processing mode")
            from backend.process_listings import update_listings_with_chatgpt
            update_listings_with_chatgpt(LISTINGS_FILE)
        
        logger.info("All operations completed")
    except Exception as e:
        logger.error(f"Error in run_scraper: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

# Function for scheduled scraping
def scheduled_scraping_thread():
    global stop_scheduled_thread
    
    while not stop_scheduled_thread:
        try:
            # Load schedule config
            if os.path.exists(SCHEDULE_CONFIG_FILE):
                with open(SCHEDULE_CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                
                interval_minutes = config.get('interval', 60)
                enabled = config.get('enabled', True)
                
                if enabled:
                    logger.info(f"Running scheduled scraping (interval: {interval_minutes} minutes)")
                    run_scraper()
                else:
                    logger.info("Scheduled scraping is disabled")
            else:
                logger.info("No schedule config found, using default (60 minutes)")
                interval_minutes = 60
                run_scraper()
            
            # Sleep for the configured interval
            for _ in range(interval_minutes * 60):
                if stop_scheduled_thread:
                    break
                time.sleep(1)
        except Exception as e:
            logger.error(f"Error in scheduled scraping: {str(e)}")
            # Sleep for 5 minutes before retrying after an error
            time.sleep(300)

# Function to set up scheduled scraping
def setup_scheduled_scraping():
    global scheduled_thread, stop_scheduled_thread
    
    # Stop existing thread if running
    if scheduled_thread and scheduled_thread.is_alive():
        stop_scheduled_thread = True
        scheduled_thread.join(timeout=5)
        stop_scheduled_thread = False
    
    # Start new thread
    scheduled_thread = threading.Thread(target=scheduled_scraping_thread)
    scheduled_thread.daemon = True
    scheduled_thread.start()
    logger.info("Scheduled scraping thread started")

# Start the Flask server when run directly
if __name__ == '__main__':
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Start scheduled scraping
    setup_scheduled_scraping()
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=3030, debug=False)