"""Pydantic models for the governance register at each phase."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Phase 1 – Risk Register
# ---------------------------------------------------------------------------

class RiskEntry(BaseModel):
    """Single risk extracted from a regulatory / policy document."""

    input_risk_mapping_id: str = Field(default="", description="UI_001 style row ID")
    source_document: str = Field(default="", description="File name or source name")
    source_ref: str = Field(default="", description="Section / page / clause")
    requirement_theme: str = Field(default="", description="Short theme label")
    risk_id: str = Field(default="", description="RISK-001 style")
    risk_statement: str = Field(..., description="Failure to … may result in …")
    risk_category: str = Field(default="Other", description="Standardized risk category")
    severity: str = Field(..., description="High / Medium / Low")
    why_identified: str = Field(..., description="Rationale tied to source")
    source_quote: str = Field(default="", description="Supporting excerpt from source")
    user_status: str = Field(default="Proposed", description="Proposed / Approved / Rejected / Edited")
    user_notes: Optional[str] = Field(default=None, description="Optional reviewer notes")


# ---------------------------------------------------------------------------
# Phase 2 – Risk-Control Matrix
# ---------------------------------------------------------------------------

class RiskControlEntry(BaseModel):
    """One risk-to-control mapping row."""

    risk_control_mapping_id: str = Field(default="", description="RC_001 style")
    input_risk_mapping_id: str = Field(default="", description="References Phase 1 row")
    risk_id: str
    risk_statement: str
    control_id: str = Field(default="", description="From control inventory, e.g. CTRL-001")
    control_description: str = Field(default="", description="Control wording from inventory")
    why_control_assigned: str = Field(default="", description="Mitigation rationale")
    control_type: str = Field(default="", description="Preventive / Detective / Corrective")
    execution_type: str = Field(default="", description="Manual / Automated / Hybrid")
    user_status: str = Field(default="Proposed", description="Proposed / Approved / Rejected / Edited")
    user_notes: Optional[str] = Field(default=None, description="Optional reviewer notes")


# ---------------------------------------------------------------------------
# Phase 3 – Control-to-Process Map
# ---------------------------------------------------------------------------

class GovernanceEntry(BaseModel):
    """One control-to-process mapping row."""

    control_process_mapping_id: str = Field(default="", description="CP_001 style")
    risk_control_mapping_id: str = Field(default="", description="References Phase 2 row")
    control_id: str
    control_description: str = Field(default="", description="Approved control wording")
    process_id: str = Field(default="", description="From process source, e.g. PROC-001")
    process_name: str = Field(default="", description="Business process name")
    process_step: str = Field(default="", description="Specific operational step")
    why_process_assigned: str = Field(default="", description="Operational rationale")
    user_status: str = Field(default="Proposed", description="Proposed / Approved / Rejected / Edited")
    user_notes: Optional[str] = Field(default=None, description="Optional reviewer notes")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_id(prefix: str, index: int) -> str:
    """Generate a zero-padded ID like RISK-001, CTRL-012."""
    return f"{prefix}-{index:03d}"


def make_row_id(prefix: str, index: int) -> str:
    """Generate a row ID like UI_001, RC_001, CP_001."""
    return f"{prefix}_{index:03d}"


def deduplicate_governance_entries(
    entries: list[GovernanceEntry],
) -> list[GovernanceEntry]:
    """Remove exact duplicate rows based on the full control+process tuple."""
    seen: set[tuple] = set()
    unique: list[GovernanceEntry] = []
    for e in entries:
        key = (e.control_id, e.process_id, e.process_step)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique
