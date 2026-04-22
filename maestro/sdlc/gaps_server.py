"""Gaps questionnaire server - parser support for [GAP] items."""
from __future__ import annotations

import re

from maestro.sdlc.schemas import GapItem

_DEFAULT_OPTIONS: list[str] = [
    "Yes",
    "No",
    "Not decided yet",
    "Other (specify in notes)",
]


def parse_gaps(gaps_markdown: str) -> list[GapItem]:
    """Extract ``[GAP]`` questions from generated gaps markdown."""
    items: list[GapItem] = []
    for line in gaps_markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("[GAP]"):
            continue

        question = stripped[len("[GAP]") :].strip()
        if not question:
            continue

        items.append(
            GapItem(
                question=question,
                options=_infer_options(question),
                recommended_index=0,
            )
        )

    return items


def _infer_options(question: str) -> list[str]:
    """Heuristically derive answer options from question text."""
    q_lower = question.lower()

    paren_match = re.search(r"\(([^)]+)\)", question)
    if paren_match:
        inner = paren_match.group(1)
        parts = [
            part.strip().rstrip("?")
            for part in re.split(r"\s+or\s+", inner, flags=re.IGNORECASE)
        ]
        if len(parts) >= 2:
            return parts + ["Needs discussion", "Not applicable"]

    yes_no_keywords = (
        "is ",
        "are ",
        "will ",
        "should ",
        "does ",
        "do ",
        "has ",
        "have ",
        "can ",
        "must ",
    )
    if any(q_lower.startswith(keyword) for keyword in yes_no_keywords):
        return ["Yes", "No", "Needs discussion", "Not applicable"]

    if any(
        keyword in q_lower
        for keyword in ("how many", "how much", "count", "number", "volume", "scale")
    ):
        return ["< 1,000 / month", "1,000-100,000 / month", "> 100,000 / month", "Unknown / TBD"]

    if any(
        keyword in q_lower
        for keyword in ("audience", "user", "customer", "persona", "target")
    ):
        return ["B2C consumers", "B2B companies", "Internal teams", "Mixed / TBD"]

    return _DEFAULT_OPTIONS.copy()
