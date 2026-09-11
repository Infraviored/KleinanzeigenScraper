# LEGACY / PRESERVED SELENIUM SCRAPER
# This file contains the original Selenium-based scraper.
# It is intentionally preserved because we need browser-session login capabilities
# and interactive features (like user outreach/messaging) inside the user account in future stages.
# Do not delete this file.
import os
import db_schema
import json
import time
import pickle
import logging
import re
import sqlite3
from selenium import webdriver
import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from config import DELAY_BETWEEN_PAGES, DELAY_BETWEEN_LISTINGS, PAGES_TO_SCRAPE

# Set up logging
logger = logging.getLogger(__name__)


def update_progress(phase, current, total, status):
    """Write progress details to a JSON file for frontend polling"""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    progress_file = os.path.join(data_dir, "scraper_progress.json")
    os.makedirs(data_dir, exist_ok=True)
    try:
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "phase": phase,
                    "current": current,
                    "total": total,
                    "status": status,
                    "timestamp": int(time.time()),
                },
                f,
                indent=2,
            )
    except Exception as e:
        logger.error(f"Error writing progress file: {str(e)}")


def harvest_missing_descriptions(driver, campaign_id=None):
    """Query SQLite database for listings missing detailed descriptions, and visit them sequentially"""
    db_path = db_schema.default_path()
    if not os.path.exists(db_path):
        logger.warning(
            f"Database not found at {db_path}. Skipping detailed description harvest."
        )
        return

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query all listings that have no detailed description, details, or images and belong to enabled searches
        if campaign_id is not None:
            cursor.execute(
                """
                SELECT l.id, l.url, l.title FROM listings l
                JOIN searches s ON l.search_id = s.id
                WHERE s.enabled = 1 AND s.campaign_id = ? AND (
                    l.detailed_description IS NULL OR l.detailed_description = '' OR
                    l.details IS NULL OR l.details = '' OR l.details = '{}' OR
                    l.images IS NULL OR l.images = '' OR l.images = '[]'
                )
            """,
                (campaign_id,),
            )
        else:
            cursor.execute(
                """
                SELECT l.id, l.url, l.title FROM listings l
                JOIN searches s ON l.search_id = s.id
                WHERE s.enabled = 1 AND (
                    l.detailed_description IS NULL OR l.detailed_description = '' OR
                    l.details IS NULL OR l.details = '' OR l.details = '{}' OR
                    l.images IS NULL OR l.images = '' OR l.images = '[]'
                )
            """
            )
        rows = cursor.fetchall()
        logger.info(
            f"Found {len(rows)} listings missing detailed descriptions to harvest"
        )

        total = len(rows)
        if total == 0:
            update_progress("harvesting", 0, 0, "No listings require harvesting.")
        else:
            update_progress(
                "harvesting",
                0,
                total,
                f"Found {total} listings missing details to harvest.",
            )

        for idx, r in enumerate(rows):
            listing_id = r["id"]
            url = r["url"]
            title = r["title"]

            logger.info(f"Harvesting details for listing {listing_id} ({title}): {url}")
            update_progress(
                "harvesting",
                idx,
                total,
                f"Harvesting listing {idx + 1}/{total}: {title}",
            )
            try:
                # Open listing detail URL directly
                driver.get(url)

                # Wait for the description element to load
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "viewad-description"))
                    )
                except TimeoutException:
                    logger.warning(
                        f"Timeout waiting for description element for listing {listing_id}"
                    )
                    continue

                soup = BeautifulSoup(driver.page_source, "html.parser")
                desc_elem = soup.select_one("#viewad-description-text")
                detailed_description = ""
                if desc_elem:
                    detailed_description = desc_elem.get_text(
                        separator="\n", strip=False
                    )

                # 1. Parse details key-value pairs
                details = {}
                details_list = soup.select("#viewad-details .addetailslist--detail")
                for detail in details_list:
                    val_elem = detail.select_one(".addetailslist--detail--value")
                    if val_elem:
                        val_text = val_elem.get_text(strip=True)
                        key_text = detail.get_text(strip=True)
                        if key_text.endswith(val_text):
                            key_text = key_text[: -len(val_text)].strip()
                        details[key_text] = val_text

                # 2. Parse images
                images = []
                image_elems = soup.select(".galleryimage-element img")
                for img in image_elems:
                    src = img.get("src") or img.get("data-imgsrc")
                    if src:
                        images.append(src)

                cursor.execute(
                    """
                    UPDATE listings 
                    SET detailed_description = ?, details = ?, images = ?, full_info_obtained = 1,
                        last_description_changed_at = ?
                    WHERE id = ?
                """,
                    (
                        detailed_description,
                        json.dumps(details),
                        json.dumps(images),
                        datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        listing_id,
                    ),
                )
                conn.commit()
                logger.info(
                    f"Successfully harvested detailed description, {len(details)} details, and {len(images)} images for ID {listing_id}"
                )

            except Exception as e:
                logger.error(
                    f"Error harvesting details for listing {listing_id}: {str(e)}"
                )

            # Delay to mimic human behavior
            time.sleep(DELAY_BETWEEN_LISTINGS)

        if total > 0:
            update_progress(
                "harvesting", total, total, "Detailed harvesting completed."
            )
        conn.close()
    except Exception as e:
        logger.error(f"Error in harvest_missing_descriptions: {str(e)}")


