import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from langchain_core.messages import HumanMessage
from maestro.auth import TokenSet
from maestro.agent import _run_agentic_loop

FAKE_TOKENS = TokenSet(
    access="tok", refresh="ref", expires=9999999999.0, account_id="acc"
)


def _sse_lines(*events):
    """Build fake SSE line iterator from list of event dicts."""
    lines = []
    for e in events:
        lines.append(f"data: {json.dumps(e)}")
    lines.append("data: [DONE]")
    return iter(lines)


def test_agentic_loop_direct_answer(tmp_path):
    """Model answers directly without any tool calls."""
    events = [
        {"type": "response.output_text.delta", "delta": "Hello"},
        {"type": "response.output_text.delta", "delta": " world"},
    ]

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.iter_lines.return_value = _sse_lines(*events)
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_response)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("maestro.agent.httpx.stream", return_value=mock_cm):
        result = _run_agentic_loop(
            messages=[HumanMessage(content="say hi")],
            model="gpt-5.4-mini",
            instructions="You are helpful.",
            tokens=FAKE_TOKENS,
            workdir=tmp_path,
            auto=True,
        )
    assert result == "Hello world"


def test_agentic_loop_one_tool_call(tmp_path):
    """Model calls write_file once then answers."""
    (tmp_path / "dummy").mkdir(exist_ok=True)

    tool_call_event = {
        "type": "response.output_item.done",
        "item": {
            "type": "function_call",
            "id": "call_1",
            "name": "write_file",
            "arguments": json.dumps({"path": "out.txt", "content": "done"}),
        },
    }
    final_events = [
        {"type": "response.output_text.delta", "delta": "File written."},
    ]

    call_count = 0

    def fake_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_response = MagicMock()
        mock_response.is_success = True
        if call_count == 1:
            mock_response.iter_lines.return_value = _sse_lines(tool_call_event)
        else:
            mock_response.iter_lines.return_value = _sse_lines(*final_events)
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_response)
        mock_cm.__exit__ = MagicMock(return_value=False)
        return mock_cm

    with patch("maestro.agent.httpx.stream", side_effect=fake_stream):
        result = _run_agentic_loop(
            messages=[HumanMessage(content="write a file")],
            model="gpt-5.4-mini",
            instructions="You are helpful.",
            tokens=FAKE_TOKENS,
            workdir=tmp_path,
            auto=True,
        )
    assert result == "File written."
    assert (tmp_path / "out.txt").read_text() == "done"
    assert call_count == 2
