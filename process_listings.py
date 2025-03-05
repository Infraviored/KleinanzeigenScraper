import os
import json
import time
import datetime
import shutil
from openai import OpenAI
from config import API_KEY

# Instantiate the OpenAI client
client = OpenAI(api_key=API_KEY)

# Set to True to print the prompt sent to the LLM
PRINT_PROMPT = False

def process_listing(title, description):
    """Send the listing title and description to ChatGPT and process the response."""
    prompt = (
        "Carefully analyze the following product listing to extract specific technical information. First, think through your reasoning step by step, then provide your final answers in the specified format.\n\n"
        
        "1. RAM size: Scan for RAM/memory information.\n"
        "   - First, search for any mention of RAM, memory, GB, or similar terms\n"
        "   - Determine the exact RAM size if possible\n"
        "   - If you can confirm RAM is 32GB or more: 'RAM_more = true'\n"
        "   - If you can confirm RAM is less than 32GB: 'RAM_more = false'\n"
        "   - If RAM size is not mentioned: 'RAM_more = unknown'\n\n"
        
        "2. Screen size: Look for screen diagonal measurement.\n"
        "   - Search for terms like screen, display, monitor followed by inch/\", or size indicators\n"
        "   - Determine the exact screen size if possible\n"
        "   - If you can confirm screen is 14 inches or smaller: 'screen_small = true'\n"
        "   - If you can confirm screen is larger than 14 inches: 'screen_small = false'\n"
        "   - If screen size is not mentioned: 'screen_small = unknown'\n\n"
        
        "3. Screen resolution: Check for resolution information.\n"
        "   - Look for terms like resolution, pixels, HD, FHD, QHD, UHD, or specific dimensions like 1920x1080\n"
        "   - Determine the exact resolution if possible\n"
        "   - If you can confirm resolution is higher than Full HD (1920x1080): 'screen_highres = true'\n"
        "   - If you can confirm resolution is Full HD or lower: 'screen_highres = false'\n"
        "   - If screen resolution is not mentioned: 'screen_highres = unknown'\n\n"
        
        "First, write out your thought process for each question. Explain what information you found or didn't find in the listing and how you reached your conclusion.\n\n"
        
        "After your reasoning, provide your final answers in this exact format:\n"
        "RAM_more = [true/false/unknown]\n"
        "screen_small = [true/false/unknown]\n"
        "screen_highres = [true/false/unknown]\n"
        "full_info_obtained = [true/false]\n\n"
        
        "Remember: If ALL three questions have 'true' or 'false' answers (no 'unknown'), then 'full_info_obtained = true'. If ANY question has an 'unknown' answer, then 'full_info_obtained = false'.\n\n"
        
        "Example input:\n"
        "Title: Gaming Laptop Lenovo Loq i5-13450hx rtx 4060 2tb 32gb ram\n"
        "Description: ich verkaufe hier mein lenovo loq Gaming Laptop.\nDie technischen Daten sind folgende:\nI5-13450hx\nRtx 4060\n32gb ram\n2 * 1tb ssd\nFullhd Display\nDas Netzteil ist mit dabei.\nAlles funktioniert einwandfrei.\nBei Fragen oder Interesse schreiben Sie mich gerne an\n"
        
        "Example thought process:\n"
        "RAM: I can see '32gb ram' mentioned in both the title and description. This is exactly 32GB, which meets the threshold of '32GB or more'. Therefore, RAM_more = true.\n\n"
        "Screen size: I've searched the title and description for any mention of screen size in inches or similar measurements. There is no specific mention of the screen diagonal size (like 13\", 14\", 15.6\", etc.). Without this information, I cannot determine if the screen is 14 inches or smaller, or larger than 14 inches. Therefore, screen_small = unknown.\n\n"
        "Screen resolution: The description mentions 'Fullhd Display'. Full HD refers to a resolution of 1920x1080 pixels. Since the question asks if the resolution is higher than Full HD, and this is exactly Full HD, the answer is screen_highres = false.\n\n"
        "Since one of the questions (screen size) has an 'unknown' answer, full_info_obtained = false.\n\n"
        
        "Example output:\n"
        "RAM_more = true\n"
        "screen_small = unknown\n"
        "screen_highres = false\n"
        "full_info_obtained = false\n\n"
        
        "Now please analyze the following listing:\n"
        
        f"Title: {title}\n\n"
        f"Description: {description}\n\n"
        
        "Remember to first show your reasoning process for each question, and then provide your final answers in the exact format specified."
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
            max_tokens=500  # Increased to ensure we get the full response
        )

        # Extract the response text
        response_text = response.choices[0].message.content.strip()
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
            print("Warning: Could not parse the model's response properly.")
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
        print(f"Error processing listing: {str(e)}")
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
        print(f"Input file not found: {input_file}")
        return
    
    # Create a backup of the original file before making any changes
    backup_file = input_file + ".backup"
    try:
        shutil.copy2(input_file, backup_file)
        print(f"Created backup of original file at {backup_file}")
    except Exception as e:
        print(f"Warning: Could not create backup file: {str(e)}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            listings = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Could not parse input file {input_file}.")
        return
    
    # Count total and unprocessed listings
    total_listings = len(listings)
    unprocessed_listings = sum(1 for listing in listings if not listing.get('llm_processed', False))
    
    print(f"\nTotal listings: {total_listings}")
    print(f"Unprocessed listings: {unprocessed_listings}")
    print(f"Already processed: {total_listings - unprocessed_listings}")
    
    if unprocessed_listings == 0:
        print("All listings have already been processed. Nothing to do.")
        return
    
    print(f"\nStarting processing of {unprocessed_listings} listings...")
    
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
            print(f"\n{separator_line}")
            print(f"Processing {title} ({processed_count+1}/{unprocessed_listings})")
            print(f"{separator_line}")
            
            # Pass both title and description to the process_listing function
            chatgpt_results = process_listing(title, listing["detailed_description"])
            listing.update(chatgpt_results)
            processed_count += 1
            
            # Write the updated listings back to the file after each processing
            try:
                # Write to a temporary file first
                temp_file = input_file + ".temp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(listings, f, ensure_ascii=False, indent=4)
                
                # Replace the original file with the temporary file
                os.replace(temp_file, input_file)
                
                print(f"Updated listing saved to {input_file}: {title} (ID: {listing_id})")
            except Exception as e:
                print(f"Error saving updates: {str(e)}")
                print("Continuing with next listing...")
    
    print(f"\nProcessing completed. Processed {processed_count} out of {unprocessed_listings} unprocessed listings.")
    
    # Remove the backup file if everything went well
    try:
        if os.path.exists(backup_file):
            user_input = input(f"Processing completed successfully. Remove backup file {backup_file}? (y/n): ")
            if user_input.lower() == 'y':
                os.remove(backup_file)
                print("Backup file removed.")
            else:
                print("Backup file kept for reference.")
    except Exception as e:
        print(f"Note: Could not remove backup file: {str(e)}")

if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    input_file = os.path.join(data_dir, "listings.json")
    
    update_listings_with_chatgpt(input_file)