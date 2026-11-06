"""Unmasking placeholders in a streamed (SSE) response.

The upstream model streams text in small chunks, so a placeholder such as
"[REDACTED_EMAIL_1]" can arrive split as "[REDAC" + "TED_EMAIL_1]".
StreamUnmasker holds back only the part of the text that could still turn
into a placeholder, and releases everything else immediately.

Why only the text after the LAST "[" can be held back: every placeholder
starts with "[" and contains no other "[". So any unfinished placeholder at
the end of the buffer must start at the last "[".
"""
import json
from typing import Dict, List, Optional

from pii import unmask_text


class StreamUnmasker:
    def __init__(self, mappings: Dict[str, str]) -> None:
        self.mappings = mappings
        self.placeholders = list(mappings)
        self.buffer = ""

    def _could_be_placeholder_start(self, tail: str) -> bool:
        # True if `tail` is the beginning (but not the whole) of a placeholder.
        return any(len(tail) < len(p) and p.startswith(tail) for p in self.placeholders)

    def feed(self, chunk: str) -> str:
        """Add a chunk from upstream; return text that is safe to send now."""
        self.buffer += chunk
        if not self.mappings:
            ready, self.buffer = self.buffer, ""
            return ready

        cut = len(self.buffer)
        last_open = self.buffer.rfind("[")
        if last_open != -1 and self._could_be_placeholder_start(self.buffer[last_open:]):
            cut = last_open

        ready, self.buffer = self.buffer[:cut], self.buffer[cut:]
        return unmask_text(ready, self.mappings)

    def flush(self) -> str:
        """Return whatever is still buffered. Call when the stream ends for ANY reason."""
        rest, self.buffer = self.buffer, ""
        return unmask_text(rest, self.mappings)


def sse(data: str) -> str:
    return f"data: {data}\n\n"


class SseUnmaskRelay:
    """Rewrites an OpenAI-style SSE stream line by line.

    process_line() takes one line from upstream and returns the SSE events
    to send to the client. finish() must be called when the upstream stream
    ends (normally, early, or with an error) so buffered text is not lost.
    """

    def __init__(self, mappings: Dict[str, str]) -> None:
        self.mappings = mappings
        self.unmaskers: Dict[int, StreamUnmasker] = {}  # one per choice index
        self.usage: Optional[dict] = None
        self.masked_parts: List[str] = []   # what upstream sent (still masked)
        self.done = False
        self._last_chunk: dict = {}

    def _unmasker(self, index: int) -> StreamUnmasker:
        if index not in self.unmaskers:
            self.unmaskers[index] = StreamUnmasker(self.mappings)
        return self.unmaskers[index]

    def _flush_events(self) -> List[str]:
        events = []
        for index, unmasker in self.unmaskers.items():
            rest = unmasker.flush()
            if rest:
                chunk = {
                    "id": self._last_chunk.get("id", ""),
                    "object": "chat.completion.chunk",
                    "created": self._last_chunk.get("created", 0),
                    "model": self._last_chunk.get("model", ""),
                    "choices": [{"index": index, "delta": {"content": rest}, "finish_reason": None}],
                }
                events.append(sse(json.dumps(chunk)))
        return events

    def process_line(self, line: str) -> List[str]:
        if not line:
            return []  # blank separator lines; we add our own
        if not line.startswith("data:"):
            return [line + "\n"]  # comments / other SSE fields pass through

        data = line[5:].strip()
        if data == "[DONE]":
            self.done = True
            return self._flush_events() + [sse("[DONE]")]

        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return [line + "\n\n"]
        if not isinstance(chunk, dict):
            return [line + "\n\n"]

        self._last_chunk = chunk
        if chunk.get("usage"):
            self.usage = chunk["usage"]

        events: List[str] = []
        send_chunk = True
        for choice in chunk.get("choices") or []:
            index = choice.get("index", 0)
            delta = choice.get("delta") or {}
            content = delta.get("content")
            finished = choice.get("finish_reason") is not None

            if isinstance(content, str) and content:
                self.masked_parts.append(content)
                text = self._unmasker(index).feed(content)
                if finished:
                    text += self._unmasker(index).flush()
                delta["content"] = text
                if not text and len(chunk["choices"]) == 1 and not finished:
                    send_chunk = False  # everything was held back; nothing to send yet
            elif finished and index in self.unmaskers:
                # finish_reason chunk without text: release held text first.
                rest = self.unmaskers[index].flush()
                if rest:
                    delta["content"] = rest
                    choice["delta"] = delta

        if send_chunk:
            events.append(sse(json.dumps(chunk)))
        return events

    def finish(self) -> List[str]:
        """Flush anything still buffered if upstream ended without [DONE]."""
        if self.done:
            return []
        return self._flush_events()

    def masked_text(self) -> str:
        return "".join(self.masked_parts)
