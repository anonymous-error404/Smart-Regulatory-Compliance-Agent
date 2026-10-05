"""
Auris — Central Configuration
Change CORTEX_MODEL and ENV here to switch between dev/demo modes.
"""

import os

# ─────────────────────────────────────────────
# Environment: "local" | "snowflake"
# ─────────────────────────────────────────────
ENV = os.getenv("AURIS_ENV", os.getenv("REGIQ_ENV", "local"))

# ─────────────────────────────────────────────
# Snowflake Connection
# ─────────────────────────────────────────────
SNOWFLAKE_ACCOUNT   = os.getenv("SNOWFLAKE_ACCOUNT", "")
SNOWFLAKE_USER      = os.getenv("SNOWFLAKE_USER", "")
SNOWFLAKE_PASSWORD  = os.getenv("SNOWFLAKE_PASSWORD", "")
SNOWFLAKE_DATABASE  = os.getenv("SNOWFLAKE_DATABASE", "AURIS_DB")
SNOWFLAKE_SCHEMA    = os.getenv("SNOWFLAKE_SCHEMA", "AURIS_SCHEMA")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "AURIS_DEV_WH")
SNOWFLAKE_ROLE      = os.getenv("SNOWFLAKE_ROLE", "SYSADMIN")

# ─────────────────────────────────────────────
# Cortex LLM Model
# Week 1-3 dev  → snowflake-arctic-instruct
# Integration   → mistral-large2
# Final demo    → mistral-large2 / llama3.1-70b
# ─────────────────────────────────────────────
CORTEX_MODEL = os.getenv("CORTEX_MODEL", "snowflake-arctic-instruct")

# ─────────────────────────────────────────────
# Cortex Search Service Names
# ─────────────────────────────────────────────
CORTEX_SEARCH_SERVICE = "AURIS_REGULATORY_SEARCH"

# ─────────────────────────────────────────────
# Fraud Alert Thresholds
# ─────────────────────────────────────────────
FRAUD_ALERT_THRESHOLD   = int(os.getenv("FRAUD_ALERT_THRESHOLD", "70"))
HIGH_RISK_THRESHOLD     = int(os.getenv("HIGH_RISK_THRESHOLD", "80"))
LARGE_TXN_THRESHOLD_INR = int(os.getenv("LARGE_TXN_THRESHOLD_INR", "1_000_000"))  # ₹10L

# ─────────────────────────────────────────────
# Slack Integration
# ─────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# ─────────────────────────────────────────────
# User Permission Roles (for demo — hardcoded)
# ─────────────────────────────────────────────
USER_ROLES = {
    "junior_analyst":    {"level": 1, "allowed_doc_categories": ["public_policy", "aml_guidelines"]},
    "senior_analyst":    {"level": 2, "allowed_doc_categories": ["public_policy", "aml_guidelines", "internal_policy", "risk_reports"]},
    "compliance_head":   {"level": 3, "allowed_doc_categories": ["public_policy", "aml_guidelines", "internal_policy", "risk_reports", "board_reports", "kyc_pii"]},
}

# ─────────────────────────────────────────────
# Synthetic Data Sizes
# ─────────────────────────────────────────────
SYNTHETIC_TRANSACTION_COUNT = 10_000
SYNTHETIC_KYC_COUNT         = 500