def save_cookies(driver, path):
    """Save browser cookies to a file"""
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, "wb") as file:
        pickle.dump(driver.get_cookies(), file)
    logger.info(f"Cookies saved to {path}")


def load_cookies(driver, path):
    """Load cookies from file into browser session"""
    if not os.path.exists(path):
        logger.warning(f"Cookie file not found: {path}")
        return False

    with open(path, "rb") as file:
        cookies = pickle.load(file)
        for cookie in cookies:
            # Some cookies might cause issues, so we handle exceptions
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.warning(f"Error loading cookie: {str(e)}")

    logger.info("Cookies loaded successfully")
    return True


def save_logged_in_email(email):
    """Persist the active session user email for backend/frontend notifications"""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    os.makedirs(data_dir, exist_ok=True)
    status_path = os.path.join(data_dir, "session_status.json")
    try:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "email": email,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                },
                f,
                indent=2,
            )
        logger.info(f"Saved session status: {email}")
    except Exception as e:
        logger.error(f"Failed to write session status: {str(e)}")


def check_login_status(driver):
    """Check if the user is logged in and return their email address if found"""
    try:
        # Navigate to my-advertisements to trigger login check
        current_url = driver.current_url
        if "meine-anzeigen" not in current_url:
            driver.get(
                "https://www.kleinanzeigen.de/m-meine-anzeigen.html?tab=PROJECTS"
            )
            time.sleep(3)

        # Look for [data-testid="logged-in-user"] matching the user's signature
        indicators = driver.find_elements(
            By.CSS_SELECTOR, '[data-testid="logged-in-user"]'
        )
        if indicators:
            text = indicators[0].text
            # Extract email from e.g. "angemeldet als: floo.schneider@gmx.de"
            email_match = re.search(r"angemeldet als:\s*(.+)", text, re.IGNORECASE)
            if email_match:
                email = email_match.group(1).strip()
                save_logged_in_email(email)
                return email
            save_logged_in_email("Active Session")
            return "Active Session"

        # Fallback check for logout buttons
        logout_buttons = driver.find_elements(
            By.CSS_SELECTOR, '[data-testid="logout-button"], a[href*="abmelden.html"]'
        )
        if logout_buttons:
            save_logged_in_email("Active Session")
            return "Active Session"
    except Exception as e:
        logger.warning(f"Error checking login state: {str(e)}")
    return None


