"""Multi-agent state types and Pydantic schemas.

Defines the type foundation for the multi-agent DAG engine:
- AgentState: LangGraph TypedDict with safe reducers for parallel writes
- PlanTask/AgentPlan: Pydantic models for planner output validation
"""

from typing import TypedDict, Annotated, Literal
import operator

from pydantic import BaseModel, Field, ConfigDict


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge two dicts, used as reducer for AgentState.outputs.

    This reducer allows parallel workers to safely write to outputs
    without overwriting each other's data.
    """
    return {**a, **b}


class AgentState(TypedDict):
    """LangGraph state for multi-agent execution.

    Uses Annotated reducers to enable safe parallel writes:
    - completed/errors: list append via operator.add
    - outputs: dict merge via _merge_dicts
    """

    task: str  # Original user task
    dag: dict  # Serialized AgentPlan (for scheduler reconstruction)
    completed: Annotated[list[str], operator.add]  # Task IDs that finished
    outputs: Annotated[dict[str, str], _merge_dicts]  # task_id -> output mapping
    errors: Annotated[list[str], operator.add]  # Error messages from workers
    depth: int  # Current recursion depth
    max_depth: int  # Recursion limit
    workdir: str  # Shared working directory
    auto: bool  # Auto-approve flag


DomainName = Literal[
    "backend", "testing", "docs", "devops", "general", "security", "data"
]


class PlanTask(BaseModel):
    """Single task in a multi-agent plan.

    Validated via Pydantic with strict mode (extra="forbid") to reject
    unexpected fields from LLM output.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique task identifier, e.g. t1")
    domain: DomainName = Field(
        description="One of: backend, testing, docs, devops, general, security"
    )
    prompt: str = Field(description="Specific instruction for this worker")
    deps: list[str] = Field(..., description="IDs of tasks that must complete first")


class AgentPlan(BaseModel):
    """Complete multi-agent plan with task list.

    Validated via Pydantic with strict mode (extra="forbid") to reject
    unexpected fields from LLM output.
    """

    model_config = ConfigDict(extra="forbid")

    tasks: list[PlanTask] = Field(
        description="List of tasks in execution order (dependencies considered)"
    )
