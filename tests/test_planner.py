from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from maestro import domains
from maestro.providers.base import Message
from maestro.planner import node
from maestro.planner.schemas import AgentPlan, PlanTask
from maestro.planner.validator import validate_dag


def test_strip_reasoning_block_removes_leading_block() -> None:
    raw = "  <reasoning>step by step</reasoning>  {\"tasks\": []}  "

    assert node._strip_reasoning_block(raw) == '{"tasks": []}'


def test_strip_reasoning_block_leaves_text_without_closing_tag() -> None:
    raw = "<reasoning>missing close"

    assert node._strip_reasoning_block(raw) == raw


def test_strip_markdown_fences_removes_wrapping_fence() -> None:
    raw = "```json\n{\"tasks\": []}\n```"

    assert node._strip_markdown_fences(raw) == '{"tasks": []}'


def test_build_system_prompt_embeds_schema_and_domains() -> None:
    prompt = node._build_system_prompt()

    assert '"tasks"' in prompt
    assert "backend" in prompt
    assert "testing" in prompt
    assert "## Output Format" in prompt


@pytest.mark.asyncio
async def test_async_collect_stream_uses_response_format_and_final_message_content() -> None:
    observed: dict[str, object] = {}

    class FakeProvider:
        async def stream(self, messages, model, tools=None, **kwargs):
            observed["messages"] = messages
            observed["model"] = model
            observed["tools"] = tools
            observed["extra"] = kwargs.get("extra")
            yield "partial"
            yield Message(role="assistant", content='{"tasks": []}')

    result = await node._async_collect_stream(
        FakeProvider(),
        [Message(role="user", content="plan this")],
        "gpt-5.4-mini",
        True,
    )

    assert result == '{"tasks": []}'
    assert observed["model"] == "gpt-5.4-mini"
    assert observed["tools"] == []
    assert observed["extra"] == {
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "AgentPlan",
                "schema": node._AGENT_PLAN_SCHEMA,
                "strict": True,
            },
        }
    }


def test_call_provider_with_schema_falls_back_when_response_format_not_supported() -> None:
    calls: list[bool] = []

    def fake_run(coro):
        coro.close()
        use_response_format = len(calls) == 0
        calls.append(use_response_format)
        if use_response_format:
            raise TypeError("unsupported")
        return '{"tasks": []}'

    with patch("maestro.planner.node._run_async_sync", side_effect=fake_run):
        result = node._call_provider_with_schema(SimpleNamespace(), [], "gpt-5.4-mini")

    assert result == '{"tasks": []}'
    assert calls == [True, False]


def test_call_provider_with_schema_falls_back_on_response_format_runtime_error() -> None:
    calls: list[bool] = []

    def fake_run(coro):
        coro.close()
        use_response_format = len(calls) == 0
        calls.append(use_response_format)
        if use_response_format:
            raise RuntimeError("response_format rejected")
        return '{"tasks": []}'

    with patch("maestro.planner.node._run_async_sync", side_effect=fake_run):
        result = node._call_provider_with_schema(SimpleNamespace(), [], "gpt-5.4-mini")

    assert result == '{"tasks": []}'
    assert calls == [True, False]


def test_call_provider_with_schema_re_raises_other_runtime_errors() -> None:
    def fake_run(coro):
        coro.close()
        raise RuntimeError("network down")

    with patch("maestro.planner.node._run_async_sync", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="network down"):
            node._call_provider_with_schema(SimpleNamespace(), [], "gpt-5.4-mini")


def test_resolve_planner_provider_prefers_runtime_provider_when_ids_match() -> None:
    runtime_provider = SimpleNamespace(id="chatgpt")
    resolved_provider = SimpleNamespace(id="chatgpt")

    with patch("maestro.planner.node.resolve_model", return_value=(resolved_provider, "gpt-5.4-mini")):
        provider, model_id = node._resolve_planner_provider({"provider": runtime_provider})

    assert provider is runtime_provider
    assert model_id == "gpt-5.4-mini"


def test_resolve_planner_provider_uses_resolved_provider_when_runtime_differs() -> None:
    runtime_provider = SimpleNamespace(id="github-copilot")
    resolved_provider = SimpleNamespace(id="chatgpt")

    with patch("maestro.planner.node.resolve_model", return_value=(resolved_provider, "gpt-5.4-mini")):
        provider, model_id = node._resolve_planner_provider({"provider": runtime_provider})

    assert provider is resolved_provider
    assert model_id == "gpt-5.4-mini"


def test_planner_node_returns_valid_dag_after_stripping_reasoning_and_markdown() -> None:
    raw = '<reasoning>minimal split</reasoning>\n{"tasks": [{"id": "t1", "domain": "general", "prompt": "Do it", "deps": []}]}'
    provider = SimpleNamespace(id="chatgpt")

    with (
        patch("maestro.planner.node._resolve_planner_provider", return_value=(provider, "gpt-5.4-mini")),
        patch("maestro.planner.node._call_provider_with_schema", return_value=raw),
        patch("maestro.planner.node.validate_dag") as mock_validate,
    ):
        result = node.planner_node({"task": "Ship it", "provider": provider})

    assert result == {
        "dag": {
            "tasks": [{"id": "t1", "domain": "general", "prompt": "Do it", "deps": []}]
        }
    }
    mock_validate.assert_called_once()