def manual_login(driver, cookies_path):
    """Handle login process with cookie persistence, waiting automatically for browser-based user logins"""
    # 1. First try to load existing cookies
    if os.path.exists(cookies_path):
        driver.get("https://www.kleinanzeigen.de/")
        load_cookies(driver, cookies_path)
        driver.refresh()
        time.sleep(3)

        email = check_login_status(driver)
        if email:
            logger.info(f"Successfully logged in using saved cookies: {email}")
            return

    # 2. Watch browser interactively for user manual login
    logger.info(
        "Saved login session invalid or missing. Commencing dynamic interactive login watcher..."
    )
    driver.get("https://www.kleinanzeigen.de/m-einloggen.html")

    # Watch browser location and indicators for up to 300 seconds (5 minutes)
    max_wait = 300
    check_interval = 3
    elapsed = 0

    while elapsed < max_wait:
        try:
            current_url = driver.current_url
            # If the user reaches the advertisements/projects board, check for login signature
            if "meine-anzeigen" in current_url or "tab=PROJECTS" in current_url:
                email = check_login_status(driver)
                if email:
                    logger.info(
                        f"User manual login succeeded! Authenticated as: {email}"
                    )
                    save_cookies(driver, cookies_path)
                    return
            else:
                # Also do a quick query check in case they are still on the homepage but logged in
                indicators = driver.find_elements(
                    By.CSS_SELECTOR, '[data-testid="logged-in-user"]'
                )
                if indicators:
                    email = check_login_status(driver)
                    if email:
                        logger.info(
                            f"User manual login succeeded! Authenticated as: {email}"
                        )
                        save_cookies(driver, cookies_path)
                        return
        except Exception as e:
            logger.warning(f"Error during interactive login check: {str(e)}")

        time.sleep(check_interval)
        elapsed += check_interval

    logger.error("Interactive user login watcher timed out after 5 minutes.")
    save_logged_in_email(None)
    raise TimeoutError(
        "Interactive manual login timed out. Please trigger authentication again."
    )


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
            detailed_description = desc_elem.get_text(separator="\n", strip=False)

        # Go back to the search results
        driver.get(current_url)

        return detailed_description

    except Exception as e:
        logger.error(f"Error getting detailed description: {str(e)}")
        # Try to go back to the search results
        try:
            driver.get(current_url)
        except Exception:
            pass
        return ""


def scrape_page(driver, url, output_file=None, max_listings=None):
    """Scrape a page and get detailed descriptions without LLM processing"""

    # Open the target URL and wait for the content to load
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

    # Load existing listings to check for duplicates
    existing_listings = []
    existing_ids = set()
    if output_file and os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing_listings = json.load(f)
                existing_ids = {item.get("id", "") for item in existing_listings}
                logger.info(
                    f"Loaded {len(existing_ids)} existing listing IDs to check for duplicates"
                )
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error loading existing listings: {str(e)}")
            existing_listings = []
            existing_ids = set()

    # Loop through each listing in the search results
    scraped_listings = []
    listing_count = 0

    for item in soup.select("ul#srchrslt-adtable li.ad-listitem"):
        # Check if we've reached the maximum number of listings to process
        if max_listings is not None and listing_count >= max_listings:
            logger.info(f"Reached maximum number of listings to scrape: {max_listings}")
            break

        try:
            # Extract listing ID from data attributes first to check for duplicates
            listing_id = ""
            article_elem = item.select_one("article.aditem")
            if article_elem and article_elem.has_attr("data-adid"):
                listing_id = article_elem["data-adid"]

            # Skip if this listing ID already exists in our data
            if listing_id in existing_ids:
                logger.info(f"Skipping already scraped listing ID: {listing_id}")
                continue

            # Extract basic listing information
            title_elem = item.select_one("h2 a")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Extract the listing URL for detailed view
            listing_url = ""
            if title_elem and title_elem.has_attr("href"):
                listing_url = "https://www.kleinanzeigen.de" + title_elem["href"]

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
                "detailed_description": "",
                "llm_processed": False,
            }

            # Save after each discovery if output_file is provided
            if listing_url:
                if output_file:
                    # Add current listing to existing listings and save
                    existing_listings.append(listing)
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(existing_listings, f, ensure_ascii=False, indent=4)
                    logger.info(f"Saved discovered listing to {output_file}: {title}")

                listing_count += 1
                scraped_listings.append(listing)

        except Exception as e:
            logger.error(f"Error scraping listing: {str(e)}")
            continue

    logger.info(f"Scraped {len(scraped_listings)} discovered listings from {url}")
    return scraped_listings


