def get_laptop_analysis_prompt(title, description):
    """Returns the prompt for analyzing laptop listings"""
    return (
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