Phase: 8
Branch: gsd/phase-8-dag-state-types-domains
EXECUTION_ROOT: /home/ervison/Documents/PROJETOS/labs/timeIA/maestro/.workspace/fase8

Decisions:
- AgentState reducers: use Annotated[list, operator.add] for 'completed' and 'errors' (list append, allow duplicates)
- Deduplication strategy: downstream consumers may dedupe by task id for idempotence if needed
- PlanTask/AgentPlan schemas: strict Pydantic models. 'deps' is required and must be list[str]. Unknown fields are forbidden.
- Dep parsing: planner must emit list[str]; no coercion allowed.
- DAG validator: reject cycles using graphlib.TopologicalSorter.prepare() and raise CycleError for planner to fix.
- Domains to include: backend, testing, docs, devops, general, security, data
- Worker path guard: strict containment — workers must not write outside EXECUTION_ROOT; attempts are blocked and reported.

Artifacts to generate:
- 08-CONTEXT.md (this file)
- TODO: maestro/domains.py skeleton with listed domains
- TODO: pydantic models file (maestro/planner/schemas.py) with PlanTask and AgentPlan
- TODO: DAG validator using graphlib.TopologicalSorter
