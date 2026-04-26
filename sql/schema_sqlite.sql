-- SQLite-compatible schema for local development

PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS model_components;
DROP TABLE IF EXISTS source_product_components;
DROP TABLE IF EXISTS source_product_models;
DROP TABLE IF EXISTS component_aliases;
DROP TABLE IF EXISTS source_products;
DROP TABLE IF EXISTS models;
DROP TABLE IF EXISTS manufacturers;
DROP TABLE IF EXISTS components;
DROP TABLE IF EXISTS markets;

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_code TEXT NOT NULL UNIQUE,
    market_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_model_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS manufacturers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS model_components (
    model_id INTEGER NOT NULL,
    component_id INTEGER NOT NULL,
    PRIMARY KEY (model_id, component_id),
    FOREIGN KEY (model_id) REFERENCES models(id),
    FOREIGN KEY (component_id) REFERENCES components(id)
);

CREATE TABLE IF NOT EXISTS source_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id INTEGER NOT NULL,
    manufacturer_id INTEGER,
    raw_model_name TEXT NOT NULL,
    raw_core_components TEXT,
    raw_manufacturer_of_record TEXT NOT NULL,
    normalized_model_name TEXT,
    normalized_core_components TEXT,
    FOREIGN KEY (market_id) REFERENCES markets(id),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id)
);

CREATE INDEX IF NOT EXISTS idx_source_products_market ON source_products(market_id);

CREATE TABLE IF NOT EXISTS source_product_models (
    source_product_id INTEGER NOT NULL,
    model_id INTEGER NOT NULL,
    match_type TEXT DEFAULT 'direct',
    PRIMARY KEY (source_product_id, model_id),
    FOREIGN KEY (source_product_id) REFERENCES source_products(id),
    FOREIGN KEY (model_id) REFERENCES models(id)
);

CREATE TABLE IF NOT EXISTS source_product_components (
    source_product_id INTEGER NOT NULL,
    component_id INTEGER NOT NULL,
    PRIMARY KEY (source_product_id, component_id),
    FOREIGN KEY (source_product_id) REFERENCES source_products(id),
    FOREIGN KEY (component_id) REFERENCES components(id)
);

CREATE TABLE IF NOT EXISTS component_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_name TEXT NOT NULL UNIQUE,
    component_id INTEGER NOT NULL,
    language_code TEXT,
    FOREIGN KEY (component_id) REFERENCES components(id)
);

CREATE INDEX IF NOT EXISTS idx_spm_model ON source_product_models(model_id);
CREATE INDEX IF NOT EXISTS idx_spc_component ON source_product_components(component_id);
