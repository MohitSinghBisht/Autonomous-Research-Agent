from __future__ import annotations

from datetime import datetime
from itertools import combinations
from typing import Any

from langgraph.constants import END, START, Send
from langgraph.graph import StateGraph
from langsmith import traceable

from .config import Settings
from .dedup import deduplicate_results
from .fetchers import TavilyFetcher, fetch_with_tool
from .llm import OpenAIReasoner
from .models import (
    AgentState,
    ImproveQueryOutput,
    MasteryOutput,
    Finding,
    ProceededCall,
    QueryReviewOutput,
    RawResult,
    Reference,
    Summary,
    ToolSelectionOutput,
    ValidatorOutput,
)
from .observability import RunLogger
from .prompts import (
    IMPROVE_QUERY_SYSTEM_PROMPT,
    MASTERY_SYSTEM_PROMPT,
    QUERY_REVIEW_SYSTEM_PROMPT,
    TOOL_SELECTION_SYSTEM_PROMPT,
    VALIDATOR_SYSTEM_PROMPT,
)


DEFAULT_TOOLS = [
    "general_web_search",
    "official_docs_search",
    "expert_analysis_search",
]


def _append_reasoning(node_name: str, reasoning: str) -> list[str]:
    return [f"{node_name}: {reasoning.strip()}"]


def _inject_date(prompt: str) -> str:
    current_date = datetime.now().strftime("%Y-%m-%d")
    return f"{prompt}\n\n# System Information\nCurrent Date: {current_date}"


def _combo_key(tool_names: list[str]) -> list[str]:
    return sorted(tool_names)


def _remaining_combinations(state: AgentState) -> int:
    available_tools = state["available_tool_calls"]
    tried = {tuple(sorted(combo)) for combo in state["tried_combinations"]}
    total = 0
    for size in range(1, len(available_tools) + 1):
        for combo in combinations(available_tools, size):
            if tuple(sorted(combo)) not in tried:
                total += 1
    return total


def _references_from_results(results: list[RawResult]) -> list[Reference]:
    references: list[Reference] = []
    for index, result in enumerate(results, start=1):
        references.append(
            Reference(
                id=f"S{index}",
                title=result.title,
                url=result.url,
                source_tool=result.source_tool,
            )
        )
    return references


def _build_best_effort_summary(results: list[RawResult]) -> Summary:
    references = _references_from_results(results)
    key_points = [result.title for result in results[:3]]
    findings: list[Finding] = []
    for reference, result in zip(references, results, strict=False):
        findings.append(Finding(claim=result.content[:220].strip(), source_id=reference.id))
    return Summary(
        summary="A best-effort summary could not be fully synthesized due to retry exhaustion.",
        key_points=key_points,
        findings=findings,
        references=references,
        actionable_insights=["Review the cited sources directly before making a final decision."] if results else None,
    )


def _format_summary(summary: Summary, low_confidence: bool) -> str:
    lines: list[str] = []
    if low_confidence:
        lines.append("This summary is best-effort and may be incomplete because the agent exhausted its retry budget.")
        lines.append("")

    lines.append("## Summary")
    lines.append(summary.summary)
    lines.append("")

    lines.append("## Key Points")
    for point in summary.key_points:
        lines.append(f"- {point}")

    lines.append("")
    lines.append("## Important Findings")
    for finding in summary.findings:
        lines.append(f"- {finding.claim} ({finding.source_id})")

    lines.append("")
    lines.append("## References")
    for reference in summary.references:
        suffix = f" - {reference.url}" if reference.url else ""
        lines.append(f"- {reference.id}: {reference.title}{suffix}")

    if summary.actionable_insights:
        lines.append("")
        lines.append("## Actionable Insights")
        for insight in summary.actionable_insights:
            lines.append(f"- {insight}")

    return "\n".join(lines)


