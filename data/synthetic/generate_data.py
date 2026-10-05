"""
generate_data.py
================
Synthetic data generator for the Auris compliance hackathon project.

Generates realistic Indian financial data for:
- KYC customer profiles (Aadhaar, PAN, risk tiers)
- Financial transactions (NEFT/RTGS/IMPS/UPI/CASH) including fraud patterns
- AML watchlist entries (OFAC / UN / EU / RBI sanctions)
- Demo user permission records

Usage
-----
    python data/synthetic/generate_data.py

All CSVs are written to the ``data/synthetic/`` directory.

Dependencies
------------
    pip install faker numpy pandas
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import string
import sys

# Force UTF-8 stdout — Windows terminals default to cp1252 which can't encode
# Unicode arrows (→) and rupee symbols (₹) used in progress output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
from faker import Faker
from faker.providers import person, address

# ---------------------------------------------------------------------------
# Ensure project root is importable (for config)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402

fake = Faker("en_IN")
fake.add_provider(person)
fake.add_provider(address)

random.seed(42)
np.random.seed(42)

# Output directory is the same as this script's directory
_OUT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INDIAN_STATES = [
    "Maharashtra", "Karnataka", "Tamil Nadu", "Uttar Pradesh", "West Bengal",
    "Gujarat", "Rajasthan", "Andhra Pradesh", "Telangana", "Kerala",
    "Madhya Pradesh", "Punjab", "Haryana", "Bihar", "Odisha",
    "Jharkhand", "Assam", "Chhattisgarh", "Uttarakhand", "Himachal Pradesh",
]

INDIAN_CITIES: dict[str, list[str]] = {
    "Maharashtra":    ["Mumbai", "Pune", "Nagpur", "Thane", "Nashik"],
    "Karnataka":      ["Bengaluru", "Mysuru", "Hubli", "Mangaluru", "Belagavi"],
    "Tamil Nadu":     ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli"],
    "Uttar Pradesh":  ["Lucknow", "Kanpur", "Agra", "Varanasi", "Meerut"],
    "West Bengal":    ["Kolkata", "Howrah", "Durgapur", "Asansol", "Siliguri"],
    "Gujarat":        ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"],
    "Rajasthan":      ["Jaipur", "Jodhpur", "Udaipur", "Kota", "Ajmer"],
    "Andhra Pradesh": ["Visakhapatnam", "Vijayawada", "Guntur", "Tirupati", "Kakinada"],
    "Telangana":      ["Hyderabad", "Warangal", "Nizamabad", "Karimnagar", "Khammam"],
    "Kerala":         ["Thiruvananthapuram", "Kochi", "Kozhikode", "Thrissur", "Kollam"],
    "Madhya Pradesh": ["Bhopal", "Indore", "Gwalior", "Jabalpur", "Ujjain"],
    "Punjab":         ["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda"],
    "Haryana":        ["Gurugram", "Faridabad", "Panipat", "Ambala", "Hisar"],
    "Bihar":          ["Patna", "Gaya", "Bhagalpur", "Muzaffarpur", "Darbhanga"],
    "Odisha":         ["Bhubaneswar", "Cuttack", "Rourkela", "Berhampur", "Sambalpur"],
    "Jharkhand":      ["Ranchi", "Jamshedpur", "Dhanbad", "Bokaro", "Deoghar"],
    "Assam":          ["Guwahati", "Dibrugarh", "Silchar", "Jorhat", "Nagaon"],
    "Chhattisgarh":   ["Raipur", "Bhilai", "Bilaspur", "Korba", "Durg"],
    "Uttarakhand":    ["Dehradun", "Haridwar", "Roorkee", "Haldwani", "Rudrapur"],
    "Himachal Pradesh": ["Shimla", "Dharamsala", "Mandi", "Solan", "Kullu"],
}

ACCOUNT_TYPES = ["SAVINGS", "CURRENT", "NRI_NRE", "NRI_NRO", "SALARY", "FIXED_DEPOSIT"]
KYC_STATUSES  = ["COMPLETE", "PENDING_DOCS", "UNDER_REVIEW", "EXPIRED"]
TXN_TYPES     = ["NEFT", "RTGS", "IMPS", "UPI", "CASH"]

INTERNATIONAL_COUNTRIES = [
    "United Arab Emirates", "United States", "United Kingdom", "Singapore",
    "Hong Kong", "Cayman Islands", "British Virgin Islands", "Switzerland",
    "Panama", "Mauritius",
]

# Weighted transaction type distribution (realistic Indian banking)
TXN_TYPE_WEIGHTS = [0.20, 0.10, 0.25, 0.40, 0.05]  # NEFT, RTGS, IMPS, UPI, CASH

# Sanctioned list sources
WATCHLIST_SOURCES = ["OFAC", "UN_CONSOLIDATED", "EU_FINANCIAL_SANCTIONS", "RBI_CAUTION_LIST"]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _random_pan() -> str:
    """Generate a syntactically valid Indian PAN number (ABCDE1234F format)."""
    alpha5 = "".join(random.choices(string.ascii_uppercase, k=5))
    digits4 = "".join(random.choices(string.digits, k=4))
    last_alpha = random.choice(string.ascii_uppercase)
    return f"{alpha5}{digits4}{last_alpha}"


def _aadhaar_hash() -> str:
    """Return SHA-256 hash of a random 12-digit Aadhaar number."""
    aadhaar = "".join(random.choices(string.digits, k=12))
    return hashlib.sha256(aadhaar.encode()).hexdigest()


def _random_state_city() -> Tuple[str, str]:
    """Pick a random (state, city) pair from the Indian cities mapping."""
    state = random.choice(INDIAN_STATES)
    city  = random.choice(INDIAN_CITIES.get(state, [state]))
    return state, city


def _random_dob(min_age: int = 18, max_age: int = 75) -> date:
    """Return a random date of birth within the given age range."""
    today = date.today()
    delta_days = random.randint(min_age * 365, max_age * 365)
    return today - timedelta(days=delta_days)


def _risk_tier_weights() -> Tuple[str, int, int]:
    """Return (risk_tier, risk_score_low, risk_score_high) based on distribution.

    Distribution: 60% LOW, 30% MEDIUM, 10% HIGH.
    """
    roll = random.random()
    if roll < 0.60:
        return "LOW", 1, 40
    if roll < 0.90:
        return "MEDIUM", 41, 70
    return "HIGH", 71, 100


# ---------------------------------------------------------------------------
# Generator: KYC profiles
# ---------------------------------------------------------------------------


def generate_kyc_profiles(n: int = 500) -> pd.DataFrame:
    """Generate *n* synthetic KYC customer profiles for Indian bank customers.

    Risk distribution: 60% LOW, 30% MEDIUM, 10% HIGH.
    Politically Exposed Persons (PEP): ~5% of total.

    Parameters
    ----------
    n:
        Number of customer records to generate.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        CUSTOMER_ID, FULL_NAME, PAN_NUMBER, AADHAAR_HASH, DATE_OF_BIRTH,
        AGE, STATE, CITY, ACCOUNT_TYPE, KYC_STATUS, RISK_TIER, RISK_SCORE,
        IS_PEP, IS_ACTIVE, CUSTOMER_SINCE, OCCUPATION.
    """
    print(f"[generate_data] Generating {n} KYC profiles …")
    occupations = [
        "Salaried", "Business Owner", "Self-Employed Professional",
        "Retired", "Student", "Agriculturist", "Government Employee",
        "NRI", "Politician", "Bureaucrat",
    ]

    rows: list[dict] = []
    for i in range(n):
        state, city = _random_state_city()
        risk_tier, score_low, score_high = _risk_tier_weights()
        risk_score = random.randint(score_low, score_high)
        dob = _random_dob()
        age = (date.today() - dob).days // 365

        is_pep = random.random() < 0.05
        if is_pep:
            occupation = random.choice(["Politician", "Bureaucrat"])
        else:
            occupation = random.choice(occupations[:-2])  # exclude politician/bureaucrat

        kyc_weights = [0.75, 0.10, 0.10, 0.05]  # COMPLETE most common
        kyc_status = random.choices(KYC_STATUSES, weights=kyc_weights, k=1)[0]

        rows.append(
            {
                "CUSTOMER_ID": f"CUST-{i + 1:05d}",
                "FULL_NAME": fake.name(),
                "PAN_NUMBER": _random_pan(),
                "AADHAAR_HASH": _aadhaar_hash(),
                "DATE_OF_BIRTH": dob.isoformat(),
                "AGE": age,
                "STATE": state,
                "CITY": city,
                "ACCOUNT_TYPE": random.choice(ACCOUNT_TYPES),
                "KYC_STATUS": kyc_status,
                "RISK_TIER": risk_tier,
                "RISK_SCORE": risk_score,
                "IS_PEP": is_pep,
                "IS_ACTIVE": random.random() > 0.03,  # 97% active
                "CUSTOMER_SINCE": fake.date_between(start_date="-15y", end_date="-6m").isoformat(),
                "OCCUPATION": occupation,
            }
        )

    df = pd.DataFrame(rows)
    print(f"  → {len(df)} KYC profiles created.")
    return df


# ---------------------------------------------------------------------------
# Generator: Transactions
# ---------------------------------------------------------------------------


def _compute_risk_score(
    amount: float,
    txn_type: str,
    counterparty_country: str,
    customer_risk_tier: str,
) -> int:
    """Compute a rule-based AML risk score for a transaction.

    Scoring rules:
    - Amount > ₹10,00,000         → +30
    - Amount > ₹5,00,000          → +15
    - Amount > ₹1,00,000          → +5
    - International counterparty  → +20
    - HIGH-risk customer          → +25
    - MEDIUM-risk customer        → +10
    - CASH transaction            → +15
    - KYC status PENDING/EXPIRED  → +10 (not available here; handled downstream)

    Score is clamped to [0, 100].
    """
    score = 0

    # Amount thresholds
    if amount >= 10_00_000:
        score += 30
    elif amount >= 5_00_000:
        score += 15
    elif amount >= 1_00_000:
        score += 5

    # International
    if counterparty_country != "India":
        score += 20

    # Customer risk tier
    if customer_risk_tier == "HIGH":
        score += 25
    elif customer_risk_tier == "MEDIUM":
        score += 10

    # Cash
    if txn_type == "CASH":
        score += 15

    # Small random noise (±5) to add realism
    score += random.randint(-5, 5)

    return max(0, min(100, score))


def _random_amount() -> float:
    """Return a random transaction amount with realistic distribution.

    Mix:
    - 60% small   : ₹100 – ₹50,000
    - 25% medium  : ₹50,001 – ₹5,00,000
    - 15% large   : ₹5,00,001 – ₹50,00,000
    """
    roll = random.random()
    if roll < 0.60:
        return round(random.uniform(100, 50_000), 2)
    if roll < 0.85:
        return round(random.uniform(50_001, 5_00_000), 2)
    return round(random.uniform(5_00_001, 50_00_000), 2)


def generate_transactions(kyc_df: pd.DataFrame, n: int = 10_000) -> pd.DataFrame:
    """Generate *n* synthetic financial transactions linked to *kyc_df*.

    Includes:
    - Realistic transaction type distribution
    - 3% international transactions
    - Rule-based risk scoring
    - AML flag for risk_score ≥ 70
    - 50 injected structuring patterns (multiple sub-₹10L txns same day)

    Parameters
    ----------
    kyc_df:
        DataFrame produced by :func:`generate_kyc_profiles`.
    n:
        Number of base transactions to generate.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        TXN_ID, CUSTOMER_ID, TXN_DATE, AMOUNT, TXN_TYPE, COUNTERPARTY_NAME,
        COUNTERPARTY_ACCOUNT, COUNTERPARTY_COUNTRY, RISK_SCORE, AML_FLAG,
        TXN_STATUS, DESCRIPTION.
    """
    print(f"[generate_data] Generating {n} transactions …")
    today = date.today()
    customer_ids = kyc_df["CUSTOMER_ID"].tolist()
    customer_risk_map: dict[str, str] = dict(
        zip(kyc_df["CUSTOMER_ID"], kyc_df["RISK_TIER"])
    )

    rows: list[dict] = []

    for i in range(n):
        cust_id = random.choice(customer_ids)
        txn_type = random.choices(TXN_TYPES, weights=TXN_TYPE_WEIGHTS, k=1)[0]
        amount = _random_amount()

        # 3% international
        if random.random() < 0.03:
            counterparty_country = random.choice(INTERNATIONAL_COUNTRIES)
        else:
            counterparty_country = "India"

        txn_date = today - timedelta(days=random.randint(0, 89))
        risk_score = _compute_risk_score(
            amount, txn_type, counterparty_country, customer_risk_map.get(cust_id, "LOW")
        )
        aml_flag = risk_score >= config.FRAUD_ALERT_THRESHOLD

        rows.append(
            {
                "TXN_ID": f"TXN-{i + 1:05d}",
                "CUSTOMER_ID": cust_id,
                "TXN_DATE": txn_date.isoformat(),
                "AMOUNT": amount,
                "TXN_TYPE": txn_type,
                "COUNTERPARTY_NAME": fake.company() if random.random() > 0.5 else fake.name(),
                "COUNTERPARTY_ACCOUNT": "".join(random.choices(string.digits, k=14)),
                "COUNTERPARTY_COUNTRY": counterparty_country,
                "RISK_SCORE": risk_score,
                "AML_FLAG": aml_flag,
                "TXN_STATUS": random.choices(
                    ["COMPLETED", "PENDING", "FAILED"],
                    weights=[0.92, 0.05, 0.03],
                    k=1,
                )[0],
                "DESCRIPTION": random.choice(
                    [
                        "Vendor payment",
                        "Salary transfer",
                        "Loan repayment",
                        "Investment",
                        "Family remittance",
                        "Trade payment",
                        "Insurance premium",
                        "Rental income",
                        "Dividend",
                        "Consulting fee",
                    ]
                ),
            }
        )

    # -----------------------------------------------------------------------
    # Inject 50 structuring patterns
    # (multiple transactions just under ₹10L from the same customer on the
    #  same day — classic "structuring" AML red flag)
    # -----------------------------------------------------------------------
    print("[generate_data] Injecting 50 structuring fraud patterns …")
    structuring_customers = random.sample(customer_ids, k=min(10, len(customer_ids)))
    txn_counter = n + 1

    for cust_id in structuring_customers:
        struct_date = today - timedelta(days=random.randint(0, 60))
        # 5 transactions each, each just under ₹10L
        for _ in range(5):
            struct_amount = round(random.uniform(9_50_000, 9_99_000), 2)
            risk_score = _compute_risk_score(
                struct_amount, "NEFT", "India", customer_risk_map.get(cust_id, "LOW")
            )
            # Force high risk score for structuring
            risk_score = max(risk_score, 75)

            rows.append(
                {
                    "TXN_ID": f"TXN-{txn_counter:05d}",
                    "CUSTOMER_ID": cust_id,
                    "TXN_DATE": struct_date.isoformat(),
                    "AMOUNT": struct_amount,
                    "TXN_TYPE": "NEFT",
                    "COUNTERPARTY_NAME": fake.company(),
                    "COUNTERPARTY_ACCOUNT": "".join(random.choices(string.digits, k=14)),
                    "COUNTERPARTY_COUNTRY": "India",
                    "RISK_SCORE": risk_score,
                    "AML_FLAG": True,  # Always flag structuring
                    "TXN_STATUS": "COMPLETED",
                    "DESCRIPTION": "Business payment",
                }
            )
            txn_counter += 1

    df = pd.DataFrame(rows)
    print(f"  → {len(df)} transactions created ({df['AML_FLAG'].sum()} flagged).")
    return df


# ---------------------------------------------------------------------------
# Generator: AML watchlist
# ---------------------------------------------------------------------------


def generate_aml_watchlist() -> pd.DataFrame:
    """Generate 100 synthetic AML / sanctions watchlist entries.

    Entries mix Indian and international sanctioned entities across
    OFAC, UN, EU, and RBI lists.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        ENTITY_ID, ENTITY_NAME, ENTITY_TYPE, ALIAS_NAMES, NATIONALITY,
        LISTED_DATE, LISTING_SOURCE, LIST_CATEGORY, REASON, IS_ACTIVE.
    """
    print("[generate_data] Generating AML watchlist …")

    indian_names = [
        "Dawood Ibrahim Kaskar", "Hafiz Mohammad Saeed", "Iqbal Mirchi",
        "Abu Salem", "Ravi Pujari", "Chhota Shakeel", "Neeraj Bawana",
        "Jitendra Mane", "Arun Gawli", "Ejaz Lakdawala",
        "Pramod Mahajan Associates Ltd", "Phantom Exports Pvt Ltd",
        "Blue Chip Finance Corp", "Apex Bullion Traders", "Nexus Remittance",
    ]

    international_names = [
        "Al-Shabaab Financing Network", "Hezbollah Commercial Front",
        "Viktor Kozlov Trading LLC", "Pedro Escobar Holdings",
        "Dragon Shadow Enterprises", "Al-Nusra Investment Corp",
        "Vladislav Petrov Group", "Caribbean Shell Holdings Ltd",
        "Mohamed Al-Rashid Trading", "Kim Jong Nam Export Co.",
        "Thunder Peak Resources Ltd", "Black Sea Capital Partners",
        "Oasis Petroleum DMCC", "Pacific Rim Wealth Management",
        "Global Hawk Finance BVI",
    ]

    entity_types  = ["INDIVIDUAL", "COMPANY", "TRUST", "FOUNDATION"]
    list_categories = ["TERRORISM_FINANCING", "MONEY_LAUNDERING", "SANCTIONS_EVASION",
                       "PROLIFERATION_FINANCING", "NARCOTICS", "FRAUD", "CYBERCRIME"]
    nationalities = ["Indian", "Pakistani", "Russian", "Colombian", "North Korean",
                     "Iranian", "Syrian", "Venezuelan", "Chinese", "Nigerian"]

    rows: list[dict] = []
    all_names = indian_names + international_names
    # Pad to 100 with generated names
    while len(all_names) < 100:
        all_names.append(fake.company() if random.random() > 0.4 else fake.name())

    random.shuffle(all_names)

    for i, name in enumerate(all_names[:100]):
        source = random.choice(WATCHLIST_SOURCES)
        entity_type = "INDIVIDUAL" if any(
            c.islower() for c in name.split()[0]
        ) or len(name.split()) <= 3 else "COMPANY"

        # 2–4 alias names
        alias_count = random.randint(0, 4)
        aliases = [fake.name() if entity_type == "INDIVIDUAL" else fake.company()
                   for _ in range(alias_count)]

        rows.append(
            {
                "ENTITY_ID": f"WL-{i + 1:04d}",
                "ENTITY_NAME": name,
                "ENTITY_TYPE": entity_type,
                "ALIAS_NAMES": json.dumps(aliases),
                "NATIONALITY": random.choice(nationalities),
                "LISTED_DATE": fake.date_between(start_date="-10y", end_date="-30d").isoformat(),
                "LISTING_SOURCE": source,
                "LIST_CATEGORY": random.choice(list_categories),
                "REASON": random.choice(
                    [
                        "Designated under PMLA 2002",
                        "OFAC SDN designation",
                        "UN Security Council Resolution 1267 listing",
                        "EU Regulation 2580/2001",
                        "RBI Caution Notice",
                        "FATF High-Risk Jurisdiction association",
                        "Narcotics trafficking",
                        "Financing of proliferation activities",
                    ]
                ),
                "IS_ACTIVE": random.random() > 0.08,  # 92% still active
            }
        )

    df = pd.DataFrame(rows)
    print(f"  → {len(df)} watchlist entries created.")
    return df


# ---------------------------------------------------------------------------
# Generator: User permissions
# ---------------------------------------------------------------------------


def generate_user_permissions() -> pd.DataFrame:
    """Generate demo user permission records aligned with ``config.USER_ROLES``.

    Hard-coded demo users:
    - USER001 / Priya Sharma     / junior_analyst
    - USER002 / Rahul Mehta      / senior_analyst
    - USER003 / Deepa Krishnan   / compliance_head

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        USER_ID, FULL_NAME, ROLE, ROLE_LEVEL, ALLOWED_DOC_CATEGORIES,
        EMAIL, IS_ACTIVE, CREATED_AT.
    """
    print("[generate_data] Generating user permissions …")
    user_roles: dict = getattr(config, "USER_ROLES", {})

    demo_users = [
        ("USER001", "Priya Sharma",    "junior_analyst"),
        ("USER002", "Rahul Mehta",     "senior_analyst"),
        ("USER003", "Deepa Krishnan",  "compliance_head"),
    ]

    rows: list[dict] = []
    for uid, name, role in demo_users:
        role_config = user_roles.get(role, {})
        level = role_config.get("level", 1)
        allowed_categories = role_config.get(
            "allowed_doc_categories",
            ["KYC", "AML", "TRANSACTIONS"],
        )
        first, *rest = name.lower().split()
        email = f"{first}.{''.join(rest)}@auris.internal"

        rows.append(
            {
                "USER_ID": uid,
                "FULL_NAME": name,
                "ROLE": role,
                "ROLE_LEVEL": level,
                "ALLOWED_DOC_CATEGORIES": json.dumps(allowed_categories),
                "EMAIL": email,
                "IS_ACTIVE": True,
                "CREATED_AT": datetime(2024, 1, 15).isoformat(),
            }
        )

    df = pd.DataFrame(rows)
    print(f"  → {len(df)} user permission records created.")
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Generate all synthetic datasets and save them as CSV files.

    Files created in ``data/synthetic/``:
    - ``kyc_profiles.csv``
    - ``transactions.csv``
    - ``aml_watchlist.csv``
    - ``user_permissions.csv``
    """
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    kyc_count = getattr(config, "SYNTHETIC_KYC_COUNT", 500)
    txn_count = getattr(config, "SYNTHETIC_TRANSACTION_COUNT", 10_000)

    # 1. KYC profiles
    kyc_df = generate_kyc_profiles(n=kyc_count)
    kyc_path = _OUT_DIR / "kyc_profiles.csv"
    kyc_df.to_csv(kyc_path, index=False)

    # 2. Transactions
    txn_df = generate_transactions(kyc_df, n=txn_count)
    txn_path = _OUT_DIR / "transactions.csv"
    txn_df.to_csv(txn_path, index=False)

    # 3. AML watchlist
    wl_df = generate_aml_watchlist()
    wl_path = _OUT_DIR / "aml_watchlist.csv"
    wl_df.to_csv(wl_path, index=False)

    # 4. User permissions
    users_df = generate_user_permissions()
    users_path = _OUT_DIR / "user_permissions.csv"
    users_df.to_csv(users_path, index=False)

    # Summary
    print("\n" + "=" * 60)
    print("SYNTHETIC DATA GENERATION COMPLETE")
    print("=" * 60)
    datasets = [
        ("KYC Profiles",    kyc_path,   kyc_df),
        ("Transactions",    txn_path,   txn_df),
        ("AML Watchlist",   wl_path,    wl_df),
        ("User Permissions",users_path, users_df),
    ]
    for label, path, df in datasets:
        size_kb = path.stat().st_size / 1024
        print(f"  {label:<20} {len(df):>6,} rows  |  {size_kb:>8.1f} KB  →  {path.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
