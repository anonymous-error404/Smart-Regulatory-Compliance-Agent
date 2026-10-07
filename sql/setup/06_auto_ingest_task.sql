-- =============================================================================
-- Auris — 06_auto_ingest_task.sql
-- Purpose : Automated Event-Driven PDF Ingestion Pipeline
--           Whenever a new regulatory PDF is uploaded to @AURIS_PDF_STAGE,
--           the Stream captures the file event, the Snowflake Task fires,
--           and the Snowpark Procedure executes your existing IngestionPipeline
--           (PDFParser + DocChunker) to populate REGULATORY_DOCS.
-- =============================================================================

USE DATABASE AURIS_DB;
USE SCHEMA AURIS_SCHEMA;

-- 1. Ensure directory metadata tracking is active on the PDF Stage
ALTER STAGE AURIS_PDF_STAGE SET DIRECTORY = (ENABLE = TRUE, AUTO_REFRESH = TRUE);

-- 2. Create Change Data Capture (CDC) Stream on the Stage
CREATE STREAM IF NOT EXISTS AURIS_PDF_STAGE_STREAM 
    ON STAGE AURIS_PDF_STAGE
    COMMENT = 'Captures newly uploaded regulatory circular PDFs';

-- 3. Stored Procedure executing the IngestionPipeline
-- Imports the existing ingestion modules from @AURIS_STREAMLIT_STAGE
CREATE OR REPLACE PROCEDURE INGEST_NEW_STAGE_PDFS_PROC()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python', 'pypdf', 'pandas')
IMPORTS = ('@AURIS_DB.AURIS_SCHEMA.AURIS_APP_STAGE/src.zip')
HANDLER = 'src.ingestion.ingestion_pipeline.run_auto_ingest_handler';

-- 4. Automated Task: checks every 1 minute
-- Consumes zero compute credits if no new PDFs are in the stream
CREATE OR REPLACE TASK AURIS_AUTO_INGEST_PDF_TASK
    WAREHOUSE = AURIS_DEV_WH
    SCHEDULE = '1 MINUTE'
    WHEN SYSTEM$STREAM_HAS_DATA('AURIS_PDF_STAGE_STREAM')
AS
    CALL INGEST_NEW_STAGE_PDFS_PROC();

-- 5. Enable the Task
ALTER TASK AURIS_AUTO_INGEST_PDF_TASK RESUME;
