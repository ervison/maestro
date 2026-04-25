"""SDLC Reviewer — LLM-based gate validation between sprints."""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from maestro.sdlc.schemas import (
    GateResult,
    SDLCArtifact,
)


GATE_PROMPTS: dict[int, str] = {
    1: (
        "You are a senior business analyst reviewing discovery artifacts. "
        "Evaluate whether the briefing, hypotheses, and gaps are complete, "
        "consistent, and ready for PRD production. "
        "Check: (1) briefing covers context, objectives, stakeholders, scope; "
        "(2) hypotheses are clearly marked; "
        "(3) gaps identify actionable missing information. "
    ),
    2: (
        "You are a senior product manager reviewing a PRD. "
        "Evaluate whether the PRD is complete enough to serve as the pivot "
        "document for all downstream specification. "
        "Check: vision, goals, non-goals, user personas, key features, "
        "and alignment with briefing/hypotheses/gaps. "
    ),
    3: (
        "You are a senior systems architect reviewing specification artifacts. "
        "Evaluate whether functional-spec, business-rules, and NFR are "
        "consistent with each other and the PRD. "
        "Check: (1) func-spec covers all PRD features; "
        "(2) biz-rules constrain but don't create new behavior; "
        "(3) NFR defines measurable targets; "
        "(4) no contradictions between the three. "
    ),
    4: (
        "You are a senior UX designer reviewing UX specification. "
        "Evaluate whether the UX-spec aligns with func-spec and biz-rules. "
        "Check: screens, flows, key interactions, usability requirements "
        "match the functional behavior defined in func-spec. "
    ),
    5: (
        "You are a senior software architect reviewing technical artifacts. "
        "Evaluate whether auth-matrix, data-model, api-contracts, and ADRs "
        "are consistent and complete. "
        "Check: (1) auth permissions reflected in API operations; "
        "(2) data model entities match API contracts; "
        "(3) ADRs document key decisions; "
        "(4) NFR targets are addressed in API and data design. "
    ),
    6: (
        "You are a senior QA engineer reviewing validation artifacts. "
        "Evaluate whether the test plan covers all acceptance criteria, "
        "including functional, contract, E2E, and NFR tests. "
        "Check: (1) each acceptance criterion has at least one test case; "
        "(2) NFR test coverage exists; "
        "(3) test strategy matches the project scope. "
    ),
}

_RESPONSE_FORMAT = (
    "Respond ONLY with a JSON object in this exact format:\n"
    "```json\n"
    '{{"passed": true/false, "notes": "<summary>", "issues": ["<issue1>", ...]}}\n'
    "```\n"
    "If passed is true, issues must be empty. If passed is false, list each issue.\n"
    "Do not include any text outside the JSON block."
)


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM response. Handles nested fences and trailing prose.

    Strategy: prefer the *last* ```json ... ``` fence (LLMs sometimes echo the
    request format before producing the real answer); fall back to last
    ``` ... ``` fence; finally try the raw text.
    """
    # Prefer the last json-tagged fence
    json_fences = re.findall(r"```json\s*([\s\S]*?)```", text)
    if json_fences:
        return json.loads(json_fences[-1].strip())
    # Any code fence, last one
    any_fences = re.findall(r"```\s*([\s\S]*?)```", text)
    if any_fences:
        return json.loads(any_fences[-1].strip())
    return json.loads(text.strip())


class Reviewer:
    """LLM-based gate reviewer for sprint quality gates."""

    async def review(
        self,
        provider: Any,
        model: str | None,
        sprint_id: int,
        artifacts: list[SDLCArtifact],
        prior_artifacts: list[SDLCArtifact] | None = None,
    ) -> GateResult:
        """Run a gate review for a sprint's artifacts.

        Args:
            provider: LLM provider with stream() method.
            model: Model name to use.
            sprint_id: Sprint number (1-6).
            artifacts: Artifacts produced in this sprint.
            prior_artifacts: Artifacts from previous sprints (for cross-reference).

        Returns:
            GateResult with passed/failed status and notes.
        """
        gate_prompt = GATE_PROMPTS.get(sprint_id, "Review the following artifacts for quality and consistency. ")

        artifacts_section = "\n\n".join(
            f"=== {a.filename} ===\n{a.content}" for a in artifacts
        )

        prior_section = ""
        if prior_artifacts:
            prior_section = "\n\n## Prior Artifacts (for cross-reference)\n" + "\n\n".join(
                f"=== {a.filename} ===\n{a.content}" for a in prior_artifacts
            )

        full_prompt = (
            f"{gate_prompt}\n\n"
            f"## Sprint {sprint_id} Artifacts\n{artifacts_section}"
            f"{prior_section}\n\n{_RESPONSE_FORMAT}"
        )

        from maestro.providers.base import Message

        messages = [Message(role="user", content=full_prompt)]
        parts: list[str] = []
        async for msg in provider.stream(messages, tools=None, model=model):
            if isinstance(msg, str):
                parts.append(msg)
            elif hasattr(msg, "role") and msg.role == "assistant" and msg.content:
                parts = [msg.content]

        response_text = "".join(parts).strip()

        try:
            data = _extract_json(response_text)
            passed = bool(data.get("passed", False))
            notes = str(data.get("notes", ""))
            issues = [str(i) for i in data.get("issues", [])]
            return GateResult(sprint_id=sprint_id, passed=passed, notes=notes, issues=issues)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(
                f"[reviewer] Gate {sprint_id}: malformed response ({exc}), failing gate",
                file=sys.stderr,
            )
            return GateResult(
                sprint_id=sprint_id,
                passed=False,
                notes=f"Malformed reviewer response: {exc}",
                issues=["Reviewer returned invalid JSON"],
            )
