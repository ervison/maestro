## SECURITY REVIEW — Phase 07: GitHub Copilot Provider

**Phase:** 07 — github-copilot-provider
**ASVS Level:** 1

Summary
-------
This document records the verification of the threat mitigations declared in
the phase plan (.planning/phases/07-github-copilot-provider/07-01-PLAN.md).

Threat Model Extract (from PLAN.md)
----------------------------------
- T-07-01 — Spoofing — OAuth device code URL — mitigate
- T-07-02 — Tampering — Access token storage — mitigate
- T-07-03 — Information Disclosure — Token in logs — mitigate
- T-07-04 — Denial of Service — Infinite polling — mitigate
- T-07-05 — Elevation of Privilege — Scope creep — accept

Verification Results
--------------------

All threats declared in the PLAN.md threat model were verified against the
implementation and supporting auth module. Each entry below lists the
expected mitigation and the concrete evidence found in the codebase.

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-07-01 | Spoofing | mitigate | Hardcoded GitHub OAuth and API endpoints defined in maestro/providers/copilot.py:28-33 (CLIENT_ID, DEVICE_CODE_URL, ACCESS_TOKEN_URL, COPILOT_API_BASE) — no dynamic URL composition from user input. |
| T-07-02 | Tampering | mitigate | Token storage performed via auth.set("github-copilot", ...) in maestro/providers/copilot.py:298; auth._write_store writes files with secure mode 0o600 in maestro/auth.py:64-68. |
| T-07-03 | Information Disclosure | mitigate | Implementation avoids logging secrets: copilot.py uses logger.debug for flow state only (examples: maestro/providers/copilot.py:276, 282, 299) and never logs the access_token value. No occurrences of logging access tokens were found in the Copilot provider implementation. |
| T-07-04 | Denial of Service | mitigate | Device-code polling enforces a deadline/timeout: expires_in default 900s and deadline calculation in maestro/providers/copilot.py:244-256 and loop condition using deadline at 254-259. Polling respects interval + POLLING_SAFETY_MARGIN. |
| T-07-05 | Elevation of Privilege | accept | Accepted risk recorded below (see "Accepted Risks"). The plan documents the reduced scope (read:user) as the rationale. |

Threat Flags from SUMMARY.md
---------------------------
The phase SUMMARY (`07-01-SUMMARY.md`) contains a "Threat Surface Scan" that reports "None" — no additional threat flags were raised during implementation. Therefore there are no unregistered threat flags to log for this phase.

Notes, Review Findings, and Fixes
--------------------------------
During code review two warnings and one informational issue were raised (see .planning/phases/07-github-copilot-provider/07-REVIEW.md):
- WR-01: SSE path did not fail fast on non-2xx responses — fixed in the implementation by checking the SSE response status and raising on non-success (maestro/providers/copilot.py:136-141).
- WR-02: is_authenticated() previously reported true for unusable credential blobs — fixed by validating access_token presence (maestro/providers/copilot.py:305-308).
- IN-01: Unused helper _parse_tool_call_delta() removed (refactor/fix applied).

Those review findings were addressed and a short fix report is in 07-REVIEW-FIX.md. The changes are visible in the current implementation and the mitigations described in the plan remain present after the fixes.

Accepted Risks Log
------------------
T-07-05 (Elevation of Privilege — Scope creep): ACCEPTED

Rationale: The plan explicitly uses the minimal OAuth scope (read:user) and documents that this token cannot be used to escalate privileges. The product decision to accept this residual risk is recorded in the original threat register (PLAN.md). Acceptance is logged here so it is discoverable during security audits and release reviews.

Action items / Recommendations
-----------------------------
- Validate the CLIENT_ID against the real GitHub OAuth App before production rollout (research note in .planning/research/STACK.md). This is already listed as a research flag in the project's research docs.
- Consider adding telemetry/alerts for repeated slow_down or access_denied responses to detect automated abuse or misconfiguration during device-code polling.
- Ensure CI does not accidentally capture tokens in test logs — tests included in the phase mock external HTTP responses, but maintainers should verify test logs in CI runs.

Summary counts
--------------
- Total threats in PLAN.md: 5
- Closed (mitigated or accepted and recorded): 5/5
- Open threats: 0

SECURITY review file path: .planning/phases/07-github-copilot-provider/SECURITY.md
