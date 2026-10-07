USE DATABASE AURIS_DB;
USE SCHEMA AURIS_SCHEMA;

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

CREATE OR REPLACE CORTEX SEARCH SERVICE AURIS_REGULATORY_SEARCH
    ON CONTENT
    ATTRIBUTES DOC_CATEGORY, PERMISSION_LEVEL
    WAREHOUSE = AURIS_DEV_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT
            DOC_ID,
            DOC_NAME,
            DOC_CATEGORY,
            SECTION_NUMBER,
            SECTION_TITLE,
            CONTENT,
            SOURCE_URL,
            EFFECTIVE_DATE,
            PERMISSION_LEVEL
        FROM REGULATORY_DOCS
    );
