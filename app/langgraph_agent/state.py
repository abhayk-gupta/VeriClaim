"""
Shared state object that flows through the claim-analysis graph.

Every node receives the current `ClaimState` and returns a partial dict that
LangGraph merges in. All fields are optional (`total=False`) because each node
populates only its own slice; the initial state is built by
`graph.build_initial_state()` from the DB record.
"""
from __future__ import annotations

from typing import TypedDict, Optional, Any


class ClaimState(TypedDict, total=False):
    # ── Identity / inputs (set at build time) ──────────────────────────────────
    claim_id: str
    order_id: str
    customer_id: str
    customer_phone: str
    claim_type: str                  # ClaimType value
    policy_id: str
    order_external: str              # human-facing order number (for messages)
    product_description: str
    order_value_usd: float
    delivered_at: Optional[str]      # ISO timestamp or None
    claim_created_at: Optional[str]  # ISO timestamp
    clarification_count: int
    customer_phone: Optional[str]    # for outbound clarification calls
    verbal_description: Optional[str]  # voice transcript / clarification answers

    # Permanent media keys (R2 / Redis) — never the expiring CDN URL
    media_r2_key_item: Optional[str]
    media_r2_key_label: Optional[str]

    # Raw bytes loaded by ingest_media
    item_image: bytes
    label_image: Optional[bytes]

    # ── Gemini vision results (analyze_image) ──────────────────────────────────
    gemini_item_description: str
    gemini_damage_type: str
    gemini_damage_severity: str      # none | minor | moderate | severe
    gemini_label_match: bool
    gemini_confidence: float
    gemini_anomalies: list[str]
    gemini_assessment: str

    # ── Policy check (verify_policy) ───────────────────────────────────────────
    policy_verdict: str              # ELIGIBLE | INELIGIBLE | BORDERLINE
    policy_reasons: list[str]

    # ── Fraud check (fraud_check) ──────────────────────────────────────────────
    fraud_score: float
    fraud_signals: dict[str, Any]

    # ── Decision (decide_outcome) ──────────────────────────────────────────────
    decision: str                    # replacement | refund | rejection | escalate | clarify
    outcome: Optional[str]           # ClaimOutcome value
    final_status: str                # ClaimStatus value
    agent_reasoning: str

    # ── Control ────────────────────────────────────────────────────────────────
    error: Optional[str]
