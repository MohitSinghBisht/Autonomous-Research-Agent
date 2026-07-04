from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict
import operator

from pydantic import BaseModel, Field


class UserQueryState(TypedDict):
    mssg: str
    relevancy: bool | None
    completeness: bool | None


class ProceededCall(BaseModel):
    tool_call_name: str
    reasoning: str
    result_summary: str | None = None


class RawResult(BaseModel):
    source_tool: str
    title: str
    url: str | None = None
    content: str


class Finding(BaseModel):
    claim: str
    source_id: str


class Reference(BaseModel):
    id: str
    title: str
    url: str | None = None
    source_tool: str


class Summary(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    actionable_insights: list[str] | None = None


class QueryReviewOutput(BaseModel):
    completeness: bool
    relevant: bool
    user_mssg: str
    reasoning: str


class ImproveQueryOutput(BaseModel):
    improved_mssg: str
    reasoning: str


class ToolSelectionOutput(BaseModel):
    tool_selected: list[str] = Field(min_length=1)
    reasoning: str


class RejectionReason(BaseModel):
    tool_call_name: str
    reasoning: str


class SubAgentSpec(BaseModel):
    agent_name: str
    tool_call: str
    reasoning: str


class SpawnAgentMetadata(BaseModel):
    trigger: bool
    sub_agent_data: list[SubAgentSpec] = Field(default_factory=list)


class ValidatorOutput(BaseModel):
    re_iterate: bool = Field(alias="re-iterate")
    available_tool_list: list[str] = Field(default_factory=list)
    rejection_reasoning: list[RejectionReason] = Field(default_factory=list)
    spawn_agent_metadata: SpawnAgentMetadata

    model_config = {"populate_by_name": True}


class MasteryOutput(BaseModel):
    status: Literal["accepted", "rejected"]
    tool_calls_involved: list[str] = Field(default_factory=list)
    reasoning: str
    response: str
    summary: Summary | None = None


class ResearchToolOutput(BaseModel):
    result_summary: str
    results: list[RawResult] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    user_query: UserQueryState
    available_tool_calls: list[str]
    tried_combinations: list[list[str]]
    proceeded_tool_calls_with_reasoning: Annotated[list[ProceededCall], operator.add]
    mastery_feedback: str | None
    attempt_count: int
    MAX_ATTEMPTS: int
    low_confidence: bool
    raw_results: Annotated[list[RawResult], operator.add]
    filtered_results: list[RawResult]
    summary: Summary | None
    reasoning_log: Annotated[list[str], operator.add]
    selected_tool_calls: list[str]
    validator_output: ValidatorOutput | None
    pending_tool_jobs: list[SubAgentSpec]
    clarification_question: str | None
    final_response: str | None
    active_tool_call: str | None
    active_tool_reasoning: str | None
    run_log_path: str | None
    logger: Any
