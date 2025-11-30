import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    WINDOWS_HOST = os.environ.get("WINDOWS_HOST")
    
    # Constants
    POLL_INTERVAL_FAST = 2
    POLL_INTERVAL_SLOW = 10
    AI_UPDATE_INTERVAL = 120
    LOL_API_PORT = 2999
