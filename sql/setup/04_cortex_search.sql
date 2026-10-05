-- =============================================================================
-- Auris — 04_cortex_search.sql
-- Purpose : Define the REGULATORY_DOCS table and the Cortex Search Service
--           that powers the Auris RAG (Retrieval-Augmented Generation) pipeline.
--
-- Architecture note:
--   This file is the bridge between the document-ingestion layer and the
--   LLM-powered compliance assistant. The flow is:
--
--   [PDF / URL source]
--       └─► src/ingestion/doc_chunker.py  (splits docs into chunks)
--           └─► REGULATORY_DOCS table      (stores chunks + metadata)
--               └─► AURIS_REGULATORY_SEARCH (Cortex Search indexes CONTENT)
--                   └─► Auris Agent RAG queries (semantic retrieval)
--
--   Permission-aware retrieval: each chunk carries a PERMISSION_LEVEL that
--   the application layer enforces against USER_PERMISSIONS.ROLE before
--   surfacing results to the end user.
-- Run after : 01_database_warehouse.sql
-- =============================================================================

USE DATABASE AURIS_DB;
USE SCHEMA AURIS_SCHEMA;


-- =============================================================================
-- SECTION 1: REGULATORY_DOCS
-- Stores chunked text from regulatory documents ingested by the RAG pipeline.
-- Each row represents one logical chunk (paragraph / section) of a document.
--
-- Ingestion strategy:
--   - DOC_CATEGORY groups documents by regulatory domain (AML, BASEL, KYC…).
--   - SECTION_NUMBER enables ordered reassembly of chunks for citation display.
--   - PERMISSION_LEVEL gates retrieval so junior analysts cannot access
--     restricted supervisory circulars (matches USER_PERMISSIONS.ROLE values).
--   - CONTENT is the raw text column indexed by Cortex Search.
-- =============================================================================

CREATE TABLE IF NOT EXISTS REGULATORY_DOCS (
    DOC_ID           VARCHAR(64)    NOT NULL COMMENT 'Unique chunk identifier (UUID assigned at ingestion)',
    DOC_NAME         VARCHAR(512)   NOT NULL COMMENT 'Human-readable document title, e.g. "RBI Master Direction on KYC 2016"',
    DOC_CATEGORY     VARCHAR(64)    NOT NULL COMMENT 'Regulatory domain: AML | BASEL | KYC | FEMA | FINTRAC | SEBI | OTHER',
    SECTION_NUMBER   VARCHAR(32)             COMMENT 'Section / clause number within the source document, e.g. "4.2.1"',
    SECTION_TITLE    VARCHAR(512)            COMMENT 'Title of the section this chunk belongs to',
    CONTENT          VARCHAR(16777216) NOT NULL COMMENT 'Full text of the document chunk — indexed by Cortex Search',
    SOURCE_URL       VARCHAR(2048)           COMMENT 'Canonical URL of the source regulatory document',
    EFFECTIVE_DATE   DATE                    COMMENT 'Date the regulatory provision came into effect',
    PERMISSION_LEVEL VARCHAR(32)    NOT NULL DEFAULT 'junior_analyst'
        COMMENT 'Minimum role required to retrieve this chunk: junior_analyst | senior_analyst | compliance_head',

    CONSTRAINT PK_REGULATORY_DOCS PRIMARY KEY (DOC_ID)
);


-- =============================================================================
-- SECTION 2: CORTEX SEARCH SERVICE — AURIS_REGULATORY_SEARCH
-- Snowflake Cortex Search builds a vector index over the CONTENT column and
-- exposes a semantic-search API that the Auris agent calls at query time.
--
-- Key design choices:
--   ON CONTENT          — the free-text column to embed and index
--   ATTRIBUTES          — metadata columns returned alongside search results
--                         so the application can filter by DOC_CATEGORY and
--                         enforce PERMISSION_LEVEL without a secondary query
--   TARGET_LAG '1 hour' — index refreshes within 1 hour of new chunk inserts,
--                         balancing freshness with warehouse cost
--
-- Usage (Python — via Snowpark or REST):
--   response = session.sql("""
--       SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
--           'AURIS_DB.AURIS_SCHEMA.AURIS_REGULATORY_SEARCH',
--           '{"query": "CTR filing threshold India", "columns": ["CONTENT","DOC_NAME","SECTION_NUMBER"], "limit": 5}'
--       )
--   """).collect()
-- =============================================================================

CREATE OR REPLACE CORTEX SEARCH SERVICE AURIS_REGULATORY_SEARCH
    ON CONTENT
    WITHIN REGULATORY_DOCS
    ATTRIBUTES DOC_CATEGORY, PERMISSION_LEVEL
    WAREHOUSE = AURIS_DEV_WH
    TARGET_LAG = '1 hour'
    COMMENT = 'Semantic search index over Auris regulatory document chunks. Powers the RAG pipeline for the compliance assistant.';
