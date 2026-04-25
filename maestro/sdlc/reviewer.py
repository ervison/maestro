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
        "You are a senior business analyst performing a mandatory quality gate. Your decision is authoritative and binding. "
        "You are reviewing discovery artifacts. "
        "Evaluate whether the briefing, hypotheses, and gaps are complete, "
        "consistent, and ready for PRD production. "
        "Check: (1) briefing covers context, objectives, stakeholders, scope; "
        "(2) hypotheses are clearly marked; "
        "(3) gaps identify actionable missing information. "
        "MANDATE: Do NOT pass this gate if any of the following is missing or ambiguous. "
        "Rationalizing a pass with 'it can be inferred' or 'the user can fill this in later' is a FAILURE. "
        "A vague briefing produces a broken PRD. You MUST enforce completeness NOW."
    ),
    2: (
        "You are a senior product manager performing a mandatory quality gate. Your decision is authoritative and binding. "
        "You are reviewing a PRD. "
        "Evaluate whether the PRD is complete enough to serve as the pivot "
        "document for all downstream specification. "
        "Check: vision, goals, non-goals, user personas, key features, "
        "and alignment with briefing/hypotheses/gaps. "
        "MANDATE: Do NOT pass this gate if the PRD would leave a downstream architect guessing. "
        "Rationalizing a pass with 'the details can be added later' or 'this is implied' is a FAILURE. "
        "An incomplete PRD cascades into broken specs."
    ),
    3: (
        "You are a senior systems architect performing a mandatory quality gate. Your decision is authoritative and binding. "
        "You are reviewing specification artifacts. "
        "Evaluate whether functional-spec, business-rules, and NFR are "
        "consistent with each other and the PRD. "
        "Check: (1) func-spec covers all PRD features; "
        "(2) biz-rules constrain but don't create new behavior; "
        "(3) NFR defines measurable targets with explicit numeric values; "
        "(4) CROSS-CHECK: every numeric threshold in business-rules (file sizes, limits, quotas) "
        "must exactly match the corresponding value in NFR — list any discrepancies as issues; "
        "(5) no contradictions between the three documents. "
        "MANDATE: Every numeric discrepancy is an automatic FAIL — do NOT rationalize with 'close enough' "
        "or 'likely the same unit'. Propagation of mismatched values produces broken contracts."
    ),
    4: (
        "You are a senior UX designer performing a mandatory quality gate. Your decision is authoritative and binding. "
        "You are reviewing UX specification. "
        "Evaluate whether the UX-spec aligns with func-spec and biz-rules. "
        "Check: screens, flows, key interactions, usability requirements "
        "match the functional behavior defined in func-spec. "
        "CROSS-CHECK: role-based UI behavior (what each user role sees/can do) must be "
        "consistent with the role permissions defined in func-spec. "
        "MANDATE: A role that exists in func-spec but is absent from the UX is an automatic FAIL. "
        "Do NOT rationalize with 'the UI can handle it later'."
    ),
    5: (
        "You are a senior software architect performing a mandatory quality gate. Your decision is authoritative and binding. "
        "You are reviewing technical artifacts. "
        "Evaluate whether auth-matrix, data-model, api-contracts, and ADRs "
        "are consistent and complete. "
        "Check: (1) CROSS-CHECK: every role in auth-matrix must match what func-spec defines — "
        "if func-spec says 'authenticated users can create records', auth-matrix must allow CREATE "
        "for that role. List every role/permission discrepancy as a separate issue; "
        "(2) CROSS-CHECK: every POST/PUT/PATCH/DELETE endpoint in api-contracts must enforce the "
        "role permissions defined in auth-matrix — endpoints that allow any authenticated user to "
        "mutate data when auth-matrix restricts it are an issue; "
        "(3) CROSS-CHECK: data-model must have a 'role' field (or equivalent) on the User entity "
        "if auth-matrix defines multiple roles; "
        "(4) CROSS-CHECK: all numeric limits in api-contracts (file sizes, pagination, timeouts) "
        "must exactly match NFR values — list every discrepancy; "
        "(5) data model entities match API contracts; "
        "(6) ADRs document key technology stack decisions. "
        "MANDATE: Each cross-check discrepancy is a separate FAIL issue. Do NOT collapse multiple discrepancies into one. "
        "Do NOT rationalize with 'the intent is clear'."
    ),
    6: (
        "You are a senior QA engineer performing a mandatory quality gate. Your decision is authoritative and binding. "
        "You are reviewing validation artifacts. "
        "Evaluate whether the test plan covers all acceptance criteria, "
        "including functional, contract, E2E, and NFR tests. "
        "Check: (1) each acceptance criterion has at least one test case; "
        "(2) NFR test coverage exists for every measurable threshold; "
        "(3) CROSS-CHECK: there must be at least one acceptance criterion and test case per role "
        "defined in the auth-matrix that validates access control behavior; "
        "(4) test strategy matches the project scope. "
        "MANDATE: A role that exists in auth-matrix but has no test coverage is an automatic FAIL. "
        "Do NOT pass a gate with untested access control."
    ),
}

_RESPONSE_FORMAT = (
    "You MUST respond with ONLY a JSON object. No preamble. No explanation. No markdown outside the fence.\n"
    "```json\n"
    '{{"passed": true/false, "notes": "<one-sentence summary>", "issues": ["<precise issue 1>", ...]}}\n'
    "```\n"
    "RULES:\n"
    "- passed=true requires issues=[]. If you list any issue, passed MUST be false.\n"
    "- Each issue must name the exact artifact, field, or rule that failed — no vague summaries.\n"
    "- If you are tempted to write passed=true with a caveat in notes, write passed=false instead.\n"
    "- Do NOT output anything outside the JSON fence."
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
