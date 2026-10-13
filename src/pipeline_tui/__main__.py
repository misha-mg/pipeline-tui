import argparse
from pathlib import Path

from .app import RunsApp


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline-tui", description="Browse the webui ticket-pipeline runs.")
    parser.add_argument(
        "runs",
        nargs="?",
        type=Path,
        default=Path(".pipeline-runs"),
        help="the .pipeline-runs directory of the webui main checkout (default: ./.pipeline-runs)",
    )
    args = parser.parse_args()
    if not args.runs.is_dir():
        parser.error(f"not a directory: {args.runs}")
    RunsApp(args.runs.resolve()).run()


if __name__ == "__main__":
    main()
