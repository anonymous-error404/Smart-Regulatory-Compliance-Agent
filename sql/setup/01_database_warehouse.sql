-- =============================================================================
-- Auris — 01_database_warehouse.sql
-- Purpose : Bootstrap the Snowflake environment for the Auris project.
--           Run once as ACCOUNTADMIN (or a role with CREATE DATABASE privilege).
-- =============================================================================


-- =============================================================================
-- SECTION 1: DATABASE
-- Creates the primary Auris database that houses all schemas, tables, stages,
-- and Cortex Search services for the project.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS AURIS_DB
    COMMENT = 'Auris — Smart Regulatory Compliance Agent (Hackathon 2026)';

USE DATABASE AURIS_DB;


-- =============================================================================
-- SECTION 2: SCHEMA
-- A single schema keeps all Auris objects in one logical namespace.
-- Data masking policies and row-access policies will be applied here.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS AURIS_SCHEMA
    COMMENT = 'Primary schema for Auris tables, stages, and services';

USE SCHEMA AURIS_SCHEMA;


-- =============================================================================
-- SECTION 3: DEVELOPMENT WAREHOUSE (AURIS_DEV_WH)
-- Used during data loading, Snowpark UDF development, and ad-hoc SQL queries.
-- X-SMALL keeps costs low; AUTO_SUSPEND / AUTO_RESUME prevent idle spend.
-- =============================================================================

CREATE WAREHOUSE IF NOT EXISTS AURIS_DEV_WH
    WAREHOUSE_SIZE    = 'X-SMALL'
    AUTO_SUSPEND      = 60          -- suspend after 60 seconds of inactivity
    AUTO_RESUME       = TRUE        -- resume automatically on first query
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Auris development & data-loading warehouse';


-- =============================================================================
-- SECTION 4: APPLICATION WAREHOUSE (AURIS_APP_WH)
-- Dedicated warehouse for the Streamlit app and real-time query traffic.
-- Kept separate so app queries never compete with ETL / dev workloads.
-- =============================================================================

CREATE WAREHOUSE IF NOT EXISTS AURIS_APP_WH
    WAREHOUSE_SIZE    = 'X-SMALL'
    AUTO_SUSPEND      = 60          -- suspend after 60 seconds of inactivity
    AUTO_RESUME       = TRUE        -- resume automatically on first query
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Auris Streamlit application warehouse';
