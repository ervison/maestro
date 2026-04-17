# Agentic File Tools — Design Spec

**Date:** 2026-04-17  
**Status:** Approved

## Overview

Transform the maestro agent from a single-shot LLM call into a full agentic loop capable of creating, reading, editing, and deleting files, running shell commands, and searching in files — operating on the current working directory, with confirmation prompts before destructive actions.

## Architecture

```
run(prompt, model, system, workdir, auto)
  └─ _run_agentic_loop(messages, tools, tokens, workdir, auto)
       ├─ call API (streaming SSE) with tools JSON schemas
       ├─ collect SSE events:
       │    ├─ response.output_item.done {type: function_call} → execute tool
       │    └─ response.output_text.delta → accumulate final text
       ├─ if tool calls found:
       │    ├─ for each: confirm if destructive (unless --auto)
       │    ├─ execute → append function_call_output to messages
       │    └─ loop back to API call
       └─ if message (no tool calls): return final text
```

The LangGraph `@entrypoint` / `@task` wrapper is retained for observability and retry. The tool execution loop lives inside `_run_agentic_loop()`, called from within the `@task`.

## New Files

### `maestro/tools.py`

Defines:

- Python functions implementing each tool
- `TOOL_SCHEMAS` — list of OpenAI-format JSON Schema dicts (for the API payload)
- `execute_tool(name, args, workdir, auto) -> dict` — dispatcher
- `DESTRUCTIVE_TOOLS` — set of tool names requiring confirmation

### Updated `maestro/agent.py`

- `_run_agentic_loop()` replaces `_call_responses_api()` for the agentic path
- SSE parsing extended to collect `function_call` output items
- Loop continues until the model emits a final message with no tool calls
- Max iterations guard (default: 20) to prevent infinite loops

### Updated `maestro/cli.py`

- `run` command gains `--auto` flag (skip confirmations)
- `run` command gains `--workdir` flag (default: `os.getcwd()`)

## Tools

| Name              | Description                                   | Destructive |
| ----------------- | --------------------------------------------- | ----------- |
| `read_file`       | Read file contents (with optional line range) | No          |
| `write_file`      | Create or overwrite a file                    | Yes         |
| `create_file`     | Create file — fails if it already exists      | Yes         |
| `list_directory`  | List files/dirs in a path                     | No          |
| `delete_file`     | Delete a file                                 | Yes         |
| `move_file`       | Move or rename a file                         | Yes         |
| `search_in_files` | Grep-like text search across files            | No          |
| `execute_shell`   | Run a shell command                           | Yes         |

### Tool contracts

All path arguments are resolved relative to `workdir`. Any path that resolves outside `workdir` (via `..` traversal) is rejected with `{"error": "path outside workdir"}`.

`execute_shell` captures stdout+stderr, returns `{"stdout": ..., "stderr": ..., "returncode": ...}`. Timeout: 30s.

`read_file` returns `{"content": ..., "lines": N}`. Optionally accepts `start_line` / `end_line`.

`search_in_files` accepts `pattern` (regex), optional `path` (subdir), `include` (glob). Returns list of `{file, line, text}` matches (max 100).

### Confirmation flow

Before executing any destructive tool:

```
  [maestro] write_file → src/main.py (42 lines)
  Execute? [y/N]:
```

If user inputs anything other than `y` / `yes`, the tool returns `{"error": "user denied"}` and execution continues — the model receives the denial as feedback.

`--auto` flag skips all prompts (auto-confirms).

## SSE Event Parsing

New events to handle beyond existing `response.output_text.delta`:

- `response.output_item.done` with `item.type == "function_call"` → collect `{id, name, arguments}`
- After all function calls collected: execute each, build `function_call_output` input items
- Append to `input` list and re-call API with `previous_response_id` (if available) or full conversation

## Conversation State

The Responses API is stateless (`store: false`). Each loop iteration sends the full accumulated `input` list:

- Initial user message
- Model's `function_call` output items (from previous turns)
- Tool results as `function_call_output` items
- Continues until model emits a `message` with no tool calls

## Error Handling

- Tool execution errors are returned as `{"error": "..."}` — the model sees them and can retry or report
- API errors during the loop surface as `RuntimeError` with the full context (turn N of M)
- Max iterations exceeded raises `RuntimeError("Agent loop exceeded max_iterations=20")`

## CLI Changes

```
maestro run "prompt" [-m model] [-s system] [--auto] [--workdir PATH]
```

- `--auto`: skip all confirmation prompts
- `--workdir PATH`: set working directory (default: current directory)

## Security

- All file paths validated to stay within `workdir` (no `..` escapes)
- `execute_shell` always requires confirmation unless `--auto`
- `execute_shell` runs with the user's own permissions (no sandboxing beyond confirmation)
