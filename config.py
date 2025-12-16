"""
Configuration constants for Yulia Assistant
"""

from enum import Enum

# Thresholds and limits
CONFIDENCE_THRESHOLD = 0.7
MAX_FOLLOWUP_QUESTIONS = 2
MAX_GUARDRAIL_RETRIES = 5
TOP_K_PRODUCTS = 5

# Database
DATABASE_NAME = 'yuh_products.db'

# Intent categories
class Intent(str, Enum):
    BEGINNER = "Beginner"
    CAPITAL_PRESERVATION = "capital_preservation"
    UNKNOWN = "Unknown"

# Follow-up question templates
FOLLOWUP_QUESTIONS = {
    "experience": "To help you better, could you tell me about your experience with investing? Are you just starting out, or do you have some experience already?",
    "goals": "What are your main investment goals? For example, are you looking to grow your wealth over time, preserve your capital, or something else?",
    "risk": "How do you feel about investment risk? Are you comfortable with potential ups and downs, or do you prefer more stable options?",
    "timeframe": "Are you thinking about investing for the short term (a few years) or the long term (many years)?",
}

# Suggested prompts for UI
SUGGESTED_PROMPTS = [
    "I'm new to investing and want to learn the basics",
    "I want to preserve my capital with minimal risk",
    "What investment options are available on yuh?",
]
