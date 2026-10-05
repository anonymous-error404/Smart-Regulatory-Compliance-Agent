-- =============================================================================
-- Auris — 03_alerts.sql
-- Purpose : Snowflake Alerts for real-time fraud detection and daily compliance
--           summaries, plus stub stored procedures that the Snowpark layer will
--           replace with full implementations.
-- Run after : 01_database_warehouse.sql, 02_tables.sql
-- =============================================================================

USE DATABASE AURIS_DB;
USE SCHEMA AURIS_SCHEMA;


-- =============================================================================
-- SECTION 1: STUB STORED PROCEDURES
-- These stubs are placeholders so that the CREATE ALERT statements below can
-- reference valid procedure objects. They will be replaced by the full Snowpark
-- Python implementations in src/snowpark/procs/.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Stub: SEND_FRAUD_ALERT_PROC
-- Called by AURIS_FRAUD_ALERT every minute when high-risk unreviewed
-- transactions are detected. The real implementation will:
--   1. Pull the flagged TXN_IDs from TRANSACTIONS.
--   2. Format a notification payload.
--   3. Dispatch via SYSTEM$SEND_SNOWFLAKE_NOTIFICATION (email / Slack webhook).
--   4. Write a record to AUDIT_TRAIL for full traceability.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE AURIS_SCHEMA.SEND_FRAUD_ALERT_PROC()
    RETURNS VARCHAR
    LANGUAGE SQL
    COMMENT = 'Stub: notify compliance team of high-risk transactions. Replace with Snowpark implementation.'
AS
$$
DECLARE
    flagged_count INTEGER;
    audit_msg     VARCHAR;
BEGIN
    -- Count flagged, unreviewed, high-risk transactions
    SELECT COUNT(*) INTO :flagged_count
    FROM AURIS_DB.AURIS_SCHEMA.TRANSACTIONS
    WHERE RISK_SCORE >= 70
      AND AML_FLAG   = TRUE
      AND REVIEWED   = FALSE;

    -- Build a short summary message
    audit_msg := 'FRAUD_ALERT_PROC (stub) — flagged_count=' || :flagged_count || ' at ' || CURRENT_TIMESTAMP::VARCHAR;

    -- Log execution to AUDIT_TRAIL so the event is never silently swallowed
    INSERT INTO AURIS_DB.AURIS_SCHEMA.AUDIT_TRAIL
        (USER_ID, QUERY_TEXT, AGENT_ROUTED_TO, RESPONSE_SUMMARY, QUERY_TIMESTAMP)
    VALUES
        ('SYSTEM', 'AURIS_FRAUD_ALERT fired', 'SEND_FRAUD_ALERT_PROC', :audit_msg, CURRENT_TIMESTAMP);

    RETURN :audit_msg;
END;
$$;


-- ---------------------------------------------------------------------------
-- Stub: SEND_DAILY_SUMMARY_PROC
-- Called by AURIS_DAILY_SUMMARY_ALERT at 08:00 each morning. The real
-- implementation will:
--   1. Aggregate yesterday's flagged transactions by type and channel.
--   2. Generate an AML_SUMMARY entry in REGULATORY_REPORTS.
--   3. Dispatch the summary report via SYSTEM$SEND_SNOWFLAKE_NOTIFICATION.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE AURIS_SCHEMA.SEND_DAILY_SUMMARY_PROC()
    RETURNS VARCHAR
    LANGUAGE SQL
    COMMENT = 'Stub: send daily AML summary report. Replace with Snowpark implementation.'
AS
$$
DECLARE
    yesterday_start TIMESTAMP_NTZ;
    yesterday_end   TIMESTAMP_NTZ;
    txn_count       INTEGER;
    high_risk_count INTEGER;
    flagged_amount  NUMBER(18, 2);
    report_id       VARCHAR;
    summary_msg     VARCHAR;
