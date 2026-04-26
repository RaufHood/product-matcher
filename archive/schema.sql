-- ElectroPulse unified catalog relational schema
-- Purpose: preserve raw source traceability while mapping to canonical models.

-- =========================================================
-- 1) Canonical entities
-- =========================================================

CREATE TABLE markets (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market_code VARCHAR(10) NOT NULL UNIQUE,   -- EU, US, ES, CH
    market_name VARCHAR(100) NOT NULL
);

CREATE TABLE models (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_model_name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE manufacturers (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE components (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name VARCHAR(255) NOT NULL UNIQUE
);

-- Model <-> Component is many-to-many
CREATE TABLE model_components (
    model_id    INTEGER NOT NULL REFERENCES models(id),
    component_id INTEGER NOT NULL REFERENCES components(id),
    PRIMARY KEY (model_id, component_id)
);

-- =========================================================
-- 2) Raw source records (single table across all markets)
-- =========================================================

CREATE TABLE source_products (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market_id   INTEGER NOT NULL REFERENCES markets(id),
    manufacturer_id INTEGER REFERENCES manufacturers(id),   -- resolved during ingestion

    -- Raw values for full traceability:
    raw_model_name          TEXT NOT NULL,
    raw_core_components     TEXT,           -- NULL for Spain
    raw_manufacturer_of_record TEXT NOT NULL,

    -- Normalized text snapshots produced by the cleaning pipeline:
    normalized_model_name       TEXT,
    normalized_core_components  TEXT
);

CREATE INDEX idx_source_products_market ON source_products(market_id);

-- =========================================================
-- 3) Link raw rows to canonical entities
-- =========================================================

-- A raw row maps to one or more canonical models (bundles / combos)
CREATE TABLE source_product_models (
    source_product_id BIGINT  NOT NULL REFERENCES source_products(id),
    model_id          INTEGER NOT NULL REFERENCES models(id),
    match_type        VARCHAR(30) DEFAULT 'direct',  -- direct | bundle_part | fuzzy
    PRIMARY KEY (source_product_id, model_id)
);

-- Source row <-> components (many-to-many)
CREATE TABLE source_product_components (
    source_product_id BIGINT  NOT NULL REFERENCES source_products(id),
    component_id      INTEGER NOT NULL REFERENCES components(id),
    PRIMARY KEY (source_product_id, component_id)
);

-- =========================================================
-- 4) Alias dictionary for component translation (CH multilingual)
-- =========================================================

CREATE TABLE component_aliases (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alias_name   VARCHAR(255) NOT NULL UNIQUE,
    component_id INTEGER NOT NULL REFERENCES components(id),
    language_code VARCHAR(10)     -- de, fr, es, etc.
);

-- =========================================================
-- 5) Indexes
-- =========================================================

CREATE INDEX idx_spm_model       ON source_product_models(model_id);
CREATE INDEX idx_spc_component   ON source_product_components(component_id);
