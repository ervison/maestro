---
status: complete
phase: 10-scheduler-workers
source: [10-01-SUMMARY.md]
started: 2026-04-19T01:01:06Z
updated: 2026-04-19T01:04:30Z
---

## Current Test

[testing complete]

## Tests

### 1. Scheduler dispatches ready tasks in correct dependency order
expected: Given a DAG with tasks A → B → C (sequential), calling run_multi_agent() executes A first, then B after A completes, then C after B. The scheduler does NOT dispatch B until A appears in the completed list.
result: pass
verified_by: test_scheduler_returns_initial_ready_batch, test_scheduler_unblocks_next_batch_after_completion

### 2. Parallel tasks fan out simultaneously via Send API
expected: Given a DAG where tasks B and C both depend only on A (diamond shape), after A completes the scheduler dispatches B and C in the same batch. Both outputs are preserved in the final state — neither overwrites the other.
result: pass
verified_by: test_parallel_worker_writes_preserve_both_outputs, test_dispatch_route_returns_one_send_per_ready_task

### 3. Worker failure is non-fatal to independent branches
expected: If task B fails (exception or error), task C (which doesn't depend on B) still executes and completes successfully. The final state has B in `failed`, C in `completed`, and both B's error and C's output recorded.
result: pass
verified_by: test_independent_branch_continues_after_other_worker_failure, test_worker_records_error_and_failed_task_without_crashing_graph

### 4. Worker uses domain-specific system prompt
expected: When a task has domain="coding", the worker composes the system prompt as `get_domain_prompt("coding") + "\n\n## Your Task\n\n" + task_prompt`. The agentic loop receives this composed prompt, not a generic one.
result: pass
verified_by: test_worker_uses_domain_prompt_and_task_prompt

### 5. Path guard blocks writes outside workdir
expected: If a worker attempts to write a file outside its assigned workdir (e.g., `../escape.txt`), the tool call returns an error containing "escapes workdir" and the file is NOT created. The worker records a failure without crashing the graph.
result: pass
verified_by: test_worker_blocks_write_outside_workdir

### 6. Depth guard enforces recursion limit
expected: Calling `run_multi_agent(task, workdir=..., auto=True, depth=3, max_depth=2)` raises an error or records a failure immediately — no agentic loop is started. The `depth` parameter has no default value (calling without it raises TypeError).
result: pass
verified_by: test_worker_rejects_depth_above_max_depth, test_depth_argument_is_required_on_runner

### 7. run_multi_agent() calls planner then executes resulting DAG
expected: Calling `run_multi_agent("build a REST API with tests", workdir=..., auto=True, depth=0)` invokes the planner to generate a DAG from the task, then feeds that DAG into the scheduler/worker graph. The function returns a final state with `completed` tasks.
result: pass
verified_by: test_run_multi_agent_threads_provider_model_to_planner_and_workers, test_run_multi_agent_rejects_invalid_workdir, test_run_multi_agent_rejects_file_as_workdir

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
