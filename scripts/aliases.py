# README challenge #3 — resolve multilingual / market-specific component aliases
# to their canonical English names from component_list.json

import json
import sqlite3
from pathlib import Path

from db import upsert_name_entity

ROOT = Path(__file__).resolve().parent.parent


def load_canonical_components(conn: sqlite3.Connection) -> None:
    """Seed the components table from data/component_list.json."""
    path = ROOT / "data" / "component_list.json"
    names: list[str] = json.loads(path.read_text(encoding="utf-8"))
    for name in names:
        upsert_name_entity(conn, "components", "canonical_name", name)
    conn.commit()
    print(f"[aliases] seeded {len(names)} canonical components")


def resolve_component(conn: sqlite3.Connection, raw_component: str) -> int | None:
    """
    Challenge #3: map a raw (possibly localized) component name to a canonical component_id.
    Checks the components table for an exact match first, then falls back to component_aliases.
    Returns None when the name cannot be resolved.
    """
    row = conn.execute(
        "SELECT id FROM components WHERE canonical_name = ?", (raw_component,)
    ).fetchone()
    if row:
        return int(row[0])

    row = conn.execute(
        "SELECT component_id FROM component_aliases WHERE alias_name = ?", (raw_component,)
    ).fetchone()
    if row:
        return int(row[0])

    return None
