import os
import json
import datetime
import logging
from openai import OpenAI
from config import API_KEY, LLM_MODEL, PRINT_PROMPT
from prompts import get_laptop_analysis_prompt

# Set up logging
logger = logging.getLogger(__name__)

# Instantiate the OpenAI client
client = OpenAI(api_key=API_KEY)

def process_listing(title, description):
    """Send the listing title and description to ChatGPT and process the response."""
    # Get the prompt from the prompts module
    prompt = get_laptop_analysis_prompt(title, description)
    
    if PRINT_PROMPT:
        print("\nPrompt sent to LLM:")
        print("-" * 40)
        print(prompt)
        print("-" * 40)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500  # Increased to ensure we get the full response
        )

        # Extract the response text
        response_text = response.choices[0].message.content.strip()
        logger.info(f"Received LLM response for: {title}")
        
        if PRINT_PROMPT:
            print(f"\nModel response: {response_text}")  # Log the model's response for debugging

        # Parse the response to extract the values
        ram_more = None
        screen_small = None
        screen_highres = None
        full_info_obtained = None
        
        # Look for the specific format lines in the response
        for line in response_text.split('\n'):
            line = line.strip().lower()  # Convert to lowercase for easier matching
            
            if line.startswith("ram_more ="):
                if "true" in line:
                    ram_more = True
                elif "false" in line:
                    ram_more = False
                elif "unknown" in line:
                    ram_more = "unknown"  # Explicitly set to "unknown" string
                
            elif line.startswith("screen_small ="):
                if "true" in line:
                    screen_small = True
                elif "false" in line:
                    screen_small = False
                elif "unknown" in line:
                    screen_small = "unknown"  # Explicitly set to "unknown" string
                
            elif line.startswith("screen_highres ="):
                if "true" in line:
                    screen_highres = True
                elif "false" in line:
                    screen_highres = False
                elif "unknown" in line:
                    screen_highres = "unknown"  # Explicitly set to "unknown" string
                
            elif line.startswith("full_info_obtained ="):
                if "true" in line:
                    full_info_obtained = True
                elif "false" in line:
                    full_info_obtained = False
        
        # If we couldn't parse the values properly, set defaults
        if ram_more is None and screen_small is None and screen_highres is None and full_info_obtained is None:
            logger.warning(f"Could not parse the model's response properly for: {title}")
            return {
                "llm_processed": True,
                "llm_processed_time": datetime.datetime.now().isoformat(),
                "full_info_obtained": False,
                "RAM_more": "unknown",
                "screen_small": "unknown",
                "screen_highres": "unknown"
            }
        
        # If full_info_obtained wasn't explicitly set, calculate it
        if full_info_obtained is None:
            # If any value is "unknown", full_info_obtained should be False
            full_info_obtained = (ram_more is not None and ram_more != "unknown" and 
                                 screen_small is not None and screen_small != "unknown" and 
                                 screen_highres is not None and screen_highres != "unknown")

        # Add timestamp to the results
        return {
            "llm_processed": True,
            "llm_processed_time": datetime.datetime.now().isoformat(),
            "full_info_obtained": full_info_obtained if full_info_obtained is not None else False,
            "RAM_more": ram_more if ram_more is not None else "unknown",
            "screen_small": screen_small if screen_small is not None else "unknown",
            "screen_highres": screen_highres if screen_highres is not None else "unknown"
        }

    except Exception as e:
        logger.error(f"Error processing listing with LLM: {str(e)}")
        return {
            "llm_processed": False,
            "llm_processed_time": datetime.datetime.now().isoformat(),
            "full_info_obtained": False,
            "RAM_more": "unknown",
            "screen_small": "unknown",
            "screen_highres": "unknown"
        }

def update_listings_with_chatgpt(input_file):
    """Read listings from a JSON file, process them with ChatGPT, and update the file in place."""
    if not os.path.exists(input_file):
        logger.error(f"Input file not found: {input_file}")
        return
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            listings = json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Error: Could not parse input file {input_file}.")
        return
    
    # Count total and unprocessed listings
    total_listings = len(listings)
    unprocessed_listings = sum(1 for listing in listings if not listing.get('llm_processed', False))
    
    logger.info(f"Total listings: {total_listings}")
    logger.info(f"Unprocessed listings: {unprocessed_listings}")
    logger.info(f"Already processed: {total_listings - unprocessed_listings}")
    
    if unprocessed_listings == 0:
        logger.info("All listings have already been processed. Nothing to do.")
        return
    
    logger.info(f"Starting processing of {unprocessed_listings} listings...")
    
    # Track how many listings we've processed in this run
    processed_count = 0
    
    # Process each listing
    for i, listing in enumerate(listings):
        listing_id = listing.get('id')
        title = listing.get('title', 'Unknown Title')
        
        # Skip if already processed
        if listing.get('llm_processed', False):
            continue
        
        if "detailed_description" in listing and listing["detailed_description"]:
            # Display nice separated headline
            separator_line = "-" * 70
            logger.info(f"{separator_line}")
            logger.info(f"Processing {title} ({processed_count+1}/{unprocessed_listings})")
            logger.info(f"{separator_line}")
            
            # Pass both title and description to the process_listing function
            chatgpt_results = process_listing(title, listing["detailed_description"])
            listing.update(chatgpt_results)
            processed_count += 1
            
            # Write the updated listings back to the file after each processing
            try:
                with open(input_file, 'w', encoding='utf-8') as f:
                    json.dump(listings, f, ensure_ascii=False, indent=4)
                
                logger.info(f"Updated listing saved to {input_file}: {title} (ID: {listing_id})")
            except Exception as e:
                logger.error(f"Error saving updates: {str(e)}")
                logger.info("Continuing with next listing...")
    
    logger.info(f"Processing completed. Processed {processed_count} out of {unprocessed_listings} unprocessed listings.")

if __name__ == "__main__":
    # Set up logging when run as a standalone script
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    input_file = os.path.join(data_dir, "listings.json")
    
    update_listings_with_chatgpt(input_file)