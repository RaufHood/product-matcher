# README challenge #1 — strip spec tokens from model names
# README challenge #4 — parse multi-component strings with inconsistent delimiters

import re

NOISE_PATTERN = re.compile(
    r"\b("
    r"\d+(?:gb|tb)|"
    r"dual[-\s]?sim|"
    r"starter\s+kit|"
    r"refurbished|"
    r"bundle|"
    r"lite|"
    r"gen\s*\d+"
    r")\b",
    flags=re.IGNORECASE,
)


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_spec_tokens(text: str) -> str:
    """Challenge #1: remove storage sizes, bundle flags, and market tags from a model name."""
    text = text.replace("‑", "-")
    return normalize_spaces(NOISE_PATTERN.sub(" ", text))


def normalize_manufacturer(raw: str) -> str:
    return normalize_spaces(raw.replace("‑", "-"))


def split_components(raw_components: str | None) -> list[str]:
    """Challenge #4: split a component string regardless of delimiter (/ , ; + & and)."""
    if not raw_components:
        return []
    text = raw_components.replace("‑", "-")
    parts = re.split(r"\s*(?:/|,|;|\+|&|\band\b)\s*", text, flags=re.IGNORECASE)
    return [normalize_spaces(p) for p in parts if normalize_spaces(p)]
