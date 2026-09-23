"""Test helper: a fake transport implementing the SerialTransport interface."""

from __future__ import annotations

from collections import deque


class FakeTransport:
    """Stand-in for :class:`pinefeat_focuser.device.SerialTransport`.

    Responses can be queued per-command (a mapping of command -> deque of
    responses) or a single default response callable can be supplied.
    """

    def __init__(self, responses: dict[str, object] | None = None):
        self.responses = {k: deque(v if isinstance(v, list) else [v]) for k, v in (responses or {}).items()}
        self.sent: list[str] = []
        self.is_open = True

    def send(self, command: str) -> str:
        self.sent.append(command)
        if command not in self.responses or not self.responses[command]:
            raise AssertionError(f"No canned response for command {command!r}")
        return self.responses[command].popleft()

    def close(self) -> None:
        self.is_open = False
