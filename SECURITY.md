## SECURED

**Phase:** 6 — auth-model-cli-commands
**Threats Closed:** 3/3
**ASVS Level:** not specified

### Threat Verification
| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-06-01 | Spoofing | accept | SECURITY.md: Accepted risks log entry for T-06-01 (this file) and `.planning/phases/06-auth-model-cli-commands/06-01-SUMMARY.md:167-171` documents provider validation on logout |
| T-06-02 | Information Disclosure | mitigate | `maestro/cli.py:141-149` — auth status prints only provider IDs and "authenticated/not authenticated"; no credential contents printed; covered by `tests/test_cli_auth.py` |
| T-06-03 | Tampering | existing | `maestro/auth.py:66-69` and `tests/test_auth_store.py:36-82` — auth store written with secure create mode `os.open(..., 0o600)` and `AUTH_FILE.chmod(0o600)` enforced |

### Unregistered Flags
None. No `## Threat Flags` were present in the Phase 06 summary.

## Accepted Risks

| Threat ID | Rationale | Recorded In |
|-----------|-----------|-------------|
| T-06-01 | Provider ID spoofing is accepted for this phase because provider IDs are validated against the discovered registry and unknown IDs are rejected with a helpful error. Operational risk accepted to preserve UX for multi-provider workflows. | `.planning/phases/06-auth-model-cli-commands/06-01-SUMMARY.md:167-171` and this SECURITY.md |