def scrape_listings(urls, output_file, max_listings=None):
    """Main function to scrape listings from multiple URLs"""
    # Define paths for persistent data
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    cookies_path = os.path.join(data_dir, "cookies.pkl")
    user_data_dir = os.path.join(data_dir, "chrome_profile")

    # Create directories if they don't exist
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(user_data_dir, exist_ok=True)

    # Initialize your Selenium driver with persistent profile
    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.binary_location = "/opt/google/chrome/chrome"

    # Headless optimization:
    is_interactive = os.environ.get("INTERACTIVE_LOGIN") == "1"
    if not is_interactive and os.path.exists(cookies_path):
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    # Execute CDP commands to make the browser less detectable
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """
        },
    )

    try:
        # Handle login with cookie persistence
        manual_login(driver, cookies_path)

        all_scraped_listings = []
        total_pages = len(urls) * PAGES_TO_SCRAPE
        current_page_idx = 0

        for base_url in urls:
            # Process multiple pages for each base URL
            for page in range(1, PAGES_TO_SCRAPE + 1):
                current_page_idx += 1
                update_progress(
                    "discovery",
                    current_page_idx - 1,
                    total_pages,
                    f"Discovering listings on page {page} of {PAGES_TO_SCRAPE}...",
                )
                if page == 1:
                    # First page uses the original URL
                    current_url = base_url
                else:
                    # For subsequent pages, insert the page number into the URL
                    # Check if the URL already contains a page parameter
                    if "/seite:" in base_url:
                        # Replace existing page parameter
                        current_url = re.sub(
                            r"/seite:\d+/", f"/seite:{page}/", base_url
                        )
                    else:
                        # Find the position to insert the page parameter
                        # Typically after the search path but before any filters
                        parts = base_url.split("/")
                        if len(parts) >= 4:
                            domain_part = "/".join(
                                parts[:3]
                            )  # e.g., https://www.kleinanzeigen.de
                            path_part = parts[3]  # e.g., s-notebooks

                            # Insert the page parameter after the path part
                            remaining_parts = (
                                "/".join(parts[4:]) if len(parts) > 4 else ""
                            )
                            current_url = f"{domain_part}/{path_part}/seite:{page}/{remaining_parts}"
                        else:
                            current_url = base_url

                logger.info(f"Scraping page {page} of {PAGES_TO_SCRAPE}: {current_url}")

                # Calculate remaining listings to scrape
                remaining = None
                if max_listings is not None:
                    remaining = max_listings - len(all_scraped_listings)
                    if remaining <= 0:
                        logger.info(
                            "Reached maximum listings limit, stopping scrape early."
                        )
                        break

                # Scrape the current page
                scraped_listings = scrape_page(
                    driver,
                    current_url,
                    output_file=output_file,
                    max_listings=remaining,
                )
                all_scraped_listings.extend(scraped_listings)

                # Add a delay between pages to avoid being flagged as a bot
                if page < PAGES_TO_SCRAPE:
                    time.sleep(DELAY_BETWEEN_PAGES)

        if total_pages > 0:
            update_progress(
                "discovery",
                total_pages,
                total_pages,
                "Rapid listing discovery completed.",
            )
        logger.info(
            f"Successfully scraped {len(all_scraped_listings)} listings across all pages"
        )

    except Exception as e:
        logger.error(f"Error in scraping process: {str(e)}")
    finally:
        driver.quit()


def preview_url_listings_count(url):
    """Headless driver preview to fetch first page result count quickly"""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    cookies_path = os.path.join(data_dir, "cookies.pkl")
    user_data_dir = os.path.join(data_dir, "chrome_profile")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.binary_location = "/opt/google/chrome/chrome"

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """
        },
    )
    try:
        # Load the cookies if present to bypass GDPR/captchas instantly
        if os.path.exists(cookies_path):
            driver.get("https://www.kleinanzeigen.de/")
            load_cookies(driver, cookies_path)

        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "srchrslt-adtable"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
        items = soup.select("ul#srchrslt-adtable li.ad-listitem")
        count = len(items)
        print(f"__PREVIEW_COUNT__:{count}")
        return count
    except Exception as e:
        print(f"__PREVIEW_ERROR__:{str(e)}")
        return 0
    finally:
        driver.quit()


