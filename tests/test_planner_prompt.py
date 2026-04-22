"""Unit tests for the hardened PLANNER_SYSTEM_PROMPT in maestro/planner/node.py.

These tests verify that the prompt contains all required authority language,
structural elements (rationalization table, independence criterion, reasoning
block instruction), and that no softening language has leaked back in.
"""

from maestro.planner.node import PLANNER_SYSTEM_PROMPT


def test_prompt_contains_must():
    assert "MUST" in PLANNER_SYSTEM_PROMPT


def test_prompt_contains_must_not():
    assert "MUST NOT" in PLANNER_SYSTEM_PROMPT


def test_prompt_contains_rationalization_table():
    assert "Rationalization" in PLANNER_SYSTEM_PROMPT


def test_prompt_contains_independence_criterion():
    assert (
        "A task is independent ONLY IF its result does not change based on another task's result."
        in PLANNER_SYSTEM_PROMPT
    )


def test_prompt_contains_reasoning_block_instruction():
    assert "<reasoning>" in PLANNER_SYSTEM_PROMPT


def test_prompt_forbids_softening_language():
    softening_words = ["prefer", "Prefer", "try to", "Try to", "consider", "Consider", "generally", "Generally"]
    found = [word for word in softening_words if word in PLANNER_SYSTEM_PROMPT]
    assert found == [], f"Softening language found in prompt: {found}"


def test_prompt_requires_dependencies_for_non_independent_tasks():
    """The prompt must explicitly define the independence criterion and forbid treating
    dependent tasks as independent.

    This validates the prompt contract: tests in test_planner_node.py exercise the
    planner_node runtime; this file validates prompt content only.
    """
    assert (
        "A task is independent ONLY IF its result does not change based on another task's result."
        in PLANNER_SYSTEM_PROMPT
    )
    assert "deps" in PLANNER_SYSTEM_PROMPT
    assert "independent" in PLANNER_SYSTEM_PROMPT
    assert "MUST" in PLANNER_SYSTEM_PROMPT


def test_prompt_rationalization_row_shared_context():
    assert "shared context" in PLANNER_SYSTEM_PROMPT.lower()


def test_prompt_rationalization_row_domain_boundary():
    assert "domain" in PLANNER_SYSTEM_PROMPT.lower()


def test_prompt_rationalization_row_uncertainty():
    assert "uncertainty" in PLANNER_SYSTEM_PROMPT.lower() or "uncertain" in PLANNER_SYSTEM_PROMPT.lower()


def test_prompt_rationalization_row_cleanliness():
    assert "cleanliness" in PLANNER_SYSTEM_PROMPT.lower() or "clean" in PLANNER_SYSTEM_PROMPT.lower()


def test_prompt_rationalization_verdicts_present():
    assert "MERGE" in PLANNER_SYSTEM_PROMPT


def test_prompt_cycle_prohibition():
    assert "cyclic" in PLANNER_SYSTEM_PROMPT.lower() or "cycle" in PLANNER_SYSTEM_PROMPT.lower()


def test_prompt_reasoning_block_close_tag():
    assert "</reasoning>" in PLANNER_SYSTEM_PROMPT


def test_prompt_output_only_json_after_reasoning():
    assert "ONLY the JSON" in PLANNER_SYSTEM_PROMPT or "only the JSON" in PLANNER_SYSTEM_PROMPT


def test_prompt_contains_catch_all_rule():
    assert any(phrase in PLANNER_SYSTEM_PROMPT for phrase in ["not exhaustive", "any split", "Any split"])


def test_prompt_requires_reasoning_block_before_json_output():
    """The prompt must instruct the model to output a <reasoning> block followed by JSON only."""
    assert "<reasoning>" in PLANNER_SYSTEM_PROMPT
    assert "</reasoning>" in PLANNER_SYSTEM_PROMPT
    assert "ONLY the JSON" in PLANNER_SYSTEM_PROMPT or "only the JSON" in PLANNER_SYSTEM_PROMPT

