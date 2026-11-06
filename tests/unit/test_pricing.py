from pricing import cost_micro_usd, estimate_input_tokens


def test_cost_is_exact_integer_micro_usd():
    # gpt-4o-mini: $0.15 / 1M input, $0.60 / 1M output -> 0.15 and 0.60 micro-USD per token
    assert cost_micro_usd("gpt-4o-mini", 100, 100) == 75
    assert cost_micro_usd("gpt-4o-mini", 1, 0) == 1        # 0.15 rounds UP
    assert cost_micro_usd("gpt-4o", 1000, 1000) == 20000


def test_unknown_model_uses_expensive_default():
    assert cost_micro_usd("some-new-model", 1, 1) == 40


def test_estimate_counts_text_parts():
    plain = estimate_input_tokens([{"role": "user", "content": "hello world"}], "gpt-4o-mini")
    parts = estimate_input_tokens([{"role": "user", "content": [{"type": "text", "text": "hello world"}]}],
                                  "gpt-4o-mini")
    assert plain == parts > 4


def test_byte_count_fallback_when_tokenizer_unavailable(monkeypatch):
    import pricing

    monkeypatch.setattr(pricing, "_encoding_for", lambda model: None)
    # Upper bound: never fewer tokens than the real tokenizer would count.
    assert pricing.count_text_tokens("héllo", "gpt-4o") == 6
