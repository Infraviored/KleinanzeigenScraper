import os
import json
from openai import OpenAI
from config import API_KEY

# Instantiate the OpenAI client
client = OpenAI(api_key=API_KEY)

# Set to True to print the prompt sent to the LLM
PRINT_PROMPT = True

def process_listing(title, description):
    """Send the listing title and description to ChatGPT and process the response."""
    prompt = (
        "Analyze the following product listing and determine the following information:\n"
        "1. Is the RAM size 32 gigabytes or more? Respond with 'RAM_more = true' or 'RAM_more = false'.\n"
        "2. Is the screen diagonal 14 inches or less? Respond with 'screen_small = true' or 'screen_small = false'.\n"
        "3. Is the screen resolution more than Full HD? Respond with 'screen_highres = true' or 'screen_highres = false'.\n\n"
        f"Title: {title}\n\n"
        f"Description: {description}\n\n"
        "If all these can be determined, respond with 'full_info_obtained = true'. Otherwise, respond with 'full_info_obtained = false'."
    )
    
    if PRINT_PROMPT:
        print("\nPrompt sent to LLM:")
        print("-" * 40)
        print(prompt)
        print("-" * 40)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use the appropriate model name
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150
        )

        # Extract the response text
        response_text = response.choices[0].message.content.strip()
        print(f"\nModel response: {response_text}")  # Log the model's response for debugging

        # Determine the flags based on the response
        full_info_obtained = "full_info_obtained = true" in response_text
        RAM_more = "RAM_more = true" in response_text
        screen_small = "screen_small = true" in response_text
        screen_highres = "screen_highres = true" in response_text

        return {
            "llm_processed": True,
            "full_info_obtained": full_info_obtained,
            "RAM_more": RAM_more,
            "screen_small": screen_small,
            "screen_highres": screen_highres
        }

    except Exception as e:
        print(f"Error processing listing: {str(e)}")
        return {
            "llm_processed": False,
            "full_info_obtained": False,
            "RAM_more": False,
            "screen_small": False,
            "screen_highres": False
        }

def update_listings_with_chatgpt(input_file, output_file):
    """Read listings from a JSON file, process them with ChatGPT, and update the file."""
    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}")
        return
    
    # Check if output file exists to avoid reprocessing
    existing_listings = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                # Create a dictionary with id as key for quick lookup
                existing_listings = {item.get('id'): item for item in existing_data if item.get('id')}
        except json.JSONDecodeError:
            print(f"Warning: Could not parse existing output file {output_file}. Will create a new one.")
            existing_listings = {}
    
    with open(input_file, 'r', encoding='utf-8') as f:
        listings = json.load(f)
    
    # Track if any changes were made
    changes_made = False
    
    for listing in listings:
        listing_id = listing.get('id')
        title = listing.get('title', 'Unknown Title')
        
        # Skip if already processed
        if (listing_id in existing_listings and 
            existing_listings[listing_id].get('llm_processed', False)):
            print(f"Skipping already processed listing: {title} (ID: {listing_id})")
            continue
        
        if "detailed_description" in listing and listing["detailed_description"]:
            # Display nice separated headline
            separator_line = "-" * 70
            print(f"\n{separator_line}")
            print(f"Processing {title}")
            print(f"{separator_line}")
            
            # Pass both title and description to the process_listing function
            chatgpt_results = process_listing(title, listing["detailed_description"])
            listing.update(chatgpt_results)
            changes_made = True
            
            # If the listing exists in the output file, update it there too
            if listing_id in existing_listings:
                existing_listings[listing_id].update(chatgpt_results)
    
    # Determine which data to save
    output_data = list(existing_listings.values()) if existing_listings else listings
    
    # Only write to file if changes were made
    if changes_made:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        print(f"\nUpdated listings saved to {output_file}")
    else:
        print("\nNo new listings to process. Output file remains unchanged.")

if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    input_file = os.path.join(data_dir, "listings.json")
    output_file = os.path.join(data_dir, "listings_updated.json")
    
    update_listings_with_chatgpt(input_file, output_file)