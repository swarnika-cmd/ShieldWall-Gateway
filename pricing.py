"""Token counting and cost calculation.

Money is handled as whole MICRO-DOLLARS (1 USD = 1,000,000 micro-USD) so
that Redis can add and compare amounts exactly with integer commands.
Handy fact: a price of "X USD per 1M tokens" is exactly "X micro-USD per token".
"""
import logging
import math
from functools import lru_cache
from typing import Any, Dict, List

import tiktoken

logger = logging.getLogger("shieldwall.pricing")

# USD per 1M tokens (= micro-USD per token): (input, output)
MODEL_PRICES: Dict[str, tuple] = {
    # OpenAI
    "gpt-4o": (5.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    # Groq
    "llama3-8b-8192": (0.05, 0.08),
    "llama3-70b-8192": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama-3.1-70b-versatile": (0.59, 0.79),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "mixtral-8x7b-32768": (0.24, 0.24),
    "gemma2-9b-it": (0.20, 0.20),
}
# Unknown models are charged at an expensive rate so budgets stay safe.
DEFAULT_PRICE = (10.00, 30.00)


@lru_cache(maxsize=64)
def _encoding_for(model: str):
    """The tiktoken encoding for a model, or None if it cannot be loaded.

    tiktoken downloads its vocabulary files on first use; the Docker image
    caches them at build time. If they are unavailable we return None.
    """
    try:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        logger.warning("tiktoken unavailable (%s); using byte-count upper bound", exc)
        return None


def count_text_tokens(text: str, model: str) -> int:
    encoding = _encoding_for(model)
    if encoding is None:
        # Byte-level BPE tokens are at least one byte long, so the UTF-8 byte
        # count can never be lower than the real token count (safe for budgets).
        return len(text.encode("utf-8"))
    return len(encoding.encode(text))


def estimate_input_tokens(messages: List[Dict[str, Any]], model: str) -> int:
    """Approximate prompt tokens (OpenAI chat format: ~4 tokens overhead per message)."""
    tokens = 2
    for message in messages:
        tokens += 4
        content = message.get("content")
        if isinstance(content, str):
            tokens += count_text_tokens(content, model)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    tokens += count_text_tokens(part["text"], model)
        if isinstance(message.get("role"), str):
            tokens += count_text_tokens(message["role"], model)
    return tokens


def cost_micro_usd(model: str, input_tokens: int, output_tokens: int) -> int:
    """Cost rounded UP to a whole micro-dollar (never under-charge)."""
    input_price, output_price = MODEL_PRICES.get(model, DEFAULT_PRICE)
    exact = input_tokens * input_price + output_tokens * output_price
    # round() first removes float noise such as 15.000000000000002
    return math.ceil(round(exact, 6))


def micro_to_usd(micro: int) -> float:
    return micro / 1_000_000
