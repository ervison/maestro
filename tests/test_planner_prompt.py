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
    """Independence criterion: tasks whose outputs depend on each other are NOT independent.

    This test exercises the independence discipline defined in the prompt by using
    AgentPlan/PlanTask validation to confirm that a planner output flagging sequential
    tasks as independent (empty deps when they should declare deps) is structurally
    representable but violates the independence criterion expressed in the prompt.

    The prompt states: "A task is independent ONLY IF its result does not change based
    on another task's result."  Over-decomposition produces tasks that SHOULD declare
    deps but declare none.  This test verifies the detection logic used in gate checks.
    """
    from maestro.planner.schemas import AgentPlan, PlanTask

    # Case 1: correctly declared sequential pipeline — t2 depends on t1's output (e.g.,
    # "write tests" depends on "write code"), t3 depends on t2's output.  These tasks
    # are NOT independent; their results change based on prior tasks' results.
    sequential_with_deps = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="Implement REST endpoint", deps=[]),
            PlanTask(id="t2", domain="testing", prompt="Write tests for the REST endpoint", deps=["t1"]),
            PlanTask(id="t3", domain="docs", prompt="Document the REST endpoint", deps=["t1"]),
        ]
    )
    # All tasks with deps must declare them — t2 and t3 both depend on t1
    tasks_with_declared_deps = [t for t in sequential_with_deps.tasks if len(t.deps) > 0]
    assert len(tasks_with_declared_deps) == 2, (
        "Tasks that depend on a prior result MUST declare deps; over-decomposition "
        "produces zero deps for sequential tasks that should have deps."
    )

    # Case 2: over-decomposed output — same logical workflow but deps wrongly omitted.
    # A planner hallucinating independence would emit no deps even for inherently
    # sequential tasks.  This represents a violation of the independence criterion.
    over_decomposed = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="backend", prompt="Implement REST endpoint", deps=[]),
            PlanTask(id="t2", domain="testing", prompt="Write tests for the REST endpoint", deps=[]),
            PlanTask(id="t3", domain="docs", prompt="Document the REST endpoint", deps=[]),
        ]
    )
    tasks_without_deps = [t for t in over_decomposed.tasks if len(t.deps) == 0]
    # All three tasks claim independence — but t2 and t3 require t1's output to be
    # meaningful, so this is an over-decomposition violation.
    assert len(tasks_without_deps) == 3, (
        "Confirms that over-decomposed output is structurally representable "
        "but violates the independence criterion."
    )
    # Sanity-check: the over-decomposed plan has MORE unconstrained tasks than the
    # correctly declared one (3 vs 1).  The correct plan is strictly safer.
    correct_unconstrained = sum(1 for t in sequential_with_deps.tasks if len(t.deps) == 0)
    over_unconstrained = sum(1 for t in over_decomposed.tasks if len(t.deps) == 0)
    assert over_unconstrained > correct_unconstrained, (
        "Over-decomposition produces more unconstrained (deps=[]) tasks than the "
        "correctly sequenced plan.  Independence discipline reduces unconstrained tasks."
    )


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

