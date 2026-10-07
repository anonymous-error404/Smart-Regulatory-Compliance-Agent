"""
scripts/load_data.py
====================
Automated synthetic data ingestion pipeline for Auris on Snowflake.

Reads the generated CSV files from `data/synthetic/`, transforms and validates
columns against the Snowflake table schemas, stages and loads them via
`snowflake.connector.pandas_tools.write_pandas`.

Prerequisites
-------------
1. Run `sql/setup/01_database_warehouse.sql` in Snowflake Worksheets
2. Run `sql/setup/02_tables.sql` in Snowflake Worksheets
3. Fill in your Snowflake credentials in `.env`

Usage
-----
    python scripts/load_data.py
    python scripts/load_data.py --dry-run
    python scripts/load_data.py --tables TRANSACTIONS KYC_PROFILES
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Load .env explicitly
load_dotenv(_ROOT / ".env")


def get_snowflake_connection():
    """Build and return a live Snowflake connection from environment variables."""
    import snowflake.connector

    account = os.getenv("SNOWFLAKE_ACCOUNT", "").strip()
    # Normalize account identifier (strip protocol and domain suffix if provided)
    if "://" in account:
        account = account.split("://")[-1]
    if account.endswith(".snowflakecomputing.com"):
        account = account.replace(".snowflakecomputing.com", "")

    user = os.getenv("SNOWFLAKE_USER", "").strip()
    password = os.getenv("SNOWFLAKE_PASSWORD", "").strip()
    database = os.getenv("SNOWFLAKE_DATABASE", "AURIS_DB").strip()
    schema = os.getenv("SNOWFLAKE_SCHEMA", "AURIS_SCHEMA").strip()
    warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "AURIS_DEV_WH").strip()
    role = os.getenv("SNOWFLAKE_ROLE", "SYSADMIN").strip()

    if not account or not user or not password:
        raise ValueError(
            "Missing Snowflake credentials in .env!\n"
            "Please ensure SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD are set."
        )

    print(f"Connecting to Snowflake account: {account} (user: {user}, warehouse: {warehouse})...")
    conn = snowflake.connector.connect(
        account=account,
        user=user,
        password=password,
        database=database,
        schema=schema,
        warehouse=warehouse,
        role=role,
    )
    return conn, database, schema


# ---------------------------------------------------------------------------
# Dataset Transformers (CSV -> Table Schema Mapping)
# ---------------------------------------------------------------------------

def transform_transactions(csv_path: Path) -> pd.DataFrame:
    """Transform synthetic transactions into TRANSACTIONS table schema."""
    df_raw = pd.read_csv(csv_path)
    df = pd.DataFrame()
    df["TXN_ID"] = df_raw["TXN_ID"].astype(str)
    df["CUSTOMER_ID"] = df_raw["CUSTOMER_ID"].astype(str)
    df["TXN_DATE"] = pd.to_datetime(df_raw["TXN_DATE"])
    df["AMOUNT_INR"] = df_raw["AMOUNT"].astype(float)
    df["TXN_TYPE"] = df_raw["TXN_TYPE"].astype(str)

    # Channel mapping
    channel_map = {
        "UPI": "MOBILE",
        "IMPS": "ONLINE",
        "NEFT": "ONLINE",
        "RTGS": "ONLINE",
        "CASH": "BRANCH",
    }
    df["CHANNEL"] = df["TXN_TYPE"].map(channel_map).fillna("ONLINE").astype(str)
    df["COUNTERPARTY_ACCOUNT"] = df_raw["COUNTERPARTY_ACCOUNT"].astype(str)
    df["COUNTERPARTY_BANK"] = df_raw["COUNTERPARTY_NAME"].fillna("HDFC Bank").astype(str).str[:128]
    df["COUNTERPARTY_COUNTRY"] = df_raw["COUNTERPARTY_COUNTRY"].fillna("India").astype(str).str[:64]
    df["DESCRIPTION"] = df_raw["DESCRIPTION"].fillna("Payment").astype(str).str[:512]

    # Flags
    df["IS_INTERNATIONAL"] = df["COUNTERPARTY_COUNTRY"].str.strip().str.lower() != "india"
    df["RISK_SCORE"] = df_raw["RISK_SCORE"].astype(float)
    df["AML_FLAG"] = df_raw["AML_FLAG"].astype(bool)
    df["FRAUD_FLAG"] = df["RISK_SCORE"] >= 80.0
    df["REVIEWED"] = False
    df["CREATED_AT"] = df["TXN_DATE"]

    return df


def transform_kyc_profiles(csv_path: Path) -> pd.DataFrame:
    """Transform synthetic KYC profiles into KYC_PROFILES table schema."""
    df_raw = pd.read_csv(csv_path)
    df = pd.DataFrame()
    df["CUSTOMER_ID"] = df_raw["CUSTOMER_ID"].astype(str)
    df["FULL_NAME"] = df_raw["FULL_NAME"].astype(str).str[:256]
    df["PAN_NUMBER"] = df_raw["PAN_NUMBER"].astype(str).str[:16]
    df["AADHAR_HASH"] = df_raw["AADHAAR_HASH"].astype(str).str[:128]
    df["DOB"] = pd.to_datetime(df_raw["DATE_OF_BIRTH"]).dt.date

    # Normalize account type and status
    account_map = {"NRI_NRE": "NRI", "NRI_NRO": "NRI"}
    df["ACCOUNT_TYPE"] = df_raw["ACCOUNT_TYPE"].map(account_map).fillna(df_raw["ACCOUNT_TYPE"]).astype(str).str[:16]

    kyc_map = {"COMPLETE": "VERIFIED", "PENDING_DOCS": "PENDING"}
    df["KYC_STATUS"] = df_raw["KYC_STATUS"].map(kyc_map).fillna(df_raw["KYC_STATUS"]).astype(str).str[:16]

    df["RISK_CATEGORY"] = df_raw["RISK_TIER"].astype(str).str[:8]
    df["ANNUAL_INCOME_INR"] = 1500000.0  # Normalized average baseline
    df["POLITICALLY_EXPOSED"] = df_raw["IS_PEP"].astype(bool)
    df["NATIONALITY"] = "India"
    df["STATE"] = df_raw["STATE"].fillna("Maharashtra").astype(str).str[:64]
    df["CITY"] = df_raw["CITY"].fillna("Mumbai").astype(str).str[:128]
    df["ONBOARDED_AT"] = pd.to_datetime(df_raw["CUSTOMER_SINCE"])
    df["LAST_UPDATED"] = datetime.utcnow()

    return df


def transform_aml_watchlist(csv_path: Path) -> pd.DataFrame:
    """Transform synthetic AML watchlist into AML_WATCHLIST table schema."""
    df_raw = pd.read_csv(csv_path)
    df = pd.DataFrame()
    df["ENTITY_ID"] = df_raw["ENTITY_ID"].astype(str)
    df["ENTITY_NAME"] = df_raw["ENTITY_NAME"].astype(str).str[:512]
    df["ENTITY_TYPE"] = df_raw["ENTITY_TYPE"].astype(str).str[:16]

    source_map = {
        "RBI_CAUTION_LIST": "RBI",
        "EU_FINANCIAL_SANCTIONS": "EU",
    }
    df["SANCTION_LIST"] = df_raw["LISTING_SOURCE"].map(source_map).fillna(df_raw["LISTING_SOURCE"]).astype(str).str[:16]
    df["COUNTRY"] = df_raw["NATIONALITY"].fillna("Unknown").astype(str).str[:64]
    df["ALIAS_NAMES"] = df_raw["ALIAS_NAMES"].astype(str)
    df["ADDED_DATE"] = pd.to_datetime(df_raw["LISTED_DATE"]).dt.date
    df["STATUS"] = df_raw["IS_ACTIVE"].apply(lambda x: "ACTIVE" if x else "REMOVED")
    df["SOURCE_URL"] = df_raw["ENTITY_ID"].apply(lambda x: f"https://sanctions.example.org/watchlist/{x}")

    return df


def transform_user_permissions(csv_path: Path) -> pd.DataFrame:
    """Transform synthetic user permissions into USER_PERMISSIONS table schema."""
    df_raw = pd.read_csv(csv_path)
    df = pd.DataFrame()
    df["USER_ID"] = df_raw["USER_ID"].astype(str)
    df["USERNAME"] = df_raw["FULL_NAME"].astype(str).str[:128]
    df["ROLE"] = df_raw["ROLE"].astype(str).str[:32]
    df["ALLOWED_DOC_CATEGORIES"] = df_raw["ALLOWED_DOC_CATEGORIES"].astype(str)

    scope_map = {
        "compliance_head": "all",
        "senior_analyst": "national",
        "junior_analyst": "own_region",
    }
    df["DATA_SCOPE"] = df["ROLE"].map(scope_map).fillna("own_region").astype(str)
    df["ACTIVE"] = df_raw["IS_ACTIVE"].astype(bool)
    df["CREATED_AT"] = pd.to_datetime(df_raw["CREATED_AT"])

    return df


# ---------------------------------------------------------------------------
# Main Loader Runner
# ---------------------------------------------------------------------------

TABLE_CONFIGS = [
    {
        "table": "KYC_PROFILES",
        "csv": _ROOT / "data" / "synthetic" / "kyc_profiles.csv",
        "transformer": transform_kyc_profiles,
        "is_variant_needed": False,
    },
    {
        "table": "TRANSACTIONS",
        "csv": _ROOT / "data" / "synthetic" / "transactions.csv",
        "transformer": transform_transactions,
        "is_variant_needed": False,
    },
    {
        "table": "AML_WATCHLIST",
        "csv": _ROOT / "data" / "synthetic" / "aml_watchlist.csv",
        "transformer": transform_aml_watchlist,
        "is_variant_needed": True,
        "variant_col": "ALIAS_NAMES",
    },
    {
        "table": "USER_PERMISSIONS",
        "csv": _ROOT / "data" / "synthetic" / "user_permissions.csv",
        "transformer": transform_user_permissions,
        "is_variant_needed": True,
        "variant_col": "ALLOWED_DOC_CATEGORIES",
    },
]


def load_all_data(selected_tables: list[str] | None = None, dry_run: bool = False):
    """Execute ingestion pipeline for all configured tables."""
    print("=" * 65)
    print(" ⚡ Auris — Snowflake Synthetic Data Loader")
    print("=" * 65)

    if dry_run:
        print("🔍 DRY RUN MODE: Validating files and transformations only.\n")

    conn, database, schema = (None, None, None)
    if not dry_run:
        try:
            conn, database, schema = get_snowflake_connection()
            print(" Connected successfully to Snowflake!\n")
        except Exception as e:
            print(f"\n❌ Connection failed: {e}")
            print("\nPlease ensure you have:")
            print("1. Run `sql/setup/01_database_warehouse.sql` in Snowflake Worksheets.")
            print("2. Correct account, username, and password in `.env`.")
            sys.exit(1)

    from snowflake.connector.pandas_tools import write_pandas

    summary = []

    for cfg in TABLE_CONFIGS:
        table_name = cfg["table"]
        if selected_tables and table_name not in selected_tables:
            continue

        csv_file = cfg["csv"]
        if not csv_file.exists():
            print(f"⚠️  File not found: {csv_file}. Run `python data/synthetic/generate_data.py` first.")
            continue

        t0 = time.time()
        print(f"📦 Processing {table_name} from {csv_file.name}...")
        df_clean = cfg["transformer"](csv_file)
        row_count = len(df_clean)
        elapsed_transform = time.time() - t0
        print(f"   ↳ Cleaned & mapped {row_count:,} rows ({elapsed_transform:.2f}s)")

        if dry_run:
            summary.append((table_name, row_count, "DRY-RUN OK", f"{elapsed_transform:.2f}s"))
            continue

        # Ingestion into Snowflake
        try:
            t_ingest = time.time()
            cursor = conn.cursor()

            # Ensure warehouse is active
            cursor.execute("USE WAREHOUSE AURIS_DEV_WH;")

            # Write dataframe
            success, nchunks, nrows, _ = write_pandas(
                conn=conn,
                df=df_clean,
                table_name=table_name,
                database=database,
                schema=schema,
                overwrite=True,
                auto_create_table=False,
                quote_identifiers=False,
                use_logical_type=True,
            )

            # If VARIANT column needs parsing from JSON string to native VARIANT
            if cfg.get("is_variant_needed") and cfg.get("variant_col"):
                col = cfg["variant_col"]
                try:
                    cursor.execute(
                        f"""
                        UPDATE {database}.{schema}.{table_name}
                        SET {col} = PARSE_JSON({col}::VARCHAR)
                        WHERE {col} IS NOT NULL
                        """
                    )
                except Exception as var_err:
                    print(f"   (Notice: VARIANT parse skipped: {var_err})")

            # Verify count
            cursor.execute(f"SELECT COUNT(*) FROM {database}.{schema}.{table_name}")
            actual_count = cursor.fetchone()[0]

            elapsed_total = time.time() - t_ingest
            print(f"   ✅ Successfully loaded into {table_name}! (Verified: {actual_count:,} rows in {elapsed_total:.2f}s)\n")
            summary.append((table_name, actual_count, "SUCCESS", f"{elapsed_total:.2f}s"))
            cursor.close()

        except Exception as err:
            print(f"   ❌ Failed to load {table_name}: {err}\n")
            summary.append((table_name, row_count, "FAILED", "-"))

    if conn:
        conn.close()

    # Final summary display
    print("=" * 65)
    print(" INGESTION SUMMARY")
    print("=" * 65)
    print(f"  {'Table Name':<20} {'Rows':>10}  {'Status':<12} {'Time':>8}")
    print("  " + "-" * 56)
    for t_name, rows, status, duration in summary:
        print(f"  {t_name:<20} {rows:>10,}  {status:<12} {duration:>8}")
    print("=" * 65)
    print("\nNext step: Run your queries or switch `AURIS_ENV=snowflake` in `.env` to test live!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest synthetic data into Snowflake tables.")
    parser.add_argument("--tables", nargs="+", help="Specific tables to ingest (e.g. TRANSACTIONS KYC_PROFILES)")
    parser.add_argument("--dry-run", action="store_true", help="Validate transformations without loading into Snowflake")
    args = parser.parse_args()

    load_all_data(selected_tables=args.tables, dry_run=args.dry_run)
