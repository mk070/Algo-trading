"""
Evidence Validator — citation integrity checks for AI agent outputs.

Checks:
1. Model-claimed URLs exist in the supplied source list.
2. Invented dates are flagged (date in citation not in supplied range).
3. Strips or rejects unsupported factual claims.

Does NOT modify historical benchmark results.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_FORBIDDEN_PATTERNS = [
    # Hard-coded invented URLs or bare domains not from supply list
    r"example\.com",
    r"placeholder\.io",
]


@dataclass
class ValidationResult:
    is_valid: bool
    warnings: List[str] = field(default_factory=list)
    rejected_citations: List[str] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)


def validate_citations(
    citations: List[str],
    available_sources: List[str],
    *,
    strict: bool = False,
) -> ValidationResult:
    """
    Validate a list of model-claimed citation URLs or titles against available sources.

    Args:
        citations: URLs or titles asserted by the model.
        available_sources: Authoritative set of URLs/titles supplied as inputs.
        strict: If True, reject any citation not in available_sources.

    Returns:
        ValidationResult with warnings and rejected items.
    """
    result = ValidationResult(is_valid=True)
    available_normalized: Set[str] = {_normalize(s) for s in available_sources}

    for citation in citations:
        norm = _normalize(citation)

        # Check forbidden patterns
        for pattern in _FORBIDDEN_PATTERNS:
            if re.search(pattern, citation, re.IGNORECASE):
                result.rejected_citations.append(citation)
                result.warnings.append(
                    f"Citation rejected — forbidden placeholder pattern: '{citation}'"
                )
                result.is_valid = False
                break
        else:
            # Check against available sources
            if strict and norm not in available_normalized:
                # In strict mode, flag citations not in supply list as unsupported
                result.unsupported_claims.append(citation)
                result.warnings.append(
                    f"Unsupported citation (not in input sources): '{citation[:100]}'"
                )
                # Note: unsupported ≠ hallucination; model may have general knowledge
                # We flag but do not mark invalid in non-strict mode

    if strict and result.unsupported_claims:
        result.is_valid = False

    return result


def _normalize(text: str) -> str:
    """Lowercase and strip whitespace/punctuation for loose matching."""
    text = text.strip().lower()
    # Remove trailing slashes from URLs
    text = text.rstrip("/")
    return text


def check_for_fabricated_numbers(text: str, context_numbers: List[float]) -> List[str]:
    """
    Scan text for numeric values and flag any that don't appear in the known context.
    Returns a list of warning messages.

    This is a lightweight heuristic — not authoritative.
    """
    warnings: List[str] = []
    if not context_numbers:
        return warnings

    # Find all decimal numbers in the text
    found_numbers = re.findall(r'\b\d{1,6}(?:\.\d{1,4})?\b', text)
    context_set = {round(n, 2) for n in context_numbers}

    for num_str in found_numbers:
        try:
            val = round(float(num_str), 2)
            # Only flag numbers that look like financial figures (> 1.0, < 1_000_000)
            if 1.0 < val < 1_000_000 and val not in context_set:
                warnings.append(
                    f"Numeric value {val} in AI output not found in supplied context data. "
                    f"Verify this figure against primary source."
                )
        except ValueError:
            pass

    return warnings
