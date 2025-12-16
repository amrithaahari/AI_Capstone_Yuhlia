# intents.py
from typing import Literal, Tuple

Intent = Literal[
    "beginner_guidance",
    "capital_preservation",
    "crypto_curious",
    "theme_curious",
    "unknown",
]

def classify_intent(text: str) -> Tuple[Intent, float, str]:
    """
    Returns (intent, confidence 0..1, rationale).
    v1: rules. v2: LLM or embedding classifier.
    """
    t = (text or "").lower()

    # crypto
    if any(k in t for k in ["crypto", "bitcoin", "btc", "ethereum", "eth", "solana"]):
        return "crypto_curious", 0.95, "mentions crypto keywords"

    # themes
    if any(k in t for k in ["theme", "thematic", "ai", "robotics", "clean energy", "tech"]):
        return "theme_curious", 0.8, "mentions thematic investing keywords"

    # capital preservation
    if any(k in t for k in ["safe", "low risk", "don't lose", "capital preservation", "preserve", "stable", "etf"]):
        return "capital_preservation", 0.75, "mentions safety / low risk language"

    # beginner
    if any(k in t for k in ["beginner", "new to investing", "how do i start", "basics", "not sure"]):
        return "beginner_guidance", 0.7, "beginner phrasing"

    # sustainable
    if any(k in t for k in ["not defense", "sustainable", "esg"]):
        return "beginner_guidance", 0.7, "mentions sustainability"

    if len(t.strip()) < 8:
        return "unknown", 0.0, "too little information"

    return "unknown", 0.35, "no strong signals"
