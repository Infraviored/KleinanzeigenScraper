import os
import json
import db_schema
import time
import pickle
import logging
import re
import sqlite3
import datetime
import requests
from bs4 import BeautifulSoup

import result_list

# For the legacy interactive Selenium login route:
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import DELAY_BETWEEN_PAGES, DELAY_BETWEEN_LISTINGS, PAGES_TO_SCRAPE

# Set up logging
logger = logging.getLogger(__name__)

# Modern browser request headers to safely bypass Akamai bot protection filters
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def fetch(url, caller=None, timeout=10):
    """GETs a page and decodes it as UTF-8.

    The decoding is not incidental. Kleinanzeigen answers with a bare
    `Content-Type: text/html` and no charset, and RFC 2616 tells an HTTP client to
    assume ISO-8859-1 in that case — so `response.text` silently mangles every
    umlaut and the euro sign, turning "Weiß" into "WeiÃ" and hiding "60 € VB" from
    anything looking for a price. The pages are UTF-8; requests' own
    `apparent_encoding` agrees. Setting it explicitly is the fix, and it belongs
    here so no call site can forget it.
    """
    caller = caller if caller is not None else requests
    response = caller.get(url, headers=HEADERS, timeout=timeout)
    response.encoding = "utf-8"
    return response


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


def parse_listing_details_requests(url, session=None):
    """Retrieve and parse detailed specifications, description, and images using direct requests"""
    try:
        caller = session if session is not None else requests
        response = fetch(url, caller=caller)
        if response.status_code != 200:
            logger.warning(
                f"Failed to fetch listing details for {url}. Status: {response.status_code}"
            )
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. Schema.org JSON-LD parsing
        schema_description = None
        schema_main_image = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                # Normalize to a list of objects to handle both single objects and arrays
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    if "@graph" in data and isinstance(data["@graph"], list):
                        items = data["@graph"]
                    else:
                        items = [data]

                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "ImageObject":
                        if item.get("representativeOfPage") is True:
                            schema_description = item.get("description")
                            schema_main_image = item.get("contentUrl")
            except Exception:
                continue

        # 2. HTML fallback
        html_description = ""
        desc_elem = soup.select_one("#viewad-description-text")
        if desc_elem:
            html_description = desc_elem.get_text(separator="\n", strip=False)

        # 3. Parse details key-value pairs
        details = {}
        details_list = soup.select("#viewad-details .addetailslist--detail")
        for detail in details_list:
            val_elem = detail.select_one(".addetailslist--detail--value")
            if val_elem:
                val_text = val_elem.get_text(strip=True)
                key_text = detail.get_text(strip=True)
                if key_text.endswith(val_text):
                    key_text = key_text[: -len(val_text)].strip()
                key_text = key_text.rstrip(":").strip()
                details[key_text] = val_text

        # 4. Parse images
        images = []
        if schema_main_image:
            images.append(schema_main_image)
        image_elems = soup.select(".galleryimage-element img")
        for img in image_elems:
            src = img.get("src") or img.get("data-imgsrc")
            if src and src not in images:
                images.append(src)

        detailed_description = schema_description or html_description

        return {
            "detailed_description": detailed_description,
            "details": details,
            "images": images,
        }
    except Exception as e:
        logger.error(f"Error parsing listing details for {url}: {str(e)}")
        return None


def scrape_listings(urls, output_file, max_listings=None):
    """Main function to scrape listings. Routes to Selenium if interactive login is requested."""
    is_interactive = os.environ.get("INTERACTIVE_LOGIN") == "1"
    if is_interactive:
        logger.info("INTERACTIVE_LOGIN requested. Routing to legacy Selenium scraper.")
        return scrape_listings_selenium(urls, output_file, max_listings)
    else:
        logger.info("Executing optimized fast requests-based scraper.")
        return scrape_listings_requests(urls, output_file, max_listings)


