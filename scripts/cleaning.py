# README challenge #1 — strip spec tokens from model names
# README challenge #4 — parse multi-component strings with inconsistent delimiters
# README challenge #5 — strip manufacturer brand appended to generic product names

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
    # top_model_words.py ranks 2–18 (mini, air, se, ultra, pro, max, plus, edge) look
    # frequent but are model-tier suffixes that the README explicitly keeps in the
    # canonical name (e.g. "AzureRouter SE Ultra 64GB Starter Kit" → "AzureRouter SE Ultra").
    # Adding them causes false cross-variant matches. Ranks 21–100 are product-name words
    # (echophone, kernel, core, stack, …) — never noise. Nothing new to add here.
    r")\b",
    flags=re.IGNORECASE,
)

# Legal / entity-type words that follow the brand in manufacturer_of_record strings.
# e.g. "Copperline Holdings Inc." → brand = "Copperline"
_MFR_SUFFIX = re.compile(
    r"\s+(?:Components|Devices|Electronics|Group|Holdings|Industries|Labs|"
    r"Manufacturing|Networks|Systems|Technologies|Works|Inc\.?|LLC|AG|BV|SL|"
    r"Ltd\.?|GmbH)\b.*$",
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


def extract_brand_from_manufacturer(manufacturer: str) -> str:
    """Challenge #5: extract the brand token from a manufacturer_of_record string.

    'Copperline Holdings Inc.' → 'Copperline'
    'GoldenGate Networks Inc.' → 'GoldenGate'
    """
    if not manufacturer:
        return ""
    clean = normalize_manufacturer(manufacturer)
    return _MFR_SUFFIX.sub("", clean).strip()


def strip_manufacturer_suffix(model_name: str, manufacturer: str) -> str:
    """Challenge #5: remove a manufacturer brand that was appended to a generic product name.

    'Cinder Stack Copperline', 'Copperline Holdings Inc.' → 'Cinder Stack'
    'Vega Beam GoldenGate',    'GoldenGate Networks Inc.' → 'Vega Beam'
    """
    brand = extract_brand_from_manufacturer(manufacturer)
    if not brand:
        return model_name
    pattern = re.compile(r"\s+" + re.escape(brand) + r"\s*$", flags=re.IGNORECASE)
    return normalize_spaces(pattern.sub("", model_name))


def split_components(raw_components: str | None) -> list[str]:
    """Challenge #4: split a component string regardless of delimiter (/ , ; + & and)."""
    if not raw_components:
        return []
    text = raw_components.replace("‑", "-")
    parts = re.split(r"\s*(?:/|,|;|\+|&|\band\b)\s*", text, flags=re.IGNORECASE)
    return [normalize_spaces(p) for p in parts if normalize_spaces(p)]
