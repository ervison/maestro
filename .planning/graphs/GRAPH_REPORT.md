# Graph Report - maestro  (2026-04-22)

## Corpus Check
- 41 files · ~143,901 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1129 nodes · 2893 edges · 16 communities detected
- Extraction: 42% EXTRACTED · 58% INFERRED · 0% AMBIGUOUS · INFERRED: 1678 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]

## God Nodes (most connected - your core abstractions)
1. `Message` - 343 edges
2. `ProviderPlugin` - 178 edges
3. `Tool` - 170 edges
4. `ToolCall` - 158 edges
5. `AgentPlan` - 89 edges
6. `CopilotProvider` - 83 edges
7. `PlanTask` - 75 edges
8. `ChatGPTProvider` - 70 edges
9. `TokenSet` - 67 edges
10. `main()` - 64 edges

## Surprising Connections (you probably didn't know these)
- `TokenSet` --uses--> `Build fake SSE line iterator from list of event dicts.`  [INFERRED]
  maestro/auth.py → tests/test_agent_loop.py
- `TokenSet` --uses--> `Model answers directly without any tool calls.`  [INFERRED]
  maestro/auth.py → tests/test_agent_loop.py
- `TokenSet` --uses--> `Model calls write_file once then answers.`  [INFERRED]
  maestro/auth.py → tests/test_agent_loop.py
- `TokenSet` --uses--> `Old logout command shows deprecation warning and calls auth.remove.`  [INFERRED]
  maestro/auth.py → tests/test_auth_store.py
- `TokenSet` --uses--> `Non-chatgpt providers are now allowed to run (guard relaxed in Phase 7).`  [INFERRED]
  maestro/auth.py → tests/test_auth_store.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.03