def scrape_listings_requests(urls, output_file, max_listings=None):
    """Main function to scrape listings from multiple URLs using fast requests GET"""
    all_scraped_listings = []
    total_pages = len(urls) * PAGES_TO_SCRAPE
    current_page_idx = 0

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

    for base_url in urls:
        for page in range(1, PAGES_TO_SCRAPE + 1):
            current_page_idx += 1
            update_progress(
                "discovery",
                current_page_idx - 1,
                total_pages,
                f"Discovering listings on page {page} of {PAGES_TO_SCRAPE}...",
            )

            # Insert pagination parameter into URL if page > 1
            if page == 1:
                current_url = base_url
            else:
                if "/seite:" in base_url:
                    current_url = re.sub(
                        r"/seite:\d+(/|$)", f"/seite:{page}\\1", base_url
                    )
                else:
                    parts = base_url.split("/")
                    if len(parts) >= 4:
                        domain_part = "/".join(parts[:3])
                        path_part = parts[3]
                        remaining_parts = "/".join(parts[4:]) if len(parts) > 4 else ""
                        current_url = (
                            f"{domain_part}/{path_part}/seite:{page}/{remaining_parts}"
                        )
                    else:
                        current_url = base_url

            logger.info(f"Scraping page {page} of {PAGES_TO_SCRAPE}: {current_url}")

            # Check if we've reached the maximum listings limit
            if max_listings is not None and len(all_scraped_listings) >= max_listings:
                logger.info("Reached maximum listings limit, stopping scrape early.")
                break

            try:
                response = fetch(current_url)
                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch page {current_url}. Status: {response.status_code}"
                    )
                    continue

                scraped_count = 0

                for parsed in result_list.parse(response.text):
                    # Check limit inside loop too
                    if (
                        max_listings is not None
                        and len(all_scraped_listings) >= max_listings
                    ):
                        break

                    listing_id = parsed["id"]
                    if listing_id in existing_ids:
                        continue

                    listing = result_list.as_db_listing(parsed)

                    # Append and save intermediate
                    existing_listings.append(listing)
                    existing_ids.add(listing_id)
                    all_scraped_listings.append(listing)
                    scraped_count += 1

                if output_file:
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(existing_listings, f, ensure_ascii=False, indent=4)

                logger.info(
                    f"Scraped {scraped_count} discovered listings from {current_url}"
                )

            except Exception as e:
                logger.error(f"Error scraping page {current_url}: {str(e)}")

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
    return all_scraped_listings


def preview_url_listings_count(url):
    """Fetch first page result count quickly using fast requests GET"""
    try:
        response = fetch(url)
        if response.status_code != 200:
            print(
                f"__PREVIEW_ERROR__:Failed to fetch search page, status: {response.status_code}"
            )
            return 0

        # The site reports the full total, which is what a preview should show;
        # the page itself only ever carries the first page of it.
        count = result_list.total_results(response.text)
        if count is None:
            count = len(result_list.parse(response.text))
        print(f"__PREVIEW_COUNT__:{count}")
        return count
    except Exception as e:
        print(f"__PREVIEW_ERROR__:{str(e)}")
        return 0


def harvest_descriptions(campaign_id=None):
    """Main wrapper function to harvest missing descriptions using direct requests GET"""
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
            f"Found {len(rows)} listings missing detailed descriptions to harvest using requests"
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

        with requests.Session() as session:
            for idx, r in enumerate(rows):
                listing_id = r["id"]
                url = r["url"]
                title = r["title"]

                logger.info(
                    f"Harvesting details for listing {listing_id} ({title}): {url}"
                )
                update_progress(
                    "harvesting",
                    idx,
                    total,
                    f"Harvesting listing {idx + 1}/{total}: {title}",
                )

                # Respectful delay between requests
                time.sleep(DELAY_BETWEEN_LISTINGS)

                parsed = parse_listing_details_requests(url, session=session)
                if parsed is None:
                    continue

                cursor.execute(
                    """
                    UPDATE listings 
                    SET detailed_description = ?, details = ?, images = ?, full_info_obtained = 1,
                        last_description_changed_at = ?
                    WHERE id = ?
                """,
                    (
                        parsed["detailed_description"],
                        json.dumps(parsed["details"]),
                        json.dumps(parsed["images"]),
                        datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        listing_id,
                    ),
                )
                conn.commit()
                logger.info(
                    f"Successfully harvested detailed description, {len(parsed['details'])} details, and {len(parsed['images'])} images for ID {listing_id}"
                )

        if total > 0:
            update_progress(
                "harvesting", total, total, "Detailed harvesting completed."
            )
        conn.close()
    except Exception as e:
        logger.error(f"Error in requests-based harvest_descriptions: {str(e)}")


def update_all_descriptions_session(campaign_id=None):
    """Query SQLite database for all active listings, check and update using direct requests GET"""
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
        logger.info(f"Found {len(rows)} listings to check for updates using requests")

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

        with requests.Session() as session:
            for idx, r in enumerate(rows):
                listing_id = r["id"]
                url = r["url"]
                title = r["title"]
                old_description = r["detailed_description"] or ""

                logger.info(
                    f"Checking updates for listing {listing_id} ({title}): {url}"
                )
                update_progress(
                    "updating-descriptions",
                    idx,
                    total,
                    f"Checking listing {idx + 1}/{total}: {title}",
                )

                # Respectful delay between requests
                time.sleep(DELAY_BETWEEN_LISTINGS)

                parsed = parse_listing_details_requests(url, session=session)
                if parsed is None:
                    continue

            detailed_description = parsed["detailed_description"] or ""

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
                        json.dumps(parsed["details"]),
                        json.dumps(parsed["images"]),
                        datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        listing_id,
                    ),
                )
                conn.commit()
            else:
                logger.info(f"No description changes for listing {listing_id}.")

        if total > 0:
            update_progress(
                "updating-descriptions", total, total, "Deep updates completed."
            )
        conn.close()
    except Exception as e:
        logger.error(
            f"Error in requests-based update_all_descriptions_session: {str(e)}"
        )


# =========================================================================
# LEGACY SELENIUM CODE PATHS (PRESERVED FOR FUTURE USER ACCOUNT OUTREACH / MESSAGING)
# =========================================================================


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
        current_url = driver.current_url
        if "meine-anzeigen" not in current_url:
            driver.get(
                "https://www.kleinanzeigen.de/m-meine-anzeigen.html?tab=PROJECTS"
            )
            time.sleep(3)

        indicators = driver.find_elements(
            By.CSS_SELECTOR, '[data-testid="logged-in-user"]'
        )
        if indicators:
            text = indicators[0].text
            email_match = re.search(r"angemeldet als:\s*(.+)", text, re.IGNORECASE)
            if email_match:
                email = email_match.group(1).strip()
                save_logged_in_email(email)
                return email
            save_logged_in_email("Active Session")
            return "Active Session"

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
    if os.path.exists(cookies_path):
        driver.get("https://www.kleinanzeigen.de/")
        load_cookies(driver, cookies_path)
        driver.refresh()
        time.sleep(3)

        email = check_login_status(driver)
        if email:
            logger.info(f"Successfully logged in using saved cookies: {email}")
            return

    logger.info(
        "Saved login session invalid or missing. Commencing dynamic interactive login watcher..."
    )
    driver.get("https://www.kleinanzeigen.de/m-einloggen.html")

    max_wait = 300
    check_interval = 3
    elapsed = 0

    while elapsed < max_wait:
        try:
            current_url = driver.current_url
            if "meine-anzeigen" in current_url or "tab=PROJECTS" in current_url:
                email = check_login_status(driver)
                if email:
                    logger.info(
                        f"User manual login succeeded! Authenticated as: {email}"
                    )
                    save_cookies(driver, cookies_path)
                    return
            else:
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


def scrape_listings_selenium(urls, output_file, max_listings=None):
    """Fallback interactive login / Selenium-based scraper. Preserved intentionally."""
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    cookies_path = os.path.join(data_dir, "cookies.pkl")
    user_data_dir = os.path.join(data_dir, "chrome_profile")

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(user_data_dir, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={user_data_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.binary_location = "/opt/google/chrome/chrome"

    # In case we only run interactive login, run full chrome UI
    is_interactive = os.environ.get("INTERACTIVE_LOGIN") == "1"
    if not is_interactive and os.path.exists(cookies_path):
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
        manual_login(driver, cookies_path)

        # If it was triggered purely to authenticate the user session, stop here:
        if is_interactive and urls and "m-meine-anzeigen.html" in urls[0]:
            logger.info("Interactive manual login session validated successfully.")
            return []

        # Otherwise perform Selenium index scraping:
        all_scraped_listings = []
        total_pages = len(urls) * PAGES_TO_SCRAPE
        current_page_idx = 0

        for base_url in urls:
            for page in range(1, PAGES_TO_SCRAPE + 1):
                current_page_idx += 1
                update_progress(
                    "discovery",
                    current_page_idx - 1,
                    total_pages,
                    f"Discovering listings on page {page} of {PAGES_TO_SCRAPE}...",
                )
                if page == 1:
                    current_url = base_url
                else:
                    if "/seite:" in base_url:
                        current_url = re.sub(
                            r"/seite:\d+(/|$)", f"/seite:{page}\\1", base_url
                        )
                    else:
                        parts = base_url.split("/")
                        domain_part = "/".join(parts[:3])
                        path_part = parts[3]
                        remaining_parts = "/".join(parts[4:]) if len(parts) > 4 else ""
                        current_url = (
                            f"{domain_part}/{path_part}/seite:{page}/{remaining_parts}"
                        )

                logger.info(
                    f"[Selenium] Scraping page {page} of {PAGES_TO_SCRAPE}: {current_url}"
                )
                driver.get(current_url)

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "srchrslt-adtable"))
                    )
                except TimeoutException:
                    logger.error("[Selenium] Timeout waiting for page to load")
                    continue

                existing_listings = []
                existing_ids = set()
                if output_file and os.path.exists(output_file):
                    try:
                        with open(output_file, "r", encoding="utf-8") as f:
                            existing_listings = json.load(f)
                            existing_ids = {
                                item.get("id", "") for item in existing_listings
                            }
                    except Exception:
                        pass

                scraped_count = 0
                for parsed in result_list.parse(driver.page_source):
                    if (
                        max_listings is not None
                        and len(all_scraped_listings) >= max_listings
                    ):
                        break

                    listing_id = parsed["id"]
                    if listing_id in existing_ids:
                        continue

                    listing = result_list.as_db_listing(parsed)
                    existing_listings.append(listing)
                    existing_ids.add(listing_id)
                    all_scraped_listings.append(listing)
                    scraped_count += 1

                    if output_file:
                        with open(output_file, "w", encoding="utf-8") as f:
                            json.dump(
                                existing_listings, f, ensure_ascii=False, indent=4
                            )

                logger.info(
                    f"[Selenium] Scraped {scraped_count} listings from {current_url}"
                )
                if page < PAGES_TO_SCRAPE:
                    time.sleep(DELAY_BETWEEN_PAGES)

        return all_scraped_listings
    finally:
        driver.quit()
