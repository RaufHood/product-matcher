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
    canonical_model_name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE manufacturers (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE components (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Model <-> Component is many-to-many
CREATE TABLE model_components (
    model_id INTEGER NOT NULL,
    component_id INTEGER NOT NULL,
    PRIMARY KEY (model_id, component_id),
    FOREIGN KEY (model_id) REFERENCES models(id),
    FOREIGN KEY (component_id) REFERENCES components(id)
);

-- Optional: canonical model <-> canonical manufacturer (many-to-many)
CREATE TABLE model_manufacturers (
    model_id INTEGER NOT NULL,
    manufacturer_id INTEGER NOT NULL,
    role VARCHAR(50) DEFAULT 'manufacturer_of_record',
    PRIMARY KEY (model_id, manufacturer_id, role),
    FOREIGN KEY (model_id) REFERENCES models(id),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id)
);

-- =========================================================
-- 2) Raw source records (single table across all markets)
-- =========================================================

CREATE TABLE source_products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market_id INTEGER NOT NULL,
    source_row_key VARCHAR(255), -- optional source-native id if available

    -- Raw values for full traceability:
    raw_model_name TEXT NOT NULL,
    raw_core_components TEXT, -- Spain may be NULL
    raw_manufacturer_of_record TEXT NOT NULL,

    -- Optional normalized text snapshots produced by cleaning pipeline:
    normalized_model_name TEXT,
    normalized_core_components TEXT,
    normalized_manufacturer_name TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (market_id) REFERENCES markets(id)
);

-- Prevent duplicate ingestion per market+row key when key exists
CREATE UNIQUE INDEX uq_source_products_market_rowkey
    ON source_products (market_id, source_row_key);

-- =========================================================
-- 3) Link raw rows to canonical entities
-- =========================================================

-- A raw row may map to one or more canonical models (bundles / combos)
CREATE TABLE source_product_models (
    source_product_id BIGINT NOT NULL,
    model_id INTEGER NOT NULL,
    match_type VARCHAR(30) DEFAULT 'direct',  -- direct | bundle_part | fuzzy
    confidence_score DECIMAL(5,4),            -- e.g., 0.0000 - 1.0000
    is_primary BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (source_product_id, model_id),
    FOREIGN KEY (source_product_id) REFERENCES source_products(id),
    FOREIGN KEY (model_id) REFERENCES models(id)
);

-- Source row <-> components found/mapped (many-to-many)
CREATE TABLE source_product_components (
    source_product_id BIGINT NOT NULL,
    component_id INTEGER NOT NULL,
    mapping_type VARCHAR(30) DEFAULT 'parsed', -- parsed | translated | inferred
    PRIMARY KEY (source_product_id, component_id),
    FOREIGN KEY (source_product_id) REFERENCES source_products(id),
    FOREIGN KEY (component_id) REFERENCES components(id)
);

-- Source row <-> manufacturer mapping
-- Keep this many-to-many to support ambiguous or corrected mappings.
CREATE TABLE source_product_manufacturers (
    source_product_id BIGINT NOT NULL,
    manufacturer_id INTEGER NOT NULL,
    mapping_type VARCHAR(30) DEFAULT 'direct',
    is_primary BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (source_product_id, manufacturer_id),
    FOREIGN KEY (source_product_id) REFERENCES source_products(id),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id)
);

-- =========================================================
-- 4) Optional alias dictionaries for matching pipeline
-- =========================================================

CREATE TABLE component_aliases (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alias_name VARCHAR(255) NOT NULL UNIQUE,
    component_id INTEGER NOT NULL,
    language_code VARCHAR(10), -- de, fr, es, etc.
    FOREIGN KEY (component_id) REFERENCES components(id)
);

CREATE TABLE manufacturer_aliases (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alias_name VARCHAR(255) NOT NULL UNIQUE,
    manufacturer_id INTEGER NOT NULL,
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id)
);

-- =========================================================
-- 5) Useful indexes for matching/query performance
-- =========================================================

CREATE INDEX idx_source_products_market ON source_products(market_id);
CREATE INDEX idx_spm_model ON source_product_models(model_id);
CREATE INDEX idx_spc_component ON source_product_components(component_id);
CREATE INDEX idx_spman_manufacturer ON source_product_manufacturers(manufacturer_id);
