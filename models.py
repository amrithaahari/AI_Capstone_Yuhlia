# models.py
"""
Data models and schemas for Yulia Assistant
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    reasoning: str


@dataclass
class Product:
    id: int
    name: str
    description: str
    sector: Optional[str] = None
    currency: Optional[str] = None
    region: Optional[str] = None
    esg: Optional[str] = None
    ter: Optional[float] = None


@dataclass
class GuardrailResult:
    passed: bool
    reason: Optional[str] = None
    severity: str = "none"  # "none" | "minor" | "fail"
    category: str = "none"  # "none" | "advice" | "instructions" | "prediction" | "recommendation_wording" | "risk_free_claim"


@dataclass
class ConversationState:
    # Keep minimal state for now. Multi-turn follow-ups are intentionally disabled.
    goal: str = ""
    last_intent: Optional[str] = None
    last_confidence: Optional[float] = None


@dataclass
class ProcessingResult:
    type: str  # success | unknown | guardrail_failure | error
    message: str
    products: Optional[List[Product]] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    retries: int = 0
    responses: List[str] = field(default_factory=list)
    guardrail: Optional[dict] = None
