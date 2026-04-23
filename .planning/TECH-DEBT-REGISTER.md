# Maestro - Tech Debt Register

Last updated: 2026-04-23

This register tracks post-roadmap work that is still worth doing even though Phases 1-13 are complete.

## Prioritized Register

| Priority | ID | Debt | Owner | Effort | Why it matters | Evidence |
|----------|----|------|-------|--------|----------------|----------|
| P1 | TD-03 | Add an automated planning-artifact consistency check so `ROADMAP.md`, `STATE.md`, milestone summaries, and requirements snapshots cannot drift silently. | Planning Maintainer | S | The project already had roadmap/state drift across Phases 1, 2, 7, and 12. Preventing recurrence is cheaper than another manual reconciliation pass. | `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/reports/MILESTONE_SUMMARY-v1.1.md` |
| P1 | TD-04 | Add a real third-party provider installation smoke test for `maestro.providers` entry points (`pip install` / isolated env). | Provider Platform Owner | M | `importlib.metadata` wiring is implemented, but the external package contract is still validated mainly by local/static evidence rather than an end-to-end install test. | `.planning/v1.0-MILESTONE-AUDIT.md` (PROV-05, Phase 4 human-needed note) |
| P2 | TD-05 | Add a release-grade Copilot provider smoke check or documented manual gate for real OAuth device-code login and live API use. | Provider/Auth Owner | M | Copilot is implemented and verified in tests, but the most user-sensitive path still relies on manual real-account verification. | `.planning/phases/07-github-copilot-provider/07-VERIFICATION.md` |
| P2 | TD-06 | Add spend/rate limiting controls around optional aggregator LLM calls. | Multi-Agent Runtime Owner | M | Aggregation is optional, but repeated calls can create avoidable cost or abuse risk in unattended usage. | `.planning/phases/11-aggregator-multi-agent-cli/11-SECURITY.md` |
| P3 | TD-02 | Implement the optional recursive sub-planner worker path behind the existing depth guard. | Orchestration Owner | L | The depth-guard infrastructure exists, but recursive decomposition is still deferred. This is product expansion rather than a blocker. | `.planning/v1.0-MILESTONE-AUDIT.md` |

## Sequencing Recommendation

1. TD-03 first, because it prevents planning metadata from drifting again.
2. TD-04 next, because it validates the external provider plugin contract promised by the architecture.
3. TD-05 and TD-06 after that, depending on whether provider reliability or multi-agent runtime hardening is more urgent.
4. TD-02 last, because it is explicitly optional and not required for current roadmap completeness.

## Ownership Notes

- Planning Maintainer: whoever owns `.planning/` artifact generation and milestone closeout.
- Provider Platform Owner: whoever owns `maestro/providers/`, `pyproject.toml`, and plugin-discovery behavior.
- Provider/Auth Owner: whoever owns OAuth flows and provider login UX.
- Multi-Agent Runtime Owner: whoever owns `maestro/multi_agent.py` and aggregator runtime policy.
- Orchestration Owner: whoever owns planner/worker execution model evolution.
