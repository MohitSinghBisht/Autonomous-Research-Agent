# Autonomous Research Agent — Build Specification

## Constraints (non-negotiable — assignment requirement)
- No hardcoded responses, predefined rule-based decisions, or static outputs for anything that requires judgment.
- Query relevancy/completeness check, tool selection, validation, relevance filtering, and synthesis MUST be LLM reasoning calls.
- Exception: deduplication may use a non-LLM heuristic (string/embedding similarity) — this is data hygiene, not a judgment call. State this explicitly in the README.
- Every LLM decision node must log its reasoning to `reasoning_log` in state, for traceability.
- Fan-out (number of parallel tool calls) is Validator-decided but must respect the shared attempt/combination budget below.

---

## 1. State schema

```
AgentState:
  user_query:
    mssg: str
    relevancy: bool | None
    completeness: bool | None

  available_tool_calls: list[str]          # fixed registry, e.g. ["api", "docs", "web_search"]
  tried_combinations: list[list[str]]       # every tool-call combination already attempted this run
  proceeded_tool_calls_with_reasoning: list[ProceededCall]   # running history across attempts

  mastery_feedback: str | None              # reasoning from Mastery Agent's last rejection,
                                             # passed back into Choose Tools/Validator on retry

  attempt_count: int                        # SHARED budget across Validator-rejection retries
  MAX_ATTEMPTS: int                         # AND Mastery Agent failure retries — one counter, not two

  low_confidence: bool                      # set true if budget exhausted without a passing result

  raw_results: list[RawResult]
  filtered_results: list[RawResult]
  summary: Summary | None
  reasoning_log: list[str]

ProceededCall:
  tool_call_name: str
  reasoning: str
  result_summary: str | None

RawResult:
  source_tool: str
  title: str
  url: str | None
  content: str

Finding:
  claim: str
  source_id: str

Reference:
  id: str
  title: str
  url: str | None
  source_tool: str

Summary:
  key_points: list[str]
  findings: list[Finding]
  references: list[Reference]
  actionable_insights: list[str] | None
```

---

## 2. Node specs (LLM structured output for each, except dedup)

### Node 1 — Query Completeness & Relevancy (cheap model)
Input: `user_query.mssg`
Output:
```
{ "completeness": boolean, "relevant": boolean, "user_mssg": str , "reasoning" : str}
```
Routing:
- `relevant=false` → Clarification (Node 2b), **regardless of completeness**
- `relevant=true, completeness=false` → Improve Query (Node 2a)
- `relevant=true, completeness=true` → straight to Choose Tools / Validator loop

### Node 2a — Improve Query (cheap model)
Output: `{ "improved_mssg": str }`
Feeds directly into Choose Tools — deliberately **not** re-run through Node 1. One-shot only, to avoid infinite recursion on adversarial input.

### Node 2b — Clarification (interrupt)
Uses LangGraph `interrupt()` to pause the graph, persist state via a checkpointer, and resume from this exact point when the user replies — not a restart from scratch.
Scope note: treat the full pause/resume round-trip as bonus-tier. If time-constrained, stub this as "return a clarification question and end the run."

### Node 3 — Choose Tools (mid-tier model)
Output:
```
{ "tool_selected": [str, ...], "reasoning": str }
```
Constraint: `tool_selected` must not match any entry already in `tried_combinations`.

### Node 4 — Validator Agent (mid-tier model)
Output:
```
{
  "re-iterate": boolean,
  "available_tool_list": [str, ...],
  "rejection_reasoning": [{ "tool_call_name": str, "reasoning": str }],
  "spawn_agent_metadata": {
    "trigger": bool,
    "sub_agent_data": [
      { "agent_name": str, "tool_call": str, "reasoning": str }
    ]
  }
}
```
Loop: Choose Tools ↔ Validator Agent, bounded by `attempt_count < MAX_ATTEMPTS` **and** unexplored combinations remaining in `available_tool_calls`. On rejection, append the rejected combination to `tried_combinations` before retrying.

