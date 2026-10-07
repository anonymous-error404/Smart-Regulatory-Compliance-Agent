CREATE DATABASE IF NOT EXISTS AURIS_DB
    COMMENT = 'Auris — Smart Regulatory Compliance Agent (Hackathon 2026)';

USE DATABASE AURIS_DB;

CREATE SCHEMA IF NOT EXISTS AURIS_SCHEMA
    COMMENT = 'Primary schema for Auris tables, stages, and services';

USE SCHEMA AURIS_SCHEMA;

CREATE WAREHOUSE IF NOT EXISTS AURIS_DEV_WH
    WAREHOUSE_SIZE    = 'X-SMALL'
    AUTO_SUSPEND      = 60          -- suspend after 60 seconds of inactivity
    AUTO_RESUME       = TRUE        -- resume automatically on first query
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Auris development & data-loading warehouse';

CREATE WAREHOUSE IF NOT EXISTS AURIS_APP_WH
    WAREHOUSE_SIZE    = 'X-SMALL'
    AUTO_SUSPEND      = 60          -- suspend after 60 seconds of inactivity
    AUTO_RESUME       = TRUE        -- resume automatically on first query
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Auris Streamlit application warehouse';
