import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from pipeline_tui.server import server_status, worktrees_size


class MockHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"BOARD-TYPE": "BOARD-1", "PROVIDER": "example"}).encode()
        self.send_response(200 if self.path == "/device-cfg.json" else 404)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def test_counts_worktrees_and_reads_the_mock_board(tmp_path: Path) -> None:
    worktrees = tmp_path / ".claude" / "worktrees"
    (worktrees / "ABC-1" / "node_modules").mkdir(parents=True)
    (worktrees / "ABC-2").mkdir()
    mock = HTTPServer(("127.0.0.1", 0), MockHandler)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    try:
        status = server_status(tmp_path, f"http://127.0.0.1:{mock.server_port}")
    finally:
        mock.shutdown()

    assert (status.worktrees, status.with_node_modules, status.mock_board) == (2, 1, "BOARD-1")
    assert 0 < status.disk_free <= status.disk_total


def test_no_worktrees_and_no_mock(tmp_path: Path) -> None:
    status = server_status(tmp_path, "http://127.0.0.1:9")

    assert (status.worktrees, status.with_node_modules, status.mock_board) == (0, 0, None)
    assert worktrees_size(tmp_path) == 0


def test_worktrees_size_counts_their_files(tmp_path: Path) -> None:
    worktree = tmp_path / ".claude" / "worktrees" / "ABC-1"
    worktree.mkdir(parents=True)
    (worktree / "big").write_bytes(b"x" * 100_000)

    assert worktrees_size(tmp_path) >= 100_000