### Node 5 — Spawn Sub Agents (parallel fan-out, cheap tool-calling model)
One sub-agent per entry in `spawn_agent_metadata.sub_agent_data`, `n` decided dynamically by the Validator. Fan out via LangGraph `Send`, merge results back into a flat list. Then run non-LLM dedup on the merged list.

### Node 6 — Mastery Agent (heavy model)
Output:
```
{
  "status": "accepted" | "rejected",
  "tool_calls_involved": [str, ...],
  "reasoning": str,
  "response": str
}
```
Also owns: relevance filtering of extracted content and final formatting (dedup happens before this node, not inside it).
Routing:
- `accepted` → Response → END → User
- `rejected` → write `reasoning` into `mastery_feedback` → route back into the **same** Choose Tools/Validator loop (shared `attempt_count`, not a separate retry mechanism), with `mastery_feedback` available as context so it doesn't re-select the same failing combination.

### Node 7 — Exhaustion fallback (new — was implicit, now explicit)
Triggered when `attempt_count >= MAX_ATTEMPTS` **or** no unexplored combinations remain, and Mastery Agent has not yet accepted.
Action: proceed to Response using the best available `raw_results`/`filtered_results` so far, with `low_confidence: true` set in state and surfaced in the response text (e.g. "This answer may be incomplete — available sources didn't fully resolve the query"). Do **not** loop further or error out silently.

---

## 3. Build order

1. Project skeleton (folders, `requirements.txt`, `.env.example`)
2. Pydantic models — all schemas above
3. Query Completeness & Relevancy node — test standalone against relevant/irrelevant × complete/incomplete test queries
4. Improve Query node — test standalone
5. Clarification stub (simple return + end; defer full `interrupt()` if time-constrained)
6. Single-source fetch function (web search + trafilatura)
7. Choose Tools node — start forcing single-tool selection to unblock an end-to-end test
8. **Checkpoint**: linear happy path — query → completeness/relevancy → (improve if needed) → Choose Tools → fetch → Mastery Agent (stub as pass-through) → Response. Get this fully working before anything else.
9. Validator Agent node + retry loop, with `tried_combinations` tracking and the shared `attempt_count`
10. Second source fetch function
11. Parallel fan-out via `Send` (Spawn Sub Agents)
12. Dedup node (heuristic, non-LLM) on merged results
13. Mastery Agent full implementation: relevance filter + synthesis + accept/reject decision
14. Wire Mastery Agent's `rejected` path back into the Choose Tools/Validator loop
15. Implement the exhaustion fallback (Node 7) — don't skip this, it's the one gap that isn't self-evident from the diagram
16. Markdown export
17. README + installation steps
18. Edge case pass: irrelevant query, persistently-incomplete query, all tool combinations rejected, one source timing out

---

## 4. Known gaps to state explicitly in the README (not oversights — deliberate scope calls)
- Cache-hit path's downstream destination is undefined — deferred as bonus scope.
- Improved queries are not re-verified for completeness/relevancy — deliberate, to avoid infinite recursion on adversarial input.
- Full clarification round-trip (`interrupt()`/resume) may be stubbed rather than fully implemented depending on time.
- Exhaustion fallback returns a best-effort, explicitly flagged low-confidence answer rather than guaranteeing a fully validated one.

---

## 5. Definition of done
- [ ] Runs end to end on a real query with 2 sources
- [ ] Irrelevant query routes to clarification; incomplete-but-relevant query routes to Improve Query
- [ ] Choose Tools/Validator loop never re-attempts an already-tried combination
- [ ] Mastery Agent rejection correctly feeds back into the same loop with reasoning, not a separate path
- [ ] Exhaustion fallback produces a flagged low-confidence response instead of looping indefinitely or crashing
- [ ] Parallel fan-out actually executes concurrently
- [ ] Every Finding traces to a real Reference
- [ ] reasoning_log has an entry from every LLM node
- [ ] README documents all four known-gap scope decisions above