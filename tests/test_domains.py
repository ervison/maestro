"""Tests for domain system."""

import pytest

from maestro.domains import DOMAINS, DEFAULT_DOMAIN, get_domain_prompt, list_domains


# Expected domains per D-06 from CONTEXT.md
EXPECTED_DOMAINS = {
    "backend",
    "testing",
    "docs",
    "devops",
    "general",
    "security",
    "data",
}


def test_all_expected_domains_exist():
    """All 7 required domains are defined."""
    assert set(DOMAINS.keys()) == EXPECTED_DOMAINS


def test_default_domain_is_general():
    """DEFAULT_DOMAIN constant is 'general'."""
    assert DEFAULT_DOMAIN == "general"


@pytest.mark.parametrize("domain", EXPECTED_DOMAINS)
def test_get_domain_prompt_returns_prompt(domain):
    """get_domain_prompt returns a non-empty string for each domain."""
    prompt = get_domain_prompt(domain)
    assert isinstance(prompt, str)
    assert len(prompt) > 50  # prompts should be substantial


def test_get_domain_prompt_falls_back_to_general():
    """Unknown domains fall back to 'general' prompt without error."""
    unknown_prompt = get_domain_prompt("unknown_domain_xyz")
    general_prompt = DOMAINS["general"]
    assert unknown_prompt == general_prompt


def test_fallback_does_not_raise():
    """Fallback works silently, no exception."""
    # Should not raise any exception
    result = get_domain_prompt("nonexistent")
    assert result is not None


@pytest.mark.parametrize("domain", EXPECTED_DOMAINS)
def test_domain_prompt_mentions_working_directory(domain):
    """Each domain prompt instructs writing to shared workdir (per DOM-04)."""
    prompt = get_domain_prompt(domain)
    assert "working directory" in prompt.lower()


def test_list_domains_returns_all():
    """list_domains returns all 7 domain names."""
    domains = list_domains()
    assert set(domains) == EXPECTED_DOMAINS


def test_domain_prompts_are_distinct():
    """Each domain has a unique prompt (except possibly similar structure)."""
    prompts = [DOMAINS[d] for d in EXPECTED_DOMAINS - {"general"}]
    # Non-general domains should have unique first lines (different focus)
    first_lines = [p.split("\n")[0] for p in prompts]
    assert len(first_lines) == len(set(first_lines))


@pytest.mark.parametrize("domain", ["backend", "testing", "docs", "devops", "security"])
def test_specialized_domains_have_stay_within_instruction(domain):
    """Specialized domains instruct workers to stay within their concern."""
    prompt = get_domain_prompt(domain)
    assert "stay within" in prompt.lower() or "focus on" in prompt.lower()


def test_general_domain_is_catch_all():
    """General domain has broader scope than specialized domains."""
    general_prompt = get_domain_prompt("general")
    # General should not have "stay within" restriction
    assert "stay within" not in general_prompt.lower()


@pytest.mark.parametrize("domain", EXPECTED_DOMAINS)
def test_domain_prompt_not_empty(domain):
    """No domain prompt is empty or whitespace-only."""
    prompt = get_domain_prompt(domain)
    assert prompt.strip()


def test_get_domain_prompt_case_sensitive():
    """Domain lookup is case-sensitive (unknown case falls back to general)."""
    # "Backend" (capitalized) should fall back to general
    result = get_domain_prompt("Backend")
    assert result == DOMAINS["general"]
