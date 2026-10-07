-- =============================================================================
-- Auris — 05_deploy_streamlit.sql
-- Purpose : Create Snowflake internal stage and deploy Streamlit in Snowflake (SiS)
--           so Auris runs 100% cloud-native inside the Snowflake perimeter.
-- =============================================================================

USE DATABASE AURIS_DB;
USE SCHEMA AURIS_SCHEMA;

-- 1. Create the Streamlit in Snowflake (SiS) application
-- Points directly to the staged application codebase in @AURIS_APP_STAGE
CREATE OR REPLACE STREAMLIT AURIS_COMPLIANCE_APP
    ROOT_LOCATION = '@AURIS_DB.AURIS_SCHEMA.AURIS_APP_STAGE'
    MAIN_FILE = 'app.py'
    QUERY_WAREHOUSE = AURIS_APP_WH
    COMMENT = 'Auris AI — Regulatory Compliance & Risk Copilot (SiS)';
