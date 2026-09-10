API_KEY = "YOUR_API_KEY"

# LLM provider endpoint. Any OpenAI-compatible chat-completions endpoint works.
# Leave as None to use OpenAI directly, or point at a gateway, e.g.
#   "https://openrouter.ai/api/v1"
API_BASE_URL = None

# Scraping settings
MAX_LISTINGS_PER_PAGE = 50
DELAY_BETWEEN_PAGES = 2
DELAY_BETWEEN_LISTINGS = 2

# LLM settings
# Examples: "gpt-4o-mini", "deepseek/deepseek-v4-flash-0731" (via OpenRouter)
LLM_MODEL = "gpt-4o-mini"
PRINT_PROMPT = False

PAGES_TO_SCRAPE = 2
