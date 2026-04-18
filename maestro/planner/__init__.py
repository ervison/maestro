"""Multi-agent planner package with state types and DAG validation.

This package provides:
- AgentState: TypedDict with LangGraph-compatible reducers for parallel writes
- PlanTask/AgentPlan: Pydantic models for planner output validation
- validate_dag: DAG validator using graphlib.TopologicalSorter
"""

from .schemas import AgentState, PlanTask, AgentPlan, _merge_dicts
from .validator import validate_dag

__all__ = [
    "AgentState",
    "PlanTask", 
    "AgentPlan",
    "_merge_dicts",
    "validate_dag",
]