BEGIN
    -- Define the previous calendar day window (UTC)
    yesterday_start := DATEADD('day', -1, DATE_TRUNC('day', CURRENT_TIMESTAMP));
    yesterday_end   := DATE_TRUNC('day', CURRENT_TIMESTAMP);

    -- Aggregate yesterday's transactions
    SELECT
        COUNT(*),
        SUM(CASE WHEN RISK_SCORE >= 70 THEN 1 ELSE 0 END),
        SUM(CASE WHEN AML_FLAG = TRUE THEN AMOUNT_INR ELSE 0 END)
    INTO :txn_count, :high_risk_count, :flagged_amount
    FROM AURIS_DB.AURIS_SCHEMA.TRANSACTIONS
    WHERE TXN_DATE >= :yesterday_start
      AND TXN_DATE  < :yesterday_end;

    -- Write a DRAFT report record
    report_id := UUID_STRING();
    INSERT INTO AURIS_DB.AURIS_SCHEMA.REGULATORY_REPORTS
        (REPORT_ID, REPORT_TYPE, GENERATED_BY, PERIOD_START, PERIOD_END,
         TXN_COUNT, HIGH_RISK_COUNT, TOTAL_FLAGGED_AMOUNT_INR, REPORT_STATUS)
    VALUES
        (:report_id, 'AML_SUMMARY', 'SYSTEM',
         :yesterday_start::DATE, :yesterday_end::DATE,
         :txn_count, :high_risk_count, :flagged_amount, 'DRAFT');

    summary_msg := 'DAILY_SUMMARY_PROC (stub) — report_id=' || :report_id
               || ' txns=' || :txn_count
               || ' high_risk=' || :high_risk_count
               || ' flagged_INR=' || :flagged_amount;

    -- Log to AUDIT_TRAIL
    INSERT INTO AURIS_DB.AURIS_SCHEMA.AUDIT_TRAIL
        (USER_ID, QUERY_TEXT, AGENT_ROUTED_TO, RESPONSE_SUMMARY, QUERY_TIMESTAMP)
    VALUES
        ('SYSTEM', 'AURIS_DAILY_SUMMARY_ALERT fired', 'SEND_DAILY_SUMMARY_PROC', :summary_msg, CURRENT_TIMESTAMP);

    RETURN :summary_msg;
END;
$$;


-- =============================================================================
-- SECTION 2: REAL-TIME FRAUD ALERT (AURIS_FRAUD_ALERT)
-- Fires every 1 minute. The IF condition queries TRANSACTIONS for any rows
-- that have a high RISK_SCORE, an AML flag, and have not yet been reviewed.
-- If at least one such row exists, the THEN clause calls the fraud procedure.
-- =============================================================================

CREATE OR REPLACE ALERT AURIS_FRAUD_ALERT
    WAREHOUSE = AURIS_DEV_WH
    SCHEDULE  = '1 MINUTE'

    -- Condition: return rows when there are high-risk, unreviewed AML transactions
    IF (
        EXISTS (
            SELECT 1
            FROM AURIS_DB.AURIS_SCHEMA.TRANSACTIONS
            WHERE RISK_SCORE >= 70
              AND AML_FLAG   = TRUE
              AND REVIEWED   = FALSE
        )
    )

    -- Action: invoke the fraud notification procedure
    THEN
        CALL AURIS_DB.AURIS_SCHEMA.SEND_FRAUD_ALERT_PROC();


-- =============================================================================
-- SECTION 3: DAILY COMPLIANCE SUMMARY ALERT (AURIS_DAILY_SUMMARY_ALERT)
-- Fires at 08:00 UTC every day (CRON syntax). Produces a high-level AML
-- summary for the previous calendar day and dispatches it to the compliance
-- team. The IF condition always evaluates to TRUE so the THEN action runs
-- unconditionally on every scheduled trigger.
-- =============================================================================

CREATE OR REPLACE ALERT AURIS_DAILY_SUMMARY_ALERT
    WAREHOUSE = AURIS_DEV_WH
    SCHEDULE  = 'USING CRON 0 8 * * * UTC'

    -- Condition: always fire (we want an unconditional daily trigger)
    IF (
        EXISTS (
            SELECT 1
        )
    )

    -- Action: invoke the daily summary procedure
    THEN
        CALL AURIS_DB.AURIS_SCHEMA.SEND_DAILY_SUMMARY_PROC();


-- =============================================================================
-- NOTE: Alerts are created in a SUSPENDED state by default.
-- Activate them with:
--   ALTER ALERT AURIS_FRAUD_ALERT         RESUME;
--   ALTER ALERT AURIS_DAILY_SUMMARY_ALERT RESUME;
-- =============================================================================
