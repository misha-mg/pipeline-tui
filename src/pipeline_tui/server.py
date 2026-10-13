"""The pipeline server's state: disk, ticket worktrees, and the device mock app tests run against.

Each run gets its own worktree in the main checkout's `.claude/worktrees/`, with a
`node_modules` of its own until the run drops it; old worktrees stay. The mock answers
`GET <mock>/device-cfg.json` with its BOARD-TYPE.
"""

from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# The mock's address, as tools/device-mock/rpc.sh has it.
MOCK_URL = "https://127.0.0.1:8888"
MOCK_TIMEOUT_SECONDS = 2


@dataclass(frozen=True)
class ServerStatus:
    disk_free: int
    disk_total: int
    worktrees: int
    with_node_modules: int
    # The BOARD-TYPE the mock answers with; None when it does not answer.
    mock_board: str | None


def server_status(main: Path, mock_url: str = MOCK_URL) -> ServerStatus:
    """Quick to read, but waits up to MOCK_TIMEOUT_SECONDS for the mock: call it off the UI thread."""
    disk = shutil.disk_usage(main)
    worktrees = _worktrees(main)
    return ServerStatus(
        disk_free=disk.free,
        disk_total=disk.total,
        worktrees=len(worktrees),
        with_node_modules=sum((w / "node_modules").is_dir() for w in worktrees),
        mock_board=_mock_board(mock_url),
    )


def worktrees_size(main: Path) -> int:
    """Disk space the worktrees take, in bytes. Slow, tens of seconds on a server full of node_modules."""
    folder = main / ".claude" / "worktrees"
    if not folder.is_dir():
        return 0
    # Blocks on disk, not file sizes: node_modules is many small files, each filling a whole block.
    result = subprocess.run(["du", "-sk", str(folder)], capture_output=True, text=True)
    return int(result.stdout.split()[0]) * 1024 if result.stdout else 0


def _worktrees(main: Path) -> list[Path]:
    folder = main / ".claude" / "worktrees"
    return [p for p in folder.iterdir() if p.is_dir()] if folder.is_dir() else []


def _mock_board(mock_url: str) -> str | None:
    # The mock's certificate is self-signed; a proxy in the environment must not carry localhost.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
    )
    try:
        with opener.open(f"{mock_url}/device-cfg.json", timeout=MOCK_TIMEOUT_SECONDS) as response:
            return json.load(response)["BOARD-TYPE"]
    except (OSError, ValueError, KeyError):
        return None
