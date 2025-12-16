"""
Configuration constants for Yulia Assistant
"""
from enum import Enum

# Thresholds and limits
CONFIDENCE_THRESHOLD = 0.7
MAX_FOLLOWUP_QUESTIONS = 2
MAX_GUARDRAIL_RETRIES = 3
TOP_K_PRODUCTS = 5

# Database
DATABASE_NAME = "yuh_products.db"

class Intent(str, Enum):
    beginner = "beginner"
    capital_preservation = "capital_preservation"
    unknown = "unknown"

INTENT_LABELS = {
    Intent.beginner: "Beginner",
    Intent.capital_preservation: "Capital preservation",
    Intent.unknown: "Unknown",
}

# Follow-up questions (decision-based, minimal)
FOLLOWUP_QUESTIONS = [
    ("goal_type", "Are you mainly looking to learn the basics, or to explore more conservative, lower-volatility options?"),
    ("time_horizon", "Is this for money you might need in the next 1–3 years, or longer term?"),
]

SUGGESTED_PROMPTS = [
    "I'm new to investing and want to learn the basics",
    "I want to preserve my capital with minimal risk",
    "What investment options are available on yuh?",
]
