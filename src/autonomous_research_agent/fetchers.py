from __future__ import annotations

from langsmith import traceable
from tavily import TavilyClient

from .config import Settings
from .models import RawResult, ResearchToolOutput


# ---------------------------------------------------------------------------
# Tool behaviour descriptions (used in reasoning_log / tracing)
# ---------------------------------------------------------------------------
TOOL_BEHAVIOR = {
    "general_web_search": "Search broadly across the public web for the most directly relevant sources.",
    "official_docs_search": "Prioritize official documentation, standards pages, government sites, and primary sources.",
    "expert_analysis_search": "Prioritize strong secondary analysis from reputable experts or organizations.",
}

# ---------------------------------------------------------------------------
# Per-tool Tavily call profiles
# Keys:
#   include_domains  – passed directly to TavilyClient.search(); empty list = no restriction
#   query_suffix     – appended to the query string before the Tavily call
# ---------------------------------------------------------------------------
TOOL_PROFILES: dict[str, dict] = {
    "general_web_search": {
        "include_domains": [],
        "query_suffix": "",
    },
    "official_docs_search": {
        "include_domains": [
            "nih.gov",
            "who.int",
            "europa.eu",
            "gov.uk",
            "un.org",
            "ieee.org",
            "w3.org",
            "nist.gov",
            "cdc.gov",
        ],
        "query_suffix": "",
    },
    "expert_analysis_search": {
        "include_domains": [
            "brookings.edu",
            "rand.org",
            "economist.com",
            "nature.com",
            "sciencedirect.com",
            "foreignaffairs.com",
            "ft.com",
        ],
        "query_suffix": " expert analysis",
    },
}


class TavilyFetcher:
    """Thin wrapper around TavilyClient that maps tool names to search profiles."""

    def __init__(self, settings: Settings) -> None:
        self.client = TavilyClient(api_key=settings.tavily_api_key)

    def search(self, *, query: str, tool_name: str) -> ResearchToolOutput:
        profile = TOOL_PROFILES.get(tool_name, TOOL_PROFILES["general_web_search"])
        full_query = (query + profile["query_suffix"]).strip()

        kwargs: dict = {
            "query": full_query,
            "search_depth": "basic",
            "max_results": 5,
        }
        if profile["include_domains"]:
            kwargs["include_domains"] = profile["include_domains"]

        response = self.client.search(**kwargs)
        raw_results = response.get("results", [])

        if not raw_results:
            return ResearchToolOutput(
                result_summary=(
                    "No results returned by Tavily within the domain restriction for this tool. "
                    "Other tools in this batch may still have usable evidence."
                ),
                results=[],
            )

        results = [
            RawResult(
                source_tool=tool_name,
                title=r.get("title", "Untitled"),
                url=r.get("url"),
                content=r.get("content", ""),
            )
            for r in raw_results
        ]

        result_summary = f"Tavily returned {len(results)} result(s) via {tool_name}."
        return ResearchToolOutput(result_summary=result_summary, results=results)


@traceable(run_type="tool", name="fetch_with_tool")
def fetch_with_tool(
    *,
    fetcher: TavilyFetcher,
    query: str,
    tool_name: str,
    tool_reasoning: str,
) -> ResearchToolOutput:
    """Invoke the appropriate Tavily search profile for the given tool name."""
    return fetcher.search(query=query, tool_name=tool_name)
