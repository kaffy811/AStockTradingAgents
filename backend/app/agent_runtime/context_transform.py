"""Context transform helpers for Pi-compatible runtime."""
from __future__ import annotations

from typing import Iterable

from app.agent_runtime.contracts import PiAgentMessage


class PiContextTransform:
    """Keep pinned financial context separate from conversational trimming."""

    def __init__(self, *, max_message_chars: int = 12000, keep_recent_messages: int = 8) -> None:
        self.max_message_chars = max_message_chars
        self.keep_recent_messages = keep_recent_messages

    def select_messages(self, messages: Iterable[PiAgentMessage]) -> list[PiAgentMessage]:
        recent = list(messages)[-self.keep_recent_messages :]
        selected: list[PiAgentMessage] = []
        total = 0
        for message in reversed(recent):
            text = str(message.content)
            size = len(text)
            if selected and total + size > self.max_message_chars:
                break
            total += size
            selected.append(message)
        return list(reversed(selected))
