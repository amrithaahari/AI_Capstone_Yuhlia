"""
Data models and schemas for Yulia Assistant
"""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ClassificationResult:
    """Result from intent classification"""
    category: str
    confidence: float
    reasoning: str

@dataclass
class Product:
    """Product from database"""
    product_id: int
    name: str
    description: str
    sector: Optional[str]
    currency: Optional[str]
    region: Optional[str]
    esg_score: Optional[str]
    ter: Optional[float]

@dataclass
class GuardrailResult:
    """Result from guardrail check"""
    passed: bool
    reason: Optional[str]

@dataclass
class ConversationState:
    """Tracks the current conversation state"""
    original_goal: str
    followup_count: int
    followup_answers: List[str]
    last_intent: Optional[str]
    last_confidence: Optional[float]

@dataclass
class ProcessingResult:
    """Result from processing a user message"""
    type: str  # 'followup', 'success', 'mismatch', 'guardrail_failure'
    message: str
    products: Optional[List[Product]] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    retries: int = 0