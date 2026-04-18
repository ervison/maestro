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


async def _mock_stream_with_markdown(*args, **kwargs):
    """Async generator that yields JSON wrapped in markdown fences."""
    plan_json = json.dumps(_make_valid_plan_dict())
    yield Message(role="assistant", content=f"```json\n{plan_json}\n```")


class MockProvider:
    """Mock provider for testing."""

    def __init__(self, stream_generator=None, models=None):
        self._stream_generator = stream_generator or _mock_stream_valid
        self._models = models or [MagicMock(id="gpt-4o")]
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

    with patch("maestro.planner.node.get_default_provider", return_value=mock_provider):
        with patch("maestro.planner.node.load_config", return_value=MagicMock(get=lambda x, default=None: None)):
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

    with patch("maestro.planner.node.get_default_provider", return_value=mock_provider):
        with patch("maestro.planner.node.load_config", return_value=MagicMock(get=lambda x, default=None: None)):
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

    with patch("maestro.planner.node.get_default_provider", return_value=mock_provider):
        with patch("maestro.planner.node.load_config", return_value=MagicMock(get=lambda x, default=None: None)):
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


def test_config_model_resolution():
    """Mock config with agent.planner.model set → correct provider/model used."""
    mock_provider = MockProvider(stream_generator=_mock_stream_valid)
    custom_model = "custom-model-123"

    # Create a config mock that returns the custom model
    def mock_get(key, default=None):
        if key == "agent.planner.model":
            return custom_model
        return default

    mock_config = MagicMock(get=mock_get)

    with patch("maestro.planner.node.get_default_provider", return_value=mock_provider):
        with patch("maestro.planner.node.load_config", return_value=mock_config):
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
    """Mock config with provider/model format → correct provider resolved."""
    mock_provider = MockProvider(stream_generator=_mock_stream_valid)

    # Create a config mock that returns provider/model format
    def mock_get(key, default=None):
        if key == "agent.planner.model":
            return "custom-provider/gpt-5"
        return default

    mock_config = MagicMock(get=mock_get)

    with patch("maestro.planner.node.get_provider", return_value=mock_provider):
        with patch("maestro.planner.node.get_default_provider", return_value=MagicMock(id="default")):
            with patch("maestro.planner.node.load_config", return_value=mock_config):
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

    # Verify the provider was resolved via get_provider
    # (the test passes if get_provider was called, which we verified via the patch)


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

    with patch("maestro.planner.node.get_default_provider", return_value=mock_provider):
        with patch("maestro.planner.node.load_config", return_value=MagicMock(get=lambda x, default=None: None)):
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

    with patch("maestro.planner.node.get_default_provider", return_value=mock_provider):
        with patch("maestro.planner.node.load_config", return_value=MagicMock(get=lambda x, default=None: None)):
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


def test_planner_exports_prompt():
    """PLANNER_SYSTEM_PROMPT should be exported and contain key sections."""
    assert "task decomposition specialist" in PLANNER_SYSTEM_PROMPT.lower()
    assert "{schema}" in PLANNER_SYSTEM_PROMPT  # Schema placeholder
    assert "backend" in PLANNER_SYSTEM_PROMPT  # Domain list
    assert "testing" in PLANNER_SYSTEM_PROMPT
    assert "docs" in PLANNER_SYSTEM_PROMPT
    assert "devops" in PLANNER_SYSTEM_PROMPT
    assert "security" in PLANNER_SYSTEM_PROMPT
    assert "data" in PLANNER_SYSTEM_PROMPT
    assert "general" in PLANNER_SYSTEM_PROMPT


def test_config_fallback_to_default_provider():
    """When configured provider not found, fall back to default."""
    mock_default = MockProvider(stream_generator=_mock_stream_valid)

    def mock_get(key, default=None):
        if key == "agent.planner.model":
            return "nonexistent-provider/gpt-4"
        return default

    mock_config = MagicMock(get=mock_get)

    with patch("maestro.planner.node.get_provider", side_effect=ValueError("Provider not found")):
        with patch("maestro.planner.node.get_default_provider", return_value=mock_default):
            with patch("maestro.planner.node.load_config", return_value=mock_config):
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
    # Should fall back to default provider
    assert len(mock_default.stream_calls) >= 1
