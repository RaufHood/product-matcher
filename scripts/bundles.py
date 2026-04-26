# README challenge #2 — detect and split bundle / combination product entries

import re

from cleaning import normalize_spaces, strip_spec_tokens

# Separators used to join two model names into a single field
_BUNDLE_SEP = re.compile(r"\s+and\s+|\s*/\s*", flags=re.IGNORECASE)


def split_bundle(raw_model_name: str) -> list[str]:
    """
    Split a raw model name into individual cleaned model names.
    Returns a single-element list when the entry is not a bundle.
    """
    parts = _BUNDLE_SEP.split(raw_model_name)
    cleaned = [strip_spec_tokens(p) for p in parts if strip_spec_tokens(p)]
    return cleaned or [normalize_spaces(raw_model_name)]


def is_bundle(raw_model_name: str) -> bool:
    return len(split_bundle(raw_model_name)) > 1