def build_research_graph(settings: Settings):
    reasoner = OpenAIReasoner(settings)
    tavily_fetcher = TavilyFetcher(settings)
    builder = StateGraph(AgentState)

    def run_node(node_name: str, state: AgentState, work):
        logger = state["logger"]
        logger.node_start(node_name, dict(state))
        result = work()
        logger.node_end(node_name, dict(state), result)
        return result

    def query_review_node(state: AgentState) -> dict[str, Any]:
        return run_node(
            "query_review",
            state,
            lambda: {
                "user_query": {
                    "mssg": (
                        result := reasoner.parse_structured(
                            model=settings.light_model,
                            system_prompt=_inject_date(QUERY_REVIEW_SYSTEM_PROMPT),
                            user_prompt=state["user_query"]["mssg"],
                            schema=QueryReviewOutput,
                            temperature=settings.temp_query_review,
                        )
                    ).user_mssg,
                    "relevancy": result.relevant,
                    "completeness": result.completeness,
                },
                "reasoning_log": _append_reasoning("query_review", result.reasoning),
            },
        )

    def route_after_query_review(state: AgentState) -> str:
        destination = "choose_tools"
        if not state["user_query"]["relevancy"]:
            destination = "clarification"
        elif not state["user_query"]["completeness"]:
            destination = "improve_query"
        state["logger"].route("route_after_query_review", destination, dict(state))
        return destination

    def clarification_node(state: AgentState) -> dict[str, Any]:
        return run_node(
            "clarification",
            state,
            lambda: {
                "clarification_question": (
                    question := (
                        "I need a clearer research request before I can continue. "
                        f"Please clarify the topic or objective for: {state['user_query']['mssg']}"
                    )
                ),
                "final_response": question,
            },
        )

    def improve_query_node(state: AgentState) -> dict[str, Any]:
        return run_node(
            "improve_query",
            state,
            lambda: {
                "user_query": {
                    "mssg": (
                        result := reasoner.parse_structured(
                            model=settings.light_model,
                            system_prompt=_inject_date(IMPROVE_QUERY_SYSTEM_PROMPT),
                            user_prompt=state["user_query"]["mssg"],
                            schema=ImproveQueryOutput,
                            temperature=settings.temp_improve_query,
                        )
                    ).improved_mssg,
                    "relevancy": True,
                    "completeness": True,
                },
                "reasoning_log": _append_reasoning("improve_query", result.reasoning),
            },
        )

    def choose_tools_node(state: AgentState) -> dict[str, Any]:
        return run_node(
            "choose_tools",
            state,
            lambda: {
                "selected_tool_calls": (
                    result := reasoner.parse_structured(
                        model=settings.mid_model,
                        system_prompt=_inject_date(TOOL_SELECTION_SYSTEM_PROMPT),
                        user_prompt=(
                            f"Query: {state['user_query']['mssg']}\n"
                            f"Available tools: {state['available_tool_calls']}\n"
                            f"Tried combinations: {state['tried_combinations']}\n"
                            f"Mastery feedback: {state.get('mastery_feedback') or 'None'}"
                        ),
                        schema=ToolSelectionOutput,
                        temperature=settings.temp_choose_tools,
                    )
                ).tool_selected,
                "reasoning_log": _append_reasoning("choose_tools", result.reasoning),
            },
        )

    def validator_node(state: AgentState) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            selected = _combo_key(state["selected_tool_calls"])
            result = reasoner.parse_structured(
                model=settings.mid_model,
                system_prompt=_inject_date(VALIDATOR_SYSTEM_PROMPT),
                user_prompt=(
                    f"Query: {state['user_query']['mssg']}\n"
                    f"Selected tools: {selected}\n"
                    f"Available tools: {state['available_tool_calls']}\n"
                    f"Tried combinations: {state['tried_combinations']}\n"
                    f"Attempt count: {state['attempt_count']} / {state['MAX_ATTEMPTS']}\n"
                    f"Mastery feedback: {state.get('mastery_feedback') or 'None'}"
                ),
                schema=ValidatorOutput,
                temperature=settings.temp_validator,
            )
            updates: dict[str, Any] = {
                "validator_output": result,
                "reasoning_log": _append_reasoning(
                    "validator",
                    "; ".join(reason.reasoning for reason in result.rejection_reasoning)
                    if result.re_iterate and result.rejection_reasoning
                    else (
                        "; ".join(spec.reasoning for spec in result.spawn_agent_metadata.sub_agent_data)
                        if result.spawn_agent_metadata.sub_agent_data
                        else "Validator approved the selected tools."
                    ),
                ),
            }

            if result.re_iterate:
                updates["tried_combinations"] = state["tried_combinations"] + [selected]
                updates["attempt_count"] = state["attempt_count"] + 1
                updates["proceeded_tool_calls_with_reasoning"] = [
                    ProceededCall(
                        tool_call_name=reason.tool_call_name,
                        reasoning=reason.reasoning,
                        result_summary=None,
                    )
                    for reason in result.rejection_reasoning
                ]
            else:
                updates["tried_combinations"] = state["tried_combinations"] + [selected]
                updates["pending_tool_jobs"] = result.spawn_agent_metadata.sub_agent_data

            return updates

        return run_node("validator", state, work)

    def route_after_validator(state: AgentState):
        if state["attempt_count"] >= state["MAX_ATTEMPTS"] or _remaining_combinations(state) == 0:
            destination = "exhaustion_fallback"
            state["logger"].route("route_after_validator", destination, dict(state))
            return destination

        validator_output = state["validator_output"]
        if validator_output and validator_output.re_iterate:
            destination = "choose_tools"
            state["logger"].route("route_after_validator", destination, dict(state))
            return destination

        pending = state.get("pending_tool_jobs", [])
        if not pending:
            destination = "exhaustion_fallback"
            state["logger"].route("route_after_validator", destination, dict(state))
            return destination

        sends = []
        for spec in pending:
            sends.append(
                Send(
                    "research_worker",
                    {
                        "user_query": state["user_query"],
                        "active_tool_call": spec.tool_call,
                        "active_tool_reasoning": spec.reasoning,
                        "logger": state["logger"],
                        "run_log_path": state.get("run_log_path"),
                    },
                )
            )
        state["logger"].route(
            "route_after_validator",
            [send.node for send in sends],
            dict(state),
        )
        return sends

    def research_worker_node(state: AgentState) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            tool_name = state["active_tool_call"]
            tool_reasoning = state["active_tool_reasoning"] or "No reasoning provided."

            try:
                tool_output = fetch_with_tool(
                    fetcher=tavily_fetcher,
                    query=state["user_query"]["mssg"],
                    tool_name=tool_name,
                    tool_reasoning=tool_reasoning,
                )
                proceeded = ProceededCall(
                    tool_call_name=tool_name,
                    reasoning=tool_reasoning,
                    result_summary=tool_output.result_summary,
                )
                return {
                    "raw_results": tool_output.results,
                    "proceeded_tool_calls_with_reasoning": [proceeded],
                    "reasoning_log": _append_reasoning(
                        f"research_worker[{tool_name}]",
                        tool_output.result_summary,
                    ),
                }
            except Exception as exc:  # pragma: no cover - defensive runtime path
                proceeded = ProceededCall(
                    tool_call_name=tool_name,
                    reasoning=tool_reasoning,
                    result_summary=f"Tool execution failed: {exc}",
                )
                return {
                    "raw_results": [],
                    "proceeded_tool_calls_with_reasoning": [proceeded],
                    "reasoning_log": _append_reasoning(
                        f"research_worker[{tool_name}]",
                        f"Tool execution failed: {exc}",
                    ),
                }

        return run_node("research_worker", state, work)

    def deduplicate_node(state: AgentState) -> dict[str, Any]:
        return run_node(
            "deduplicate",
            state,
            lambda: {"filtered_results": deduplicate_results(state.get("raw_results", []))},
        )

    def mastery_node(state: AgentState) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            results = state.get("filtered_results") or deduplicate_results(state.get("raw_results", []))
            references = _references_from_results(results)
            user_prompt = (
                f"User query: {state['user_query']['mssg']}\n"
                f"Tool calls involved: {state.get('selected_tool_calls', [])}\n"
                f"Reference catalog: {references}\n"
                f"Evidence: {results}\n"
                f"Low confidence mode: {state.get('low_confidence', False)}"
            )

            result = reasoner.parse_structured(
                model=settings.heavy_model,
                system_prompt=_inject_date(MASTERY_SYSTEM_PROMPT),
                user_prompt=user_prompt,
                schema=MasteryOutput,
                temperature=settings.temp_mastery,
            )

            updates: dict[str, Any] = {
                "reasoning_log": _append_reasoning("mastery", result.reasoning),
            }

            if result.status == "accepted" and result.summary is not None:
                updates["summary"] = result.summary
                updates["final_response"] = _format_summary(result.summary, state.get("low_confidence", False))
                return updates

            updates["mastery_feedback"] = result.reasoning
            updates["attempt_count"] = state["attempt_count"] + 1
            return updates

        return run_node("mastery", state, work)

    def route_after_mastery(state: AgentState) -> str:
        if state.get("summary") is not None and state.get("final_response"):
            state["logger"].route("route_after_mastery", END, dict(state))
            return END
        if state["attempt_count"] >= state["MAX_ATTEMPTS"] or _remaining_combinations(state) == 0:
            destination = "exhaustion_fallback"
            state["logger"].route("route_after_mastery", destination, dict(state))
            return destination
        destination = "choose_tools"
        state["logger"].route("route_after_mastery", destination, dict(state))
        return destination

    def exhaustion_fallback_node(state: AgentState) -> dict[str, Any]:
        return run_node(
            "exhaustion_fallback",
            state,
            lambda: {
                "low_confidence": True,
                "summary": (summary := _build_best_effort_summary(
                    state.get("filtered_results") or deduplicate_results(state.get("raw_results", []))
                )),
                "final_response": _format_summary(summary, True),
            },
        )

    builder.add_node("query_review", query_review_node)
    builder.add_node("clarification", clarification_node)
    builder.add_node("improve_query", improve_query_node)
    builder.add_node("choose_tools", choose_tools_node)
    builder.add_node("validator", validator_node)
    builder.add_node("research_worker", research_worker_node)
    builder.add_node("deduplicate", deduplicate_node)
    builder.add_node("mastery", mastery_node)
    builder.add_node("exhaustion_fallback", exhaustion_fallback_node)

    builder.add_edge(START, "query_review")
    builder.add_conditional_edges(
        "query_review",
        route_after_query_review,
        {
            "clarification": "clarification",
            "improve_query": "improve_query",
            "choose_tools": "choose_tools",
        },
    )
    builder.add_edge("clarification", END)
    builder.add_edge("improve_query", "choose_tools")
    builder.add_edge("choose_tools", "validator")
    builder.add_conditional_edges(
        "validator",
        route_after_validator,
        ["choose_tools", "research_worker", "exhaustion_fallback"],
    )
    builder.add_edge("research_worker", "deduplicate")
    builder.add_edge("deduplicate", "mastery")
    builder.add_conditional_edges(
        "mastery",
        route_after_mastery,
        ["choose_tools", "exhaustion_fallback", END],
    )
    builder.add_edge("exhaustion_fallback", END)

    return builder.compile()


@traceable(name="run_agent", run_type="chain")
def run_agent(
    query: str,
    settings: Settings | None = None,
    logger: RunLogger | None = None,
) -> AgentState:
    app_settings = settings or Settings.from_env()
    active_logger = logger or RunLogger()
    graph = build_research_graph(app_settings)
    initial_state: AgentState = {
        "user_query": {"mssg": query, "relevancy": None, "completeness": None},
        "available_tool_calls": DEFAULT_TOOLS[:],
        "tried_combinations": [],
        "proceeded_tool_calls_with_reasoning": [],
        "mastery_feedback": None,
        "attempt_count": 0,
        "MAX_ATTEMPTS": app_settings.max_attempts,
        "low_confidence": False,
        "raw_results": [],
        "filtered_results": [],
        "summary": None,
        "reasoning_log": [],
        "selected_tool_calls": [],
        "pending_tool_jobs": [],
        "clarification_question": None,
        "final_response": None,
        "active_tool_call": None,
        "active_tool_reasoning": None,
        "run_log_path": str(active_logger.log_path),
        "logger": active_logger,
    }
    active_logger.run_start(query, dict(initial_state))
    final_state = graph.invoke(initial_state)
    active_logger.run_end(dict(final_state))
    return final_state