def test_planner_node_retries_and_raises_after_validation_failures() -> None:
    provider = SimpleNamespace(id="chatgpt")
    state = {"task": "Ship it", "provider": provider}
    invalid_json = "not json"

    with (
        patch("maestro.planner.node._resolve_planner_provider", return_value=(provider, "gpt-5.4-mini")),
        patch("maestro.planner.node._call_provider_with_schema", return_value=invalid_json),
    ):
        with pytest.raises(ValueError, match="Planner failed to produce a valid AgentPlan after 3 attempts"):
            node.planner_node(state)


def test_planner_node_retries_with_feedback_messages_between_attempts() -> None:
    provider = SimpleNamespace(id="chatgpt")
    observed_messages: list[list[Message]] = []

    def fake_call(provider_arg, messages, model_id):
        del provider_arg, model_id
        observed_messages.append(list(messages))
        if len(observed_messages) == 1:
            return "not json"
        return '{"tasks": [{"id": "t1", "domain": "general", "prompt": "Do it", "deps": []}]}'

    with (
        patch("maestro.planner.node._resolve_planner_provider", return_value=(provider, "gpt-5.4-mini")),
        patch("maestro.planner.node._call_provider_with_schema", side_effect=fake_call),
        patch("maestro.planner.node.validate_dag"),
    ):
        result = node.planner_node({"task": "Ship it", "provider": provider})

    assert result["dag"]["tasks"][0]["id"] == "t1"
    assert len(observed_messages) == 2
    assert observed_messages[1][-2] == Message(role="assistant", content="not json")
    assert "Your previous response was invalid" in observed_messages[1][-1].content


def test_planner_node_rejects_overlong_task() -> None:
    with pytest.raises(ValueError, match="Task too long"):
        node.planner_node({"task": "x" * 8001})


def test_validate_dag_accepts_empty_and_acyclic_plans() -> None:
    validate_dag(AgentPlan(tasks=[]))
    validate_dag(
        AgentPlan(
            tasks=[
                PlanTask(id="t1", domain="general", prompt="one", deps=[]),
                PlanTask(id="t2", domain="general", prompt="two", deps=["t1"]),
            ]
        )
    )


def test_validate_dag_rejects_duplicate_task_ids() -> None:
    plan = AgentPlan(
        tasks=[
            PlanTask(id="dup", domain="general", prompt="one", deps=[]),
            PlanTask(id="dup", domain="general", prompt="two", deps=[]),
        ]
    )

    with pytest.raises(ValueError, match=r"Duplicate task IDs are not allowed: \['dup'\]"):
        validate_dag(plan)


def test_validate_dag_rejects_unknown_dependencies() -> None:
    plan = AgentPlan(
        tasks=[PlanTask(id="t1", domain="general", prompt="one", deps=["missing"])]
    )

    with pytest.raises(ValueError, match="depends on unknown task 'missing'"):
        validate_dag(plan)


def test_validate_dag_rejects_cycles() -> None:
    plan = AgentPlan(
        tasks=[
            PlanTask(id="t1", domain="general", prompt="one", deps=["t2"]),
            PlanTask(id="t2", domain="general", prompt="two", deps=["t1"]),
        ]
    )

    with pytest.raises(ValueError, match="DAG contains a cycle"):
        validate_dag(plan)


@pytest.mark.asyncio
async def test_async_collect_stream_includes_extra_with_response_format() -> None:
    provider = SimpleNamespace(id="chatgpt", stream=lambda messages, model, tools, extra: _yield_chunks())

    async def _yield_chunks():
        yield "hello"
        yield " world"

    result = await node._async_collect_stream(provider, [], "gpt", use_response_format=True)
    assert result == "hello world"


@pytest.mark.asyncio
async def test_async_collect_stream_without_response_format() -> None:
    provider = SimpleNamespace(id="chatgpt", stream=lambda messages, model, tools: _yield_chunks())

    async def _yield_chunks():
        yield "ok"

    result = await node._async_collect_stream(provider, [], "gpt", use_response_format=False)
    assert result == "ok"


@pytest.mark.asyncio
async def test_async_collect_stream_handles_message_chunks() -> None:
    provider = SimpleNamespace(id="chatgpt", stream=lambda messages, model, tools: _yield_chunks())

    async def _yield_chunks():
        yield Message(role="assistant", content="from message")

    result = await node._async_collect_stream(provider, [], "gpt", use_response_format=False)
    assert result == "from message"


async def _fake_coro() -> str:
    return "result"


def test_run_async_sync_when_loop_exists_but_not_running() -> None:
    mock_loop = SimpleNamespace(is_running=lambda: False, run_until_complete=lambda c: "result")

    with patch("asyncio.get_running_loop", return_value=mock_loop):
        result = node._run_async_sync(_fake_coro())
        assert result == "result"


def test_run_async_sync_when_loop_already_running() -> None:
    mock_loop = SimpleNamespace(is_running=lambda: True)

    with (
        patch("asyncio.get_running_loop", return_value=mock_loop),
        patch("concurrent.futures.ThreadPoolExecutor") as mock_pool_cls,
    ):
        mock_pool = mock_pool_cls.return_value.__enter__.return_value
        mock_future = mock_pool.submit.return_value
        mock_future.result.return_value = "result"

        result = node._run_async_sync(_fake_coro())
        assert result == "result"
        mock_pool.submit.assert_called_once()


def test_run_async_sync_when_no_running_loop() -> None:
    with patch("asyncio.get_running_loop", side_effect=RuntimeError):
        with patch("asyncio.run", return_value="result"):
            result = node._run_async_sync(_fake_coro())
            assert result == "result"


def test_list_domains_includes_known_domains() -> None:
    names = domains.list_domains()

    assert "general" in names
    assert "backend" in names
