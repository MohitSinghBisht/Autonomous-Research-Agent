from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def strip_runtime_fields(state: dict[str, Any]) -> dict[str, Any]:
    filtered = dict(state)
    filtered.pop("logger", None)
    return filtered


def merge_state(base_state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(strip_runtime_fields(base_state))
    for key, value in update.items():
        merged[key] = value
    return merged


class RunLogger:
    def __init__(
        self,
        logs_dir: str | Path = "logs",
        *,
        echo_terminal: bool = True,
        message_callback: Callable[[str], None] | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        root = Path(logs_dir)
        root.mkdir(parents=True, exist_ok=True)
        self.run_id = uuid4().hex[:12]
        self.log_path = root / f"agent_run_{self.run_id}.jsonl"
        self.echo_terminal = echo_terminal
        self.message_callback = message_callback
        self.event_callback = event_callback

    def terminal(self, message: str) -> None:
        formatted = f"[agent] {message}"
        if self.echo_terminal:
            print(formatted, flush=True)
        if self.message_callback is not None:
            self.message_callback(formatted)

    def write_event(self, event: str, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp": _now_iso(),
            "event": event,
            "payload": make_json_safe(payload),
        }
        with self.log_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        if self.event_callback is not None:
            self.event_callback(event, entry)

    def node_start(self, node_name: str, state: dict[str, Any]) -> None:
        self.terminal(f"Starting node: {node_name}")
        self.write_event(
            "node_start",
            {
                "node": node_name,
                "input_state": strip_runtime_fields(state),
            },
        )

    def node_end(self, node_name: str, input_state: dict[str, Any], output_update: dict[str, Any]) -> None:
        merged_state = merge_state(input_state, output_update)
        self.terminal(f"Finished node: {node_name}")
        self.write_event(
            "node_end",
            {
                "node": node_name,
                "input_state": strip_runtime_fields(input_state),
                "output_update": output_update,
                "state_after_node": merged_state,
            },
        )

    def route(self, router_name: str, destination: Any, state: dict[str, Any]) -> None:
        self.terminal(f"Routing from {router_name} to {destination}")
        self.write_event(
            "route",
            {
                "router": router_name,
                "destination": destination,
                "state": strip_runtime_fields(state),
            },
        )

    def run_start(self, query: str, initial_state: dict[str, Any]) -> None:
        self.terminal(f"Run started for query: {query}")
        self.terminal(f"Detailed log file: {self.log_path}")
        self.write_event(
            "run_start",
            {
                "query": query,
                "initial_state": strip_runtime_fields(initial_state),
                "log_path": str(self.log_path),
            },
        )

    def run_end(self, final_state: dict[str, Any]) -> None:
        self.terminal("Run completed")
        self.write_event(
            "run_end",
            {
                "final_state": strip_runtime_fields(final_state),
                "log_path": str(self.log_path),
            },
        )
