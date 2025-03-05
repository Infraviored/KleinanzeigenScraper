import os
import logging
import argparse
from scraper import scrape_listings
from process_listings import update_listings_with_chatgpt

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Main entry point that acts as a wrapper for different functionalities"""
    parser = argparse.ArgumentParser(description="Laptop listing scraper and processor")
    parser.add_argument("--mode", choices=["scrape", "process", "both"], default="both",
                        help="Operation mode: scrape, process, or both")
    parser.add_argument("--urls", nargs="+", 
                        default=["https://www.kleinanzeigen.de/s-notebooks/preis::1400/rtx4060/k0c278"],
                        help="URLs to scrape (only used in scrape or both modes)")
    parser.add_argument("--max-listings", type=int, default=None,
                        help="Maximum number of listings to scrape per URL")
    
    args = parser.parse_args()
    
    # Define paths for data
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    output_file = os.path.join(data_dir, "listings.json")
    
    # Create data directory if it doesn't exist
    os.makedirs(data_dir, exist_ok=True)
    
    if args.mode in ["scrape", "both"]:
        logger.info("Starting scraping mode")
        scrape_listings(args.urls, output_file, max_listings=args.max_listings)
    
    if args.mode in ["process", "both"]:
        logger.info("Starting processing mode")
        update_listings_with_chatgpt(output_file)
    
    logger.info("All operations completed")

if __name__ == "__main__":
    main()
