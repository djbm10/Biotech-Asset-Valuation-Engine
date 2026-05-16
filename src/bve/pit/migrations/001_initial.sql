-- Migration 001: Initial PIT fact store schema
-- Run at: 2026-05-15

CREATE TABLE IF NOT EXISTS pit_facts (
    fact_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id        TEXT    NOT NULL,
    fact_type        TEXT    NOT NULL,
    value            TEXT,
    valid_from       TEXT    NOT NULL,   -- ISO date when fact became true in the world
    valid_to         TEXT,               -- ISO date when fact ceased to be true; NULL = still valid
    known_at         TEXT    NOT NULL,   -- ISO datetime when we learned about it
    ingested_at      TEXT    NOT NULL,   -- ISO datetime when it entered the store
    source           TEXT    NOT NULL,
    source_document_id TEXT  NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pit_entity_type ON pit_facts (entity_id, fact_type);
CREATE INDEX IF NOT EXISTS idx_pit_known_at    ON pit_facts (known_at);
CREATE INDEX IF NOT EXISTS idx_pit_valid_from  ON pit_facts (valid_from);
CREATE INDEX IF NOT EXISTS idx_pit_valid_to    ON pit_facts (valid_to);