def harvest_descriptions(campaign_id=None):
    """Main wrapper function to launch driver and harvest all missing descriptions in one go"""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    cookies_path = os.path.join(data_dir, "cookies.pkl")
    user_data_dir = os.path.join(data_dir, "chrome_profile")

    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.binary_location = "/opt/google/chrome/chrome"

    # Always headless for harvesting since session is already logged in
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """
        },
    )

    try:
        # Load persistent login session cookies
        if os.path.exists(cookies_path):
            driver.get("https://www.kleinanzeigen.de")
            with open(cookies_path, "rb") as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    driver.add_cookie(cookie)
            logger.info("Loaded persistent session cookies for description harvesting")

        # Sequential harvest loop
        harvest_missing_descriptions(driver, campaign_id)

    except Exception as e:
        logger.error(f"Error during description harvesting session: {str(e)}")
    finally:
        driver.quit()


def update_all_descriptions(driver, campaign_id=None):
    """Query SQLite database for all listings under active searches, visit them, and update if description changed"""
    db_path = db_schema.default_path()
    if not os.path.exists(db_path):
        logger.warning(
            f"Database not found at {db_path}. Skipping update all descriptions."
        )
        return

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if campaign_id is not None:
            cursor.execute(
                """
                SELECT l.id, l.url, l.title, l.detailed_description FROM listings l
                JOIN searches s ON l.search_id = s.id
                WHERE s.enabled = 1 AND s.campaign_id = ?
            """,
                (campaign_id,),
            )
        else:
            cursor.execute(
                """
                SELECT l.id, l.url, l.title, l.detailed_description FROM listings l
                JOIN searches s ON l.search_id = s.id
                WHERE s.enabled = 1
            """
            )
        rows = cursor.fetchall()
        logger.info(f"Found {len(rows)} listings to check for description updates")

        total = len(rows)
        if total == 0:
            update_progress(
                "updating-descriptions", 0, 0, "No listings found to update."
            )
        else:
            update_progress(
                "updating-descriptions",
                0,
                total,
                f"Found {total} listings to check/update.",
            )

        for idx, r in enumerate(rows):
            listing_id = r["id"]
            url = r["url"]
            title = r["title"]
            old_description = r["detailed_description"] or ""

            logger.info(f"Checking updates for listing {listing_id} ({title}): {url}")
            update_progress(
                "updating-descriptions",
                idx,
                total,
                f"Checking listing {idx + 1}/{total}: {title}",
            )
            try:
                driver.get(url)

                # Wait for the description element to load
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "viewad-description"))
                    )
                except TimeoutException:
                    logger.warning(
                        f"Timeout waiting for description element for listing {listing_id}"
                    )
                    continue

                soup = BeautifulSoup(driver.page_source, "html.parser")
                desc_elem = soup.select_one("#viewad-description-text")
                detailed_description = ""
                if desc_elem:
                    detailed_description = desc_elem.get_text(
                        separator="\n", strip=False
                    )

                # Parse details key-value pairs
                details = {}
                details_list = soup.select("#viewad-details .addetailslist--detail")
                for detail in details_list:
                    val_elem = detail.select_one(".addetailslist--detail--value")
                    if val_elem:
                        val_text = val_elem.get_text(strip=True)
                        key_text = detail.get_text(strip=True)
                        if key_text.endswith(val_text):
                            key_text = key_text[: -len(val_text)].strip()
                        details[key_text] = val_text

                # Parse images
                images = []
                image_elems = soup.select(".galleryimage-element img")
                for img in image_elems:
                    src = img.get("src") or img.get("data-imgsrc")
                    if src:
                        images.append(src)

                # Compare: Only update database and timestamp if description has changed
                if detailed_description.strip() != old_description.strip():
                    logger.info(
                        f"Description changed for listing {listing_id}! Updating in DB."
                    )
                    cursor.execute(
                        """
                        UPDATE listings 
                        SET detailed_description = ?, details = ?, images = ?, full_info_obtained = 1,
                            last_description_changed_at = ?
                        WHERE id = ?
                    """,
                        (
                            detailed_description,
                            json.dumps(details),
                            json.dumps(images),
                            datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            listing_id,
                        ),
                    )
                    conn.commit()
                else:
                    logger.info(f"No description changes for listing {listing_id}.")

            except Exception as e:
                logger.error(
                    f"Error updating details for listing {listing_id}: {str(e)}"
                )

            # Delay to mimic human behavior
            time.sleep(DELAY_BETWEEN_LISTINGS)

        if total > 0:
            update_progress(
                "updating-descriptions", total, total, "Deep updates completed."
            )
        conn.close()
    except Exception as e:
        logger.error(f"Error in update_all_descriptions: {str(e)}")


def update_all_descriptions_session(campaign_id=None):
    """Main wrapper function to launch driver and update all descriptions in one go"""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    cookies_path = os.path.join(data_dir, "cookies.pkl")
    user_data_dir = os.path.join(data_dir, "chrome_profile")

    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.binary_location = "/opt/google/chrome/chrome"

    # Always headless for harvesting/updating since session is already logged in
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
        """
        },
    )

    try:
        # Load persistent login session cookies
        if os.path.exists(cookies_path):
            driver.get("https://www.kleinanzeigen.de")
            with open(cookies_path, "rb") as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    driver.add_cookie(cookie)
            logger.info("Loaded persistent session cookies for description update")

        # Sequential update loop
        update_all_descriptions(driver, campaign_id)

    except Exception as e:
        logger.error(f"Error during description update session: {str(e)}")
    finally:
        driver.quit()
