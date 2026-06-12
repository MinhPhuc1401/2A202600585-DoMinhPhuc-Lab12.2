from __future__ import annotations

import sys
from pathlib import Path

# Configure stdout and stderr to use UTF-8 encoding on Windows to prevent UnicodeEncodeErrors
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Add src directory to sys.path to enable absolute imports
sys.path.append(str(Path(__file__).resolve().parents[1]))

import argparse
from app.agent.graph import ShoppingAssistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Student scaffold CLI.")
    parser.add_argument("--question", help="Run one question through the graph.")
    parser.add_argument("--test-file", default="data/test.json")
    parser.add_argument("--trace-file", default=None)
    parser.add_argument("--batch", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    assistant = ShoppingAssistant()

    if args.batch:
        test_file_path = Path(args.test_file)
        output_dir = Path("app/artifacts/batch_run")
        print(f"Starting batch run using test file: {test_file_path}")
        assistant.run_batch(test_file_path, output_dir)
    elif args.question:
        question = args.question
        trace_file_path = Path(args.trace_file) if args.trace_file else None
        print(f"Running single question: {question}")
        result = assistant.ask(question, trace_file=trace_file_path)
        print("\n=== FINAL ANSWER ===")
        print(result.get("final_answer", ""))
        print("====================\n")
    else:
        print("Please provide either --question or --batch argument.")


if __name__ == "__main__":
    main()
