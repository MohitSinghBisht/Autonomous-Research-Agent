from __future__ import annotations

from langsmith import traceable

from .llm import OpenAIReasoner
from .models import ResearchToolOutput
from .prompts import FETCH_SYSTEM_PROMPT


TOOL_BEHAVIOR = {
    "general_web_search": "Search broadly across the public web for the most directly relevant sources.",
    "official_docs_search": "Prioritize official documentation, standards pages, government sites, and primary sources.",
    "expert_analysis_search": "Prioritize strong secondary analysis from reputable experts or organizations.",
}


@traceable(run_type="tool", name="fetch_with_tool")
def fetch_with_tool(
    *,
    reasoner: OpenAIReasoner,
    model: str,
    query: str,
    tool_name: str,
    tool_reasoning: str,
) -> ResearchToolOutput:
    behavior = TOOL_BEHAVIOR.get(tool_name, "Search the web for relevant information.")
    user_prompt = f"""
Query: {query}
Tool name: {tool_name}
Tool-specific intent: {behavior}
Why this tool was selected: {tool_reasoning}

Collect relevant source material and return structured output.
""".strip()

    return reasoner.parse_structured(
        model=model,
        system_prompt=FETCH_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=ResearchToolOutput,
        use_web_search=True,
    )
