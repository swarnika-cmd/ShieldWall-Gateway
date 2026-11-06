import json

from hypothesis import given, settings
from hypothesis import strategies as st

from pii import unmask_text
from streaming import SseUnmaskRelay, StreamUnmasker

MAPPINGS = {
    "[REDACTED_EMAIL_1]": "alice@example.com",
    "[REDACTED_EMAIL_2]": "bob@example.com",
    "[REDACTED_IN_MOBILE_1]": "+91 98765 43210",
    "[REDACTED_EMAIL_10]": "ten@example.com",
}


def run_stream(chunks, mappings=MAPPINGS):
    unmasker = StreamUnmasker(mappings)
    out = "".join(unmasker.feed(c) for c in chunks)
    return out + unmasker.flush()


def split_at(text, cuts):
    cuts = sorted(set(c for c in cuts if 0 < c < len(text)))
    pieces, start = [], 0
    for c in cuts:
        pieces.append(text[start:c])
        start = c
    pieces.append(text[start:])
    return pieces


def test_placeholder_split_across_chunks():
    chunks = ["Hi [RED", "ACTED_EM", "AIL_1] and [REDACTED_EMAIL_", "2]!"]
    assert run_stream(chunks) == "Hi alice@example.com and bob@example.com!"


def test_text_is_released_as_soon_as_it_is_safe():
    unmasker = StreamUnmasker(MAPPINGS)
    assert unmasker.feed("Hello [RED") == "Hello "
    assert unmasker.feed("ACTED_EMAIL_1] bye") == "alice@example.com bye"


def test_brackets_that_cannot_be_placeholders_are_not_held():
    unmasker = StreamUnmasker(MAPPINGS)
    assert unmasker.feed("list[0] = [x") == "list[0] = [x"


def test_flush_returns_unfinished_placeholder_text():
    # v1 bug: if the stream ended here, "[REDACTED_EM" was silently dropped.
    unmasker = StreamUnmasker(MAPPINGS)
    assert unmasker.feed("end [REDACTED_EM") == "end "
    assert unmasker.flush() == "[REDACTED_EM"


def test_no_mappings_passes_through():
    assert run_stream(["a [b", "c"], mappings={}) == "a [bc"


FILLER = st.text(alphabet="abc [_]REDACTEMIL0123456789\n", max_size=30)


@settings(max_examples=500, deadline=None)
@given(
    parts=st.lists(st.tuples(FILLER, st.sampled_from(sorted(MAPPINGS))), max_size=6),
    tail=FILLER,
    cuts=st.lists(st.integers(min_value=0, max_value=400), max_size=25),
)
def test_streaming_equals_non_streaming_for_any_split(parts, tail, cuts):
    """Whatever the chunk boundaries, streamed output == unmasking the whole text at once."""
    masked = "".join(f + p for f, p in parts) + tail
    assert run_stream(split_at(masked, cuts)) == unmask_text(masked, MAPPINGS)


@settings(max_examples=500, deadline=None)
@given(
    parts=st.lists(st.tuples(st.text(alphabet="xyz .,\n", max_size=20),
                             st.sampled_from(sorted(MAPPINGS))), max_size=6),
    cuts=st.lists(st.integers(min_value=0, max_value=400), max_size=25),
)
def test_streaming_restores_original_text(parts, cuts):
    masked = "".join(f + p for f, p in parts)
    original = "".join(f + MAPPINGS[p] for f, p in parts)
    assert run_stream(split_at(masked, cuts)) == original


# --- SSE relay -------------------------------------------------------------

def sse_line(content=None, finish=None, usage=None):
    chunk = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": []}
    if content is not None or finish is not None:
        delta = {"content": content} if content is not None else {}
        chunk["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish}]
    if usage:
        chunk["usage"] = usage
    return "data: " + json.dumps(chunk)


def client_text(events):
    text = ""
    for event in events:
        if event.startswith("data: ") and "[DONE]" not in event:
            for choice in json.loads(event[6:]).get("choices", []):
                text += choice.get("delta", {}).get("content") or ""
    return text


def test_relay_flushes_when_upstream_ends_without_done():
    relay = SseUnmaskRelay(MAPPINGS)
    events = []
    for line in [sse_line("Mail [REDACTED_"), "", sse_line("EMAIL_1] now [REDACTED_EM")]:
        events += relay.process_line(line)
    events += relay.finish()  # upstream connection closed, no [DONE]
    assert client_text(events) == "Mail alice@example.com now [REDACTED_EM"


def test_relay_flushes_before_finish_reason_and_done():
    relay = SseUnmaskRelay(MAPPINGS)
    events = []
    for line in [sse_line("x [REDACTED_EMAIL_"), sse_line(None, finish="stop"),
                 sse_line(usage={"prompt_tokens": 3, "completion_tokens": 2}), "data: [DONE]"]:
        events += relay.process_line(line)
    events += relay.finish()
    assert client_text(events) == "x [REDACTED_EMAIL_"
    assert events[-1] == "data: [DONE]\n\n"
    assert relay.usage == {"prompt_tokens": 3, "completion_tokens": 2}
    assert relay.masked_text() == "x [REDACTED_EMAIL_"


def test_relay_passes_through_non_json_and_comments():
    relay = SseUnmaskRelay(MAPPINGS)
    assert relay.process_line(": keep-alive") == [": keep-alive\n"]
    assert relay.process_line("data: not-json") == ["data: not-json\n\n"]
