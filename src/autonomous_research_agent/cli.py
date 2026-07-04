from __future__ import annotations

import argparse

from .graph import run_agent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the autonomous research agent.")
    parser.add_argument("query", nargs="+", help="Research topic or question")
    parser.add_argument(
        "--output",
        help="Optional path to save the final markdown summary.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    query = " ".join(args.query).strip()
    result = run_agent(query)
    final_response = result.get("final_response") or "No response generated."

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file_handle:
            file_handle.write(final_response)

    print(final_response)
    if result.get("run_log_path"):
        print(f"\nRun log saved to: {result['run_log_path']}")


if __name__ == "__main__":
    main()
