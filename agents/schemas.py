"""Pydantic output schemas for Elder Shield agents.

Used as output_schema on ADK agents for structured, validated output.
Eliminates manual JSON parsing — ADK enforces these shapes natively.
"""

from typing import Literal

from pydantic import BaseModel, Field


class FinancialMention(BaseModel):
    amount: str = ""
    urgency: Literal["low", "medium", "high"] = "low"


class ExtractedFacts(BaseModel):
    claimed_name: str | None = None
    claimed_relationship: str | None = None
    claimed_location: str | None = None
    claimed_institution: str | None = None
    referenced_names: list[str] = Field(default_factory=list)
    financial_mention: FinancialMention | None = None
    life_facts: list[str] = Field(default_factory=list)
    matched_existing: list[str] = Field(default_factory=list)


class ClassificationResult(BaseModel):
    """Inbound Classifier output — per-message classification."""
    classification: Literal["safe", "suspicious", "scam", "spam"]
    confidence: float = Field(ge=0.0, le=1.0)
    detected_signals: list[str] = Field(default_factory=list)
    extracted_facts: ExtractedFacts = Field(default_factory=ExtractedFacts)
    reasoning: str = ""


class RiskAssessment(BaseModel):
    """Behavioral Analyzer output — longitudinal risk assessment."""
    sender_id: str
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_factors: list[str] = Field(default_factory=list)
    recommendation: Literal["safe", "monitor", "flag", "block", "alert_family"] = "safe"
    behavioral_velocity: dict | None = None
    abuse_indicators: dict | None = None
    contradiction_details: list[dict] = Field(default_factory=list)


class InterceptDecision(BaseModel):
    """Outbound Interceptor output — hold-or-release decision."""
    decision: Literal["release", "warn", "hold", "hard_hold"]
    signals: list[str] = Field(default_factory=list)
    victim_state_signals: list[str] = Field(default_factory=list)
    compound_risk: float = Field(ge=0.0, le=1.0, default=0.0)
    victim_falling: bool = False
    hold_id: str | None = None
    reason: str = ""


class AlertRecord(BaseModel):
    """Family Alerter output — alert generation result."""
    alert_id: str = ""
    alert_type: str = ""
    severity: Literal["info", "warning", "critical"] = "info"
    status: Literal["delivered", "dedup", "rate_limited", "pending"] = "pending"
    subject_ja: str = ""
    subject_en: str = ""
