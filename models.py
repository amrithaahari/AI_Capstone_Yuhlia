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
    sector: Optional[str]
    currency: Optional[str]
    region: Optional[str]
    esg: Optional[str]
    ter: Optional[float]

@dataclass
class GuardrailResult:
    passed: bool
    reason: Optional[str] = None
    severity: str = "none"  # "none" | "minor" | "fail"
    category: str = "none"  # "none" | "advice" | "instructions" | "prediction" | "recommendation_wording" | "risk_free_claim"

@dataclass
class ConversationState:
    goal: str = ""
    awaiting_followup: bool = False
    followup_count: int = 0
    followup_answers: List[str] = field(default_factory=list)
    last_followup_key: Optional[str] = None
    last_intent: Optional[str] = None
    last_confidence: Optional[float] = None

@dataclass
class ProcessingResult:
    type: str  # followup, success, mismatch, guardrail_failure
    message: str
    products: Optional[List[Product]] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    retries: int = 0
    responses: List[str] = None