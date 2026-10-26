"""Phase 1 runner: Regulation → Risk extraction."""

from __future__ import annotations

import re
from typing import Callable

from schemas import make_id, make_row_id
from prompts.phase_1 import build_phase_1_prompt
from llm_client import generate_json, get_model
from config import (
    RISK_ID_PREFIX,
    INPUT_RISK_MAPPING_PREFIX,
    SEVERITY_OPTIONS,
    RISK_CATEGORIES,
    MAX_OUTPUT_TOKENS_PHASE_1,
)

_VALID_SEVERITIES = {s.lower(): s for s in SEVERITY_OPTIONS}
_VALID_CATEGORIES = {c.lower(): c for c in RISK_CATEGORIES}


def _merge_key(risk_statement: str) -> str:
    """Normalized key for dedup: the 'Failure to X' part (same obligation = same key)."""
    s = risk_statement.strip().lower()
    # "failure to ... may result in ..." -> take the obligation part, collapse spaces
    m = re.match(r"failure to\s+(.+?)\s+may result in", s, re.DOTALL)
    if m:
        core = re.sub(r"\s+", " ", m.group(1).strip())[:100]
        return core
    return re.sub(r"\s+", " ", s)[:100]


def _quote_key(quote: str) -> str:
    """Normalized key for quote-based dedup: lowercased, collapsed whitespace, truncated so similar quotes match."""
    if not quote or not quote.strip():
        return ""
    s = re.sub(r"\s+", " ", quote.strip().lower())
    return s[:300] if len(s) > 300 else s


def _deduplicate_risks(risks: list[dict]) -> list[dict]:
    """Merge risks that express the same obligation (e.g. same theme from different chunks)."""
    if not risks:
        return risks
    # Don't dedup error rows
    error_key = "[error processing chunk"
    groups: dict[str, list[dict]] = {}
    for r in risks:
        stmt = r.get("risk_statement", "")
        if stmt.lower().startswith(error_key):
            groups[f"__error_{id(r)}"] = [r]
            continue
        key = _merge_key(stmt)
        if key not in groups:
            groups[key] = []
        groups[key].append(r)
    out: list[dict] = []
    for group in groups.values():
        first = group[0].copy()
        if len(group) > 1:
            refs = [r.get("source_ref", "").strip() for r in group if r.get("source_ref")]
            quotes = [r.get("source_quote", "").strip() for r in group if r.get("source_quote")]
            seen_ref: set[str] = set()
            seen_quote: set[str] = set()
            ref_parts = [r for r in refs if r and r not in seen_ref and (seen_ref.add(r) or True)]
            quote_parts = [q for q in quotes if q and q not in seen_quote and (seen_quote.add(q) or True)]
            first["source_ref"] = "; ".join(ref_parts) if ref_parts else first.get("source_ref", "")
            first["source_quote"] = " | ".join(quote_parts[:2]) if quote_parts else first.get("source_quote", "")
        out.append(first)
    return out


def _deduplicate_by_quote(risks: list[dict]) -> list[dict]:
    """Keep one risk per similar source_quote; drop later duplicates to remove citation duplication."""
    if not risks:
        return risks
    error_key = "[error processing chunk"
    seen_quote_key: set[str] = set()
    out: list[dict] = []
    for r in risks:
        stmt = r.get("risk_statement", "")
        if stmt.strip().lower().startswith(error_key):
            out.append(r)
            continue
        q = r.get("source_quote", "") or ""
        key = _quote_key(q)
        if not key:
            out.append(r)
            continue
        if key in seen_quote_key:
            continue
        seen_quote_key.add(key)
        out.append(r)
    return out


def _normalise_severity(raw: str) -> str:
    return _VALID_SEVERITIES.get(raw.strip().lower(), "Medium")


def _normalise_category(raw: str) -> str:
    low = raw.strip().lower()
    for key, canonical in _VALID_CATEGORIES.items():
        if key in low or low in key:
            return canonical
    return "Other"


def run_phase_1(
    chunks: list[dict],
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Process regulatory document chunks and extract risks.

    Chunks are already in memory (from upload); no file I/O here.
    One LLM call is made per chunk, so runtime scales with chunk count.

    Args:
        chunks: list of chunk dicts from ingestion (each has 'text', 'source_name', etc.)
        progress_callback: optional (chunk_index, total_chunks) called after each chunk.

    Returns:
        list of RiskEntry-compatible dicts with assigned IDs.
    """
    all_risks: list[dict] = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        source_name = chunk.get("source_name", "")
        prompt = build_phase_1_prompt(chunk["text"], source_filename=source_name)
        try:
            raw_results = generate_json(
                prompt, model=get_model("phase_1"), max_tokens=MAX_OUTPUT_TOKENS_PHASE_1
            )
        except (ValueError, ConnectionError) as e:
            all_risks.append({
                "input_risk_mapping_id": "",
                "source_document": source_name,
                "source_ref": "",
                "requirement_theme": "",
                "risk_id": "",
                "risk_statement": f"[ERROR processing chunk {chunk.get('chunk_index', '?')}] {e}",
                "risk_category": "Other",
                "severity": "Medium",
                "why_identified": "LLM extraction failed for this chunk",
                "source_quote": "",
                "user_status": "Proposed",
                "user_notes": None,
            })
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        if isinstance(raw_results, dict):
            raw_results = [raw_results]

        for item in raw_results:
            statement = item.get("risk_statement", "").strip()
            if not statement:
                continue

            risk = {
                "input_risk_mapping_id": "",
                "source_document": item.get("source_document", source_name),
                "source_ref": item.get("source_ref", ""),
                "requirement_theme": item.get("requirement_theme", ""),
                "risk_id": "",
                "risk_statement": statement,
                "risk_category": _normalise_category(item.get("risk_category", "")),
                "severity": _normalise_severity(item.get("severity", "")),
                "why_identified": item.get("why_identified", ""),
                "source_quote": item.get("source_quote", ""),
                "user_status": "Proposed",
                "user_notes": None,
            }
            all_risks.append(risk)

        if progress_callback:
            progress_callback(i + 1, total)

    # Merge duplicate obligations across chunks (same "Failure to X" = one canonical risk)
    all_risks = _deduplicate_risks(all_risks)
    # Drop risks with duplicate/similar source_quote (keep first occurrence per quote)
    all_risks = _deduplicate_by_quote(all_risks)

    for i, risk in enumerate(all_risks, start=1):
        risk["risk_id"] = make_id(RISK_ID_PREFIX, i)
        risk["input_risk_mapping_id"] = make_row_id(INPUT_RISK_MAPPING_PREFIX, i)

    return all_risks
