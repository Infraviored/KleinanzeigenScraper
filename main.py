import os
import json
import time
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def save_cookies(driver, path):
    """Save browser cookies to a file"""
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, 'wb') as file:
        pickle.dump(driver.get_cookies(), file)
    logger.info(f"Cookies saved to {path}")

def load_cookies(driver, path):
    """Load cookies from file into browser session"""
    if not os.path.exists(path):
        logger.warning(f"Cookie file not found: {path}")
        return False
    
    with open(path, 'rb') as file:
        cookies = pickle.load(file)
        for cookie in cookies:
            # Some cookies might cause issues, so we handle exceptions
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.warning(f"Error loading cookie: {str(e)}")
    
    logger.info("Cookies loaded successfully")
    return True

def check_login_status(driver):
    """Check if the user is logged in"""
    # Navigate to the homepage
    driver.get("https://www.kleinanzeigen.de/")
    
    # Wait for the page to load
    time.sleep(2)
    
    # Look for elements that indicate a logged-in state
    # This could be a username display, account menu, etc.
    try:
        # This selector might need adjustment based on the actual website structure
        logged_in_indicator = driver.find_elements(By.CSS_SELECTOR, ".mein-kleinanzeigen, .user-menu, .account-link")
        return len(logged_in_indicator) > 0
    except:
        return False

def manual_login(driver, cookies_path):
    """Handle login process with cookie persistence"""
    # First try to load cookies
    if os.path.exists(cookies_path):
        # Load the site first (cookies need a matching domain)
        driver.get("https://www.kleinanzeigen.de/")
        load_cookies(driver, cookies_path)
        driver.refresh()  # Refresh to apply cookies
        
        # Check if we're logged in
        if check_login_status(driver):
            logger.info("Successfully logged in using saved cookies")
            return
    
    # If we get here, we need manual login
    driver.get("https://www.kleinanzeigen.de/")
    input("Please log in manually and then press Enter to continue...")
    
    # Save the cookies for next time
    save_cookies(driver, cookies_path)
    logger.info("Manual login completed and cookies saved")

def scrape_page(driver, url, max_details=None, output_file=None):
    # Open the target URL and wait for the content to load.
    logger.info(f"Scraping page: {url}")
    driver.get(url)
    
    # Wait for the main content to load
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "srchrslt-adtable"))
        )
    except TimeoutException:
        logger.error("Timeout waiting for page to load")
        return []
    
    # Parse the page with BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")
    listings = []
    
    # Load existing listings to check for duplicates
    existing_listings = []
    existing_ids = set()
    if output_file and os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_listings = json.load(f)
                existing_ids = {item.get('id', '') for item in existing_listings}
                logger.info(f"Loaded {len(existing_ids)} existing listing IDs to check for duplicates")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error loading existing listings: {str(e)}")
            existing_listings = []
            existing_ids = set()
    
    # Loop through each listing in the search results
    detail_count = 0
    for item in soup.select("ul#srchrslt-adtable li.ad-listitem"):
        try:
            # Extract listing ID from data attributes first to check for duplicates
            listing_id = ""
            article_elem = item.select_one("article.aditem")
            if article_elem and article_elem.has_attr('data-adid'):
                listing_id = article_elem['data-adid']
            
            # Skip if this listing ID already exists in our data
            if listing_id in existing_ids:
                logger.info(f"Skipping already processed listing ID: {listing_id}")
                continue
            
            # Extract basic listing information
            title_elem = item.select_one("h2 a")
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # Extract the listing URL for detailed view
            listing_url = ""
            if title_elem and title_elem.has_attr('href'):
                listing_url = "https://www.kleinanzeigen.de" + title_elem['href']
            
            price_elem = item.select_one("p.aditem-main--middle--price-shipping--price")
            price = price_elem.get_text(strip=True) if price_elem else ""
            
            desc_elem = item.select_one("p.aditem-main--middle--description")
            short_description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            location_elem = item.select_one(".aditem-main--top--left")
            location = location_elem.get_text(strip=True) if location_elem else ""
            
            # Create listing object with basic info
            listing = {
                "id": listing_id,
                "title": title,
                "price": price,
                "short_description": short_description,
                "location": location,
                "url": listing_url,
                "detailed_description": ""
            }
            
            # If we have a valid URL and haven't reached max_details, get detailed information
            if listing_url and (max_details is None or detail_count < max_details):
                detailed_description = get_detailed_description(driver, listing_url)
                listing["detailed_description"] = detailed_description
                detail_count += 1
                
                # Save after each detailed fetch if output_file is provided
                if output_file:
                    # Add current listing to existing listings and save
                    existing_listings.append(listing)
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(existing_listings, f, ensure_ascii=False, indent=4)
                    logger.info(f"Saved listing to {output_file}: {title}")
            
            listings.append(listing)
            logger.info(f"Scraped listing: {title}")
            
        except Exception as e:
            logger.error(f"Error scraping listing: {str(e)}")
            continue
    
    logger.info(f"Scraped {len(listings)} new listings from {url}")
    return listings

def get_detailed_description(driver, url):
    """Get detailed description from a listing's detail page"""
    try:
        # Store current URL to return to later
        current_url = driver.current_url
        
        # Navigate to the listing detail page
        logger.info(f"Getting detailed description from: {url}")
        driver.get(url)
        
        # Wait for the description to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "viewad-description"))
            )
        except TimeoutException:
            logger.warning(f"Timeout waiting for detailed description to load: {url}")
            driver.get(current_url)  # Go back to the search results
            return ""
        
        # Parse the page with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Extract detailed description
        detailed_description = ""
        desc_elem = soup.select_one("#viewad-description-text")
        if desc_elem:
            detailed_description = desc_elem.get_text(separator='\n', strip=False)
        
        # Go back to the search results
        driver.get(current_url)
        
        return detailed_description
        
    except Exception as e:
        logger.error(f"Error getting detailed description: {str(e)}")
        # Try to go back to the search results
        try:
            driver.get(current_url)
        except:
            pass
        return ""

def save_to_json(listings, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=4)
    logger.info(f"Saved {len(listings)} listings to {file_path}")

if __name__ == "__main__":
    # Define paths for persistent data
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    cookies_path = os.path.join(data_dir, "cookies.pkl")
    user_data_dir = os.path.join(data_dir, "chrome_profile")
    output_file = os.path.join(data_dir, "listings.json")
    
    # Create directories if they don't exist
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(user_data_dir, exist_ok=True)
    
    # Initialize your Selenium driver with persistent profile
    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(options=options)
    # Execute CDP commands to make the browser less detectable
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """
    })
    
    try:
        # Handle login with cookie persistence
        manual_login(driver, cookies_path)
        
        # List the target URLs you want to process.
        urls = [
            "https://www.kleinanzeigen.de/s-notebooks/preis::1400/rtx4060/k0c278",
            # Add more URLs as required.
        ]
        
        all_listings = []
        for url in urls:
            # Process only first 2 listings for detailed info and save incrementally
            listings = scrape_page(driver, url, output_file=output_file)
            all_listings.extend(listings)
            # Add a delay between pages to avoid being flagged as a bot
            time.sleep(3)
        
        # No need to save all listings again as we've been saving incrementally
        logger.info(f"Successfully scraped {len(all_listings)} listings with {min(2, len(all_listings))} detailed descriptions")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
    finally:
        driver.quit()
