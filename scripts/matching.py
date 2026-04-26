# Orchestrates all matching challenges:
#   challenge #2 (bundles)  — via bundles.split_bundle
#   challenge #3 (aliases)  — via aliases.resolve_component
#   challenge #4 (components) — via cleaning.split_components
#   challenge #5 (generic products) — TODO: detect "component + manufacturer suffix" pattern

import sqlite3

from aliases import resolve_component
from bundles import split_bundle
from cleaning import (
    normalize_manufacturer,
    split_components,
    strip_spec_tokens,
    strip_manufacturer_suffix,
)
from db import upsert_name_entity


def _get_or_create_component(conn: sqlite3.Connection, raw_name: str) -> int:
    """Challenge #3: resolve via alias table before falling back to upsert."""
    component_id = resolve_component(conn, raw_name)
    if component_id is None:
        component_id = upsert_name_entity(conn, "components", "canonical_name", raw_name)
    return component_id


def run_matching_pipeline(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, raw_model_name, raw_core_components, raw_manufacturer_of_record
        FROM source_products
        ORDER BY id
        """
    ).fetchall()

    for source_product_id, raw_model, raw_components, raw_manufacturer in rows:
        normalized_manufacturer = normalize_manufacturer(raw_manufacturer)
        manufacturer_id = upsert_name_entity(
            conn, "manufacturers", "canonical_name", normalized_manufacturer
        )

        # Challenge #4: parse component list
        parsed_components = split_components(raw_components)

        # Challenge #2: split bundle model names
        model_parts = split_bundle(raw_model)
        match_type = "bundle_part" if len(model_parts) > 1 else "direct"

        # Challenge #1 + #5: strip spec tokens and manufacturer suffix from each part
        normalized_parts = [
            strip_manufacturer_suffix(strip_spec_tokens(part), raw_manufacturer)
            for part in model_parts
        ]

        conn.execute(
            """
            UPDATE source_products
            SET manufacturer_id = ?,
                normalized_model_name = ?,
                normalized_core_components = ?
            WHERE id = ?
            """,
            (
                manufacturer_id,
                normalized_parts[0],
                " | ".join(parsed_components) or None,
                source_product_id,
            ),
        )

        # Upsert one canonical model per bundle part
        model_ids: list[int] = []
        for part in normalized_parts:
            model_id = upsert_name_entity(conn, "models", "canonical_model_name", part)
            model_ids.append(model_id)
            conn.execute(
                """
                INSERT INTO source_product_models (source_product_id, model_id, match_type)
                VALUES (?, ?, ?)
                ON CONFLICT(source_product_id, model_id) DO NOTHING
                """,
                (source_product_id, model_id, match_type),
            )

        # Challenge #3: resolve and link components to source row and canonical models
        for raw_comp in parsed_components:
            component_id = _get_or_create_component(conn, raw_comp)
            conn.execute(
                """
                INSERT INTO source_product_components (source_product_id, component_id)
                VALUES (?, ?)
                ON CONFLICT(source_product_id, component_id) DO NOTHING
                """,
                (source_product_id, component_id),
            )
            for model_id in model_ids:
                conn.execute(
                    """
                    INSERT INTO model_components (model_id, component_id)
                    VALUES (?, ?)
                    ON CONFLICT(model_id, component_id) DO NOTHING
                    """,
                    (model_id, component_id),
                )

    conn.commit()