Nodes (150): LangGraph agent that uses LLM providers via the provider plugin system., Convert raw tool schema dicts to neutral Tool types., Convert LangChain messages to neutral Message types., Synchronous wrapper for async provider.stream().      Since _run_agentic_loop is, Run the agentic loop using provider.stream() for HTTP delegation.      Args:, Synchronous wrapper for legacy httpx.stream() SSE loop.      Backward-compatibil, Single-shot call to the Responses API (no tool loop). Used by models --check., Run the agentic loop with the given model and prompt.      Uses the given provid (+142 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (126): _call_responses_api(), all_providers(), _build_authorize_url(), _generate_pkce(), _generate_state(), login_browser(), List all provider IDs with stored credentials., _available_cache_path() (+118 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (151): BaseModel, aggregator_node(), dispatch_node(), dispatch_route(), _materialize_plan(), _print_lifecycle(), Multi-agent scheduler and worker execution module.  Provides LangGraph StateGrap, Route from scheduler to dispatch or aggregator.      Returns string destinations (+143 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (84): _decode_jwt(), ensure_valid(), _exchange_code(), _extract_account_id(), _extract_email(), get(), __getattr__(), load() (+76 more)

### Community 4 - "Community 4"
Cohesion: 0.03
Nodes (57): resolve_model(), Config, load(), Configuration management for maestro.  This module handles loading, saving, and, Save configuration to disk with secure permissions.      Writes config to ~/.mae, Maestro configuration with provider and agent settings.      Attributes:, Load configuration from disk.      Returns:         Config instance with values, save() (+49 more)

### Community 5 - "Community 5"
Cohesion: 0.04
Nodes (46): discover_providers(), DuplicateProviderError, get_default_provider(), _is_valid_provider(), list_providers(), Provider registry for runtime discovery and access to LLM providers.  This modul, Discover all providers registered via entry points.      Uses importlib.metadata, List all discovered provider IDs.      Returns:         Sorted list of provider (+38 more)

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (58): _build_system_prompt(), _call_provider_with_schema(), planner_node(), _make_plan_with_cycle(), _make_valid_plan_dict(), _mock_stream_cycle(), _mock_stream_invalid_json(), _mock_stream_invalid_schema() (+50 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (31): format_model_list(), get_available_models(), _is_usable(), Model resolution and management for maestro.  This module handles: - Model strin, Check if a provider is usable (doesn't require auth or is authenticated)., Get all available models from usable providers.      Returns:         Dictionary, Format model list for display.      Args:         models_by_provider: Dictionary, _is_usable() (+23 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (43): test_create_file_exists_fails(), test_create_file_new(), test_delete_file(), test_execute_shell_failure(), test_execute_shell_success(), test_execute_shell_timeout(), test_execute_tool_always_escalates(), test_execute_tool_always_short_form() (+35 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (30): get_domain_prompt(), list_domains(), Domain system for multi-agent worker specialization.  Each domain has a system p, Get the system prompt for a domain, falling back to 'general' if unknown.      A, Return list of available domain names., Tests for domain system., All 7 required domains are defined., DEFAULT_DOMAIN constant is 'general'. (+22 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (20): parse_model_string(), Parse a model string into provider_id and model_id.      Validates the "provider, Resolve model following the priority chain.      Resolution priority (highest to, resolve_model(), get_provider(), Get a provider instance by ID.      Args:         provider_id: Unique provider i, Tests for parse_model_string() function., Parses valid provider/model format. (+12 more)

### Community 11 - "Community 11"
Cohesion: 0.12
Nodes (23): _convert_messages_to_neutral(), _convert_tool_schemas(), run(), _run_agentic_loop(), _run_httpx_stream_sync(), _run_provider_stream_sync(), make_mock_provider(), Provider-based agent loop regression tests.  These tests verify the provider-bas (+15 more)

### Community 12 - "Community 12"
Cohesion: 0.1
Nodes (5): Unit tests for the hardened PLANNER_SYSTEM_PROMPT in maestro/planner/node.py.  T, The prompt must explicitly define the independence criterion and forbid treating, The prompt must instruct the model to output a <reasoning> block followed by JSO, test_prompt_requires_dependencies_for_non_independent_tasks(), test_prompt_requires_reasoning_block_before_json_output()

### Community 13 - "Community 13"
Cohesion: 0.83
Nodes (3): soma(), subtracao(), teste_operacoes()

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Unique provider identifier (e.g., 'chatgpt', 'github-copilot').

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Human-readable provider name (e.g., 'ChatGPT', 'GitHub Copilot').

## Knowledge Gaps
- **158 isolated node(s):** `OAuth2 authentication for ChatGPT Plus/Pro subscriptions. Implements PKCE Author`, `Read the full auth store from disk. Auto-migrate old flat format.`, `Write the full auth store to disk with secure permissions.`, `Get credentials for a specific provider.`, `Store credentials for a specific provider.` (+153 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 15`** (1 nodes): `Unique provider identifier (e.g., 'chatgpt', 'github-copilot').`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `Human-readable provider name (e.g., 'ChatGPT', 'GitHub Copilot').`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Message` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 5`, `Community 6`, `Community 7`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.322) - this node is a cross-community bridge._
- **Why does `ProviderPlugin` connect `Community 0` to `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 7`, `Community 10`?**
  _High betweenness centrality (0.186) - this node is a cross-community bridge._
- **Why does `main()` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 7`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.167) - this node is a cross-community bridge._
- **Are the 341 inferred relationships involving `Message` (e.g. with `LangGraph agent that uses LLM providers via the provider plugin system.` and `Synchronous wrapper for legacy httpx.stream() SSE loop.      Backward-compatibil`) actually correct?**
  _`Message` has 341 INFERRED edges - model-reasoned connections that need verification._
- **Are the 170 inferred relationships involving `ProviderPlugin` (e.g. with `Model resolution and management for maestro.  This module handles: - Model strin` and `Parse a model string into provider_id and model_id.      Validates the "provider`) actually correct?**
  _`ProviderPlugin` has 170 INFERRED edges - model-reasoned connections that need verification._
- **Are the 168 inferred relationships involving `Tool` (e.g. with `LangGraph agent that uses LLM providers via the provider plugin system.` and `Synchronous wrapper for legacy httpx.stream() SSE loop.      Backward-compatibil`) actually correct?**
  _`Tool` has 168 INFERRED edges - model-reasoned connections that need verification._
- **Are the 156 inferred relationships involving `ToolCall` (e.g. with `LangGraph agent that uses LLM providers via the provider plugin system.` and `Synchronous wrapper for legacy httpx.stream() SSE loop.      Backward-compatibil`) actually correct?**
  _`ToolCall` has 156 INFERRED edges - model-reasoned connections that need verification._