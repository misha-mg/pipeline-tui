import argparse
from pathlib import Path

from .app import RunsApp
from .bitbucket import CACHE_FILE, Bitbucket, PullRequests, load_token


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
    token = load_token()
    pull_requests = PullRequests(CACHE_FILE, Bitbucket(token) if token else None)
    RunsApp(args.runs.resolve(), pull_requests=pull_requests).run()


if __name__ == "__main__":
    main()
