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
# Universal Role & Clearance Rank Configuration
# ─────────────────────────────────────────────
# Clearance levels: 1 (Basic / Operational) -> 4 (Executive / Audit)
# Any role/designation maps to a clearance rank, allowed document categories,
# PII visibility, and regional scopes.
USER_ROLES = {
    "Level 1 (Operational)": {
        "level": 1,
        "label": "Level 1 — Operational / Analyst",
        "allowed_doc_categories": ["public_policy", "aml_guidelines"],
        "can_see_pii": False,
        "can_see_watchlist": False,
        "can_see_board_reports": False,
        "max_amount_visible": 50_00_000,
        "visible_regions": ["West"],
    },
    "Level 2 (Senior / Specialist)": {
        "level": 2,
        "label": "Level 2 — Senior Specialist",
        "allowed_doc_categories": ["public_policy", "aml_guidelines", "internal_policy", "risk_reports"],
        "can_see_pii": False,
        "can_see_watchlist": True,
        "can_see_board_reports": False,
        "max_amount_visible": 500_00_00_000,
        "visible_regions": ["West", "South", "North"],
    },
    "Level 3 (Executive / Head)": {
        "level": 3,
        "label": "Level 3 — Executive / Compliance Head",
        "allowed_doc_categories": ["public_policy", "aml_guidelines", "internal_policy", "risk_reports", "board_reports", "kyc_pii"],
        "can_see_pii": True,
        "can_see_watchlist": True,
        "can_see_board_reports": True,
        "max_amount_visible": float("inf"),
        "visible_regions": ["West", "South", "North", "East", "Central"],
    },
    # Backwards-compatibility aliases for system roles
    "junior_analyst": {
        "level": 1,
        "label": "Junior Analyst (Level 1)",
        "allowed_doc_categories": ["public_policy", "aml_guidelines"],
        "can_see_pii": False,
        "can_see_watchlist": False,
        "can_see_board_reports": False,
        "max_amount_visible": 50_00_000,
        "visible_regions": ["West"],
    },
    "senior_analyst": {
        "level": 2,
        "label": "Senior Analyst (Level 2)",
        "allowed_doc_categories": ["public_policy", "aml_guidelines", "internal_policy", "risk_reports"],
        "can_see_pii": False,
        "can_see_watchlist": True,
        "can_see_board_reports": False,
        "max_amount_visible": 500_00_00_000,
        "visible_regions": ["West", "South", "North"],
    },
    "compliance_head": {
        "level": 3,
        "label": "Compliance Head (Level 3)",
        "allowed_doc_categories": ["public_policy", "aml_guidelines", "internal_policy", "risk_reports", "board_reports", "kyc_pii"],
        "can_see_pii": True,
        "can_see_watchlist": True,
        "can_see_board_reports": True,
        "max_amount_visible": float("inf"),
        "visible_regions": ["West", "South", "North", "East", "Central"],
    },
}

def get_role_config(role: str) -> dict:
    """Resolve role configuration dict by role string or rank alias."""
    if role in USER_ROLES:
        return USER_ROLES[role]
    # Check lowercase or fallback to level 1
    role_lower = str(role).lower()
    for r_key, r_cfg in USER_ROLES.items():
        if r_key.lower() == role_lower or r_cfg.get("label", "").lower() == role_lower:
            return r_cfg
    # Fallback to level 1 basic operational scope
    return USER_ROLES["Level 1 (Operational)"]

# ─────────────────────────────────────────────
# Synthetic Data Sizes
# ─────────────────────────────────────────────
SYNTHETIC_TRANSACTION_COUNT = 10_000
SYNTHETIC_KYC_COUNT         = 500

