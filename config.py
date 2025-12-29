# config.py
"""
Configuration constants for Yulia Assistant
"""
from enum import Enum

# Limits
MAX_GUARDRAIL_RETRIES = 3

LLM_ENABLED = True

# Database
DATABASE_NAME = "yuh_products.db"
TOP_K_PRODUCTS = 5


class Intent(str, Enum):
    yuh_related = "yuh_related"
    basic_knowledge = "basic_knowledge"
    unknown = "unknown"


INTENT_LABELS = {
    Intent.yuh_related: "Yuh / in-app availability",
    Intent.basic_knowledge: "Investing basics / concepts",
    Intent.unknown: "Unknown / unrelated",
}

# Keep suggested prompts aligned to the new intents and answer-first behavior
SUGGESTED_PROMPTS = [
    "What's an ETF?",
    "How do fees affect returns?",
    "Does yuh have index funds?",
    "What investment options are available on yuh?",
]
