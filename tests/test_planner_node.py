"""Tests for planner node with mocked provider."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from maestro.planner import AgentState, AgentPlan, PlanTask, planner_node, PLANNER_SYSTEM_PROMPT
from maestro.providers.base import Message


def _make_valid_plan_dict() -> dict:
    """Return a minimal valid plan dict."""
    return {
        "tasks": [
            {
                "id": "t1",
                "domain": "backend",
                "prompt": "Write a simple API endpoint",
                "deps": []
            }
        ]
    }


def _make_plan_with_cycle() -> dict:
    """Return a plan with a cyclic dependency (t1 depends on t2, t2 depends on t1)."""
    return {
        "tasks": [
            {"id": "t1", "domain": "backend", "prompt": "Task 1", "deps": ["t2"]},
            {"id": "t2", "domain": "testing", "prompt": "Task 2", "deps": ["t1"]},
        ]
    }


async def _mock_stream_valid(*args, **kwargs):
    """Async generator that yields a valid plan JSON."""
    plan_json = json.dumps(_make_valid_plan_dict())
    yield Message(role="assistant", content=plan_json)


async def _mock_stream_invalid_json(*args, **kwargs):
    """Async generator that yields invalid JSON."""
    yield Message(role="assistant", content="this is not valid json")


async def _mock_stream_cycle(*args, **kwargs):
    """Async generator that yields a plan with a cycle."""
    plan_json = json.dumps(_make_plan_with_cycle())
    yield Message(role="assistant", content=plan_json)


async def _mock_stream_invalid_schema(*args, **kwargs):
    """Async generator that yields valid JSON with schema violations."""
    yield Message(
        role="assistant",
        content=json.dumps({
            "tasks": [
                {
                    "id": "t1",
                    "domain": "backend",
                    "prompt": "Write a simple API endpoint",
                    # Missing required `deps`
                }
            ]
        }),
    )


async def _mock_stream_with_markdown(*args, **kwargs):
    """Async generator that yields JSON wrapped in markdown fences."""
    plan_json = json.dumps(_make_valid_plan_dict())
    yield Message(role="assistant", content=f"```json\n{plan_json}\n```")


async def _mock_stream_with_text_chunks(*args, **kwargs):
    """Async generator that yields only str chunks (some providers stream this way)."""
    plan_json = json.dumps(_make_valid_plan_dict())
    # Provider that only yields text chunks, no final Message
    yield plan_json


async def _mock_stream_mixed_chunks_then_message(*args, **kwargs):
    """Async generator that yields str deltas then a complete final Message (canonical)."""
    plan_json = json.dumps(_make_valid_plan_dict())
    # Simulate partial str deltas (simulate streaming)
    half = len(plan_json) // 2
    yield plan_json[:half]   # str delta #1 — partial, not valid JSON alone
    yield plan_json[half:]   # str delta #2 — rest of the content
    # Final Message is the complete assembled response — should replace deltas
    yield Message(role="assistant", content=plan_json)


class MockProvider:
    """Mock provider for testing."""

    def __init__(self, stream_generator=None, models=None):
        self._stream_generator = stream_generator or _mock_stream_valid
        self._models = models or ["gpt-4o"]
        self.stream_calls = []

    @property
    def id(self):
        return "mock"

    @property
    def name(self):
        return "Mock Provider"

    def list_models(self):
        return self._models

    def auth_required(self):
        return False

    def is_authenticated(self):
        return True

    def login(self):
        pass

    async def stream(self, messages, model, tools=None, extra=None):
        """Capture call args and delegate to generator."""
        self.stream_calls.append({
            "messages": messages,
            "model": model,
            "tools": tools,
            "extra": extra,
        })
        async for msg in self._stream_generator(messages, model, tools, extra):
            yield msg


def test_valid_dag():
    """Mock provider stream returns valid JSON → returns {'dag': {...}}."""
    mock_provider = MockProvider(stream_generator=_mock_stream_valid)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            result = planner_node(state)

    assert "dag" in result
    assert "tasks" in result["dag"]
    assert len(result["dag"]["tasks"]) == 1
    assert result["dag"]["tasks"][0]["id"] == "t1"


def test_schema_rejection():
    """Mock returns invalid JSON → ValueError raised after 3 retries."""
    mock_provider = MockProvider(stream_generator=_mock_stream_invalid_json)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            with pytest.raises(ValueError, match="Planner failed"):
                planner_node(state)

    # Should have called stream 3 times (max_retries)
    assert len(mock_provider.stream_calls) == 3


def test_cycle_rejection():
    """Mock returns valid JSON with cycle → ValueError from validate_dag."""
    mock_provider = MockProvider(stream_generator=_mock_stream_cycle)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            with pytest.raises(ValueError, match="cycle"):
                planner_node(state)


def test_schema_validation_rejection():
    """Valid JSON with wrong schema should be rejected after 3 retries."""
    mock_provider = MockProvider(stream_generator=_mock_stream_invalid_schema)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            with pytest.raises(ValueError, match="Planner failed"):
                planner_node(state)

    assert len(mock_provider.stream_calls) == 3


def test_config_model_resolution():
    """resolve_model returns custom model → planner passes it to provider.stream."""
    custom_model = "custom-model-123"
    mock_provider = MockProvider(stream_generator=_mock_stream_valid)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, custom_model)):
        state: AgentState = {
            "task": "Create a simple API",
            "dag": {},
            "completed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 10,
            "workdir": "/tmp",
            "auto": False,
        }

        planner_node(state)

    # Verify the model was passed correctly
    assert len(mock_provider.stream_calls) >= 1
    assert mock_provider.stream_calls[0]["model"] == custom_model


def test_config_provider_resolution():
    """resolve_model returns specific provider/model → planner uses them."""
    mock_provider = MockProvider(stream_generator=_mock_stream_valid)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-5")):
        state: AgentState = {
            "task": "Create a simple API",
            "dag": {},
            "completed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 10,
            "workdir": "/tmp",
            "auto": False,
        }

        planner_node(state)

    # Verify the provider was used
    assert len(mock_provider.stream_calls) >= 1


def test_default_provider_first_model_used_when_config_absent():
    """When planner model is unset, resolve_model picks the default model."""
    mock_provider = MockProvider(stream_generator=_mock_stream_valid, models=["planner-default", "backup-model"])

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "planner-default")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            planner_node(state)

    assert mock_provider.stream_calls[0]["model"] == "planner-default"


def test_retry_success():
    """First 2 calls return invalid JSON, 3rd returns valid → success."""
    call_count = 0

    async def _mock_stream_with_retries(messages, model, tools=None, extra=None):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            yield Message(role="assistant", content="invalid json")
        else:
            yield Message(role="assistant", content=json.dumps(_make_valid_plan_dict()))

    mock_provider = MockProvider(stream_generator=_mock_stream_with_retries)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            result = planner_node(state)

    assert "dag" in result
    assert call_count == 3


def test_markdown_fences_stripped():
    """JSON wrapped in markdown fences should be properly parsed."""
    mock_provider = MockProvider(stream_generator=_mock_stream_with_markdown)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            result = planner_node(state)

    assert "dag" in result
    assert "tasks" in result["dag"]


def test_stream_with_text_chunks():
    """Provider yielding str chunks before Message should be handled (CR-01 fix)."""
    mock_provider = MockProvider(stream_generator=_mock_stream_with_text_chunks)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            result = planner_node(state)

    assert "dag" in result
    assert "tasks" in result["dag"]
    assert len(result["dag"]["tasks"]) == 1
    assert result["dag"]["tasks"][0]["id"] == "t1"


def test_planner_exports_prompt():
    """PLANNER_SYSTEM_PROMPT should be exported and contain key sections."""
    assert "task decomposition" in PLANNER_SYSTEM_PROMPT.lower()
    assert "{schema}" in PLANNER_SYSTEM_PROMPT  # Schema placeholder
    assert "backend" in PLANNER_SYSTEM_PROMPT  # Domain list
    assert "testing" in PLANNER_SYSTEM_PROMPT
    assert "docs" in PLANNER_SYSTEM_PROMPT
    assert "devops" in PLANNER_SYSTEM_PROMPT
    assert "security" in PLANNER_SYSTEM_PROMPT
    assert "data" in PLANNER_SYSTEM_PROMPT
    assert "general" in PLANNER_SYSTEM_PROMPT


def test_provider_receives_schema_enforced_system_prompt_and_user_task():
    """Planner should send schema-rich system prompt and original task to provider."""
    mock_provider = MockProvider(stream_generator=_mock_stream_valid)
    task = "Build a REST API with tests and docs"

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": task,
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            planner_node(state)

    messages = mock_provider.stream_calls[0]["messages"]
    assert messages[0].role == "system"
    assert '"title": "AgentPlan"' in messages[0].content
    assert "MUST" in messages[0].content
    assert messages[1].role == "user"
    assert task in messages[1].content


def test_config_fallback_to_default_provider():
    """resolve_model returns fallback provider → planner uses it."""
    mock_default = MockProvider(stream_generator=_mock_stream_valid)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_default, "gpt-4")):
        state: AgentState = {
            "task": "Create a simple API",
            "dag": {},
            "completed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 10,
            "workdir": "/tmp",
            "auto": False,
        }

        result = planner_node(state)

    assert "dag" in result
    # Should use the resolved provider
    assert len(mock_default.stream_calls) >= 1


def test_stream_mixed_chunks_then_message_uses_message_as_canonical():
    """When stream yields str deltas followed by final Message, Message.content wins."""
    mock_provider = MockProvider(stream_generator=_mock_stream_mixed_chunks_then_message)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            result = planner_node(state)

    # The final Message.content is the canonical response and must be used
    assert "dag" in result
    assert "tasks" in result["dag"]
    assert len(result["dag"]["tasks"]) == 1
    assert result["dag"]["tasks"][0]["id"] == "t1"


def test_non_parse_errors_propagate_without_retry():
    """Auth/network/runtime errors must NOT trigger retry — propagate immediately."""
    call_count = 0

    async def _mock_stream_raises_runtime(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Connection refused")
        yield  # make it a generator

    mock_provider = MockProvider(stream_generator=_mock_stream_raises_runtime)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        if True:  # scope preserved
            state: AgentState = {
                "task": "Create a simple API",
                "dag": {},
                "completed": [],
                "outputs": {},
                "errors": [],
                "depth": 0,
                "max_depth": 10,
                "workdir": "/tmp",
                "auto": False,
            }

            with pytest.raises(RuntimeError, match="Connection refused"):
                planner_node(state)

    # Should NOT retry on RuntimeError — called exactly once
    assert call_count == 1


def test_reasoning_block_stripped_by_planner_node():
    """planner_node must strip a leading <reasoning>...</reasoning> block before parsing."""
    plan_json = json.dumps(_make_valid_plan_dict())

    async def _mock_stream_with_reasoning(*args, **kwargs):
        """Provider that prefixes the JSON with a <reasoning> block."""
        yield Message(
            role="assistant",
            content=f"<reasoning>4 tasks, all independent</reasoning>\n{plan_json}",
        )

    mock_provider = MockProvider(stream_generator=_mock_stream_with_reasoning)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        state: AgentState = {
            "task": "Build a REST API",
            "dag": {},
            "completed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 10,
            "workdir": "/tmp",
            "auto": False,
        }
        result = planner_node(state)

    assert "dag" in result
    assert "tasks" in result["dag"]


def test_reasoning_block_not_stripped_when_embedded_in_json():
    """planner_node must NOT strip <reasoning> tags that appear inside JSON string values."""
    # JSON where a task prompt legitimately mentions the <reasoning> tag
    plan_with_tag_in_content = {
        "tasks": [
            {
                "id": "t1",
                "domain": "docs",
                "prompt": "Document the <reasoning>...</reasoning> XML format used by the planner",
                "deps": [],
            }
        ]
    }
    json_with_embedded_tag = json.dumps(plan_with_tag_in_content)

    async def _mock_stream_json_with_tag(*args, **kwargs):
        """Provider that returns JSON whose content includes <reasoning> tags."""
        yield Message(role="assistant", content=json_with_embedded_tag)

    mock_provider = MockProvider(stream_generator=_mock_stream_json_with_tag)

    with patch("maestro.planner.node.resolve_model", return_value=(mock_provider, "gpt-4o")):
        state: AgentState = {
            "task": "Document the planner format",
            "dag": {},
            "completed": [],
            "outputs": {},
            "errors": [],
            "depth": 0,
            "max_depth": 10,
            "workdir": "/tmp",
            "auto": False,
        }
        result = planner_node(state)

    # JSON must not be corrupted — the task with the embedded tag must survive
    assert "dag" in result
    tasks = result["dag"]["tasks"]
    assert len(tasks) == 1
    assert "<reasoning>" in tasks[0]["prompt"]
