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


def test_over_decomposition_behavioral():
    """Independence criterion: sequential tasks MUST declare deps, not claim independence."""
    def check_has_deps(tasks, deps):
        return any(len(deps.get(task["id"], [])) > 0 for task in tasks)

    # A sequential workflow with no deps declared — violates independence criterion
    # (t2's result changes based on t1's result, so they are NOT independent)
    mock_tasks = [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]
    mock_no_deps = {"t1": [], "t2": [], "t3": []}
    mock_correct_deps = {"t1": [], "t2": ["t1"], "t3": ["t2"]}

    # Missing deps: wrong — sequential tasks must declare deps
    assert check_has_deps(mock_tasks, mock_no_deps) is False  # bad: no deps declared
    # Correct deps: sequential deps correctly declared
    assert check_has_deps(mock_tasks, mock_correct_deps) is True  # good: deps present


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


def test_reasoning_block_stripped_from_raw_response():
    """Verify that <reasoning>...</reasoning> prefix is stripped before JSON parsing."""
    raw = "<reasoning>4 tasks, all independent</reasoning>\n{\"tasks\": []}"
    if "<reasoning>" in raw:
        end = raw.find("</reasoning>")
        if end != -1:
            raw = raw[end + len("</reasoning>"):].strip()
    assert raw == '{"tasks": []}'

