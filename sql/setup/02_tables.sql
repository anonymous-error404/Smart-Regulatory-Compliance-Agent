
USE DATABASE AURIS_DB;
USE SCHEMA AURIS_SCHEMA;

CREATE TABLE IF NOT EXISTS TRANSACTIONS (
    TXN_ID               VARCHAR(64)     NOT NULL COMMENT 'Unique transaction identifier (UUID or bank-assigned)',
    CUSTOMER_ID          VARCHAR(64)     NOT NULL COMMENT 'Foreign key to KYC_PROFILES',
    TXN_DATE             TIMESTAMP_NTZ   NOT NULL COMMENT 'Transaction execution timestamp (UTC)',
    AMOUNT_INR           NUMBER(18, 2)   NOT NULL COMMENT 'Transaction amount in Indian Rupees',
    TXN_TYPE             VARCHAR(16)     NOT NULL COMMENT 'Payment rail: NEFT | RTGS | IMPS | UPI | CASH',
    CHANNEL              VARCHAR(16)     NOT NULL COMMENT 'Originating channel: BRANCH | ONLINE | ATM | MOBILE',
    COUNTERPARTY_ACCOUNT VARCHAR(64)              COMMENT 'Beneficiary account number (may be masked)',
    COUNTERPARTY_BANK    VARCHAR(128)             COMMENT 'Beneficiary bank name / IFSC prefix',
    COUNTERPARTY_COUNTRY VARCHAR(64)              COMMENT 'Beneficiary country ISO-3166-1 alpha-2',
    DESCRIPTION          VARCHAR(512)             COMMENT 'Narration / payment reference text',
    IS_INTERNATIONAL     BOOLEAN         NOT NULL DEFAULT FALSE COMMENT 'TRUE if counterparty is outside India',
    RISK_SCORE           NUMBER(5, 2)    NOT NULL DEFAULT 0     COMMENT 'ML-derived risk score 0–100',
    AML_FLAG             BOOLEAN         NOT NULL DEFAULT FALSE COMMENT 'TRUE if AML pattern detected',
    FRAUD_FLAG           BOOLEAN         NOT NULL DEFAULT FALSE COMMENT 'TRUE if fraud pattern detected',
    REVIEWED             BOOLEAN         NOT NULL DEFAULT FALSE COMMENT 'TRUE once a compliance officer has reviewed',
    CREATED_AT           TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Row ingestion timestamp',

    CONSTRAINT PK_TRANSACTIONS PRIMARY KEY (TXN_ID)
);

CREATE TABLE IF NOT EXISTS KYC_PROFILES (
    CUSTOMER_ID         VARCHAR(64)     NOT NULL COMMENT 'Unique customer identifier',
    FULL_NAME           VARCHAR(256)    NOT NULL COMMENT 'Legal full name as per KYC document',
    PAN_NUMBER          VARCHAR(16)              COMMENT 'Masked PAN: e.g. ABCPX1234X -> ABCPX****X',
    AADHAR_HASH         VARCHAR(128)             COMMENT 'SHA-256 hash of the 12-digit Aadhaar number',
    DOB                 DATE                     COMMENT 'Date of birth',
    ACCOUNT_TYPE        VARCHAR(16)     NOT NULL COMMENT 'Account category: SAVINGS | CURRENT | NRI',
    KYC_STATUS          VARCHAR(16)     NOT NULL COMMENT 'Current KYC state: VERIFIED | PENDING | EXPIRED',
    RISK_CATEGORY       VARCHAR(8)      NOT NULL DEFAULT 'LOW' COMMENT 'Customer risk tier: LOW | MEDIUM | HIGH',
    ANNUAL_INCOME_INR   NUMBER(18, 2)            COMMENT 'Declared annual income in INR',
    POLITICALLY_EXPOSED BOOLEAN         NOT NULL DEFAULT FALSE COMMENT 'TRUE if customer is a Politically Exposed Person (PEP)',
    NATIONALITY         VARCHAR(64)              COMMENT 'Country of citizenship',
    STATE               VARCHAR(64)              COMMENT 'Indian state of residence',
    CITY                VARCHAR(128)             COMMENT 'City of residence',
    ONBOARDED_AT        TIMESTAMP_NTZ            COMMENT 'Account opening / KYC completion timestamp',
    LAST_UPDATED        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Last profile update timestamp',

    CONSTRAINT PK_KYC_PROFILES PRIMARY KEY (CUSTOMER_ID)
);


CREATE TABLE IF NOT EXISTS AML_WATCHLIST (
    ENTITY_ID    VARCHAR(64)     NOT NULL COMMENT 'Unique watchlist entity identifier',
    ENTITY_NAME  VARCHAR(512)    NOT NULL COMMENT 'Primary name of the sanctioned entity',
    ENTITY_TYPE  VARCHAR(16)     NOT NULL COMMENT 'Classification: INDIVIDUAL | ORGANIZATION',
    SANCTION_LIST VARCHAR(16)    NOT NULL COMMENT 'Source list: OFAC | UN | EU | RBI',
    COUNTRY      VARCHAR(64)              COMMENT 'Country of origin / registration',
    ALIAS_NAMES  VARIANT                  COMMENT 'JSON array of alternative names / spellings',
    ADDED_DATE   DATE            NOT NULL COMMENT 'Date the entity was added to the watchlist',
    STATUS       VARCHAR(16)     NOT NULL DEFAULT 'ACTIVE' COMMENT 'Listing status: ACTIVE | REMOVED',
    SOURCE_URL   VARCHAR(2048)            COMMENT 'URL to the official sanctions list entry',

    CONSTRAINT PK_AML_WATCHLIST PRIMARY KEY (ENTITY_ID)
);

CREATE TABLE IF NOT EXISTS USER_PERMISSIONS (
    USER_ID                VARCHAR(64)  NOT NULL COMMENT 'Unique user identifier (maps to Snowflake login)',
    USERNAME               VARCHAR(128) NOT NULL COMMENT 'Display name / email',
    ROLE                   VARCHAR(32)  NOT NULL COMMENT 'Access role: junior_analyst | senior_analyst | compliance_head',
    ALLOWED_DOC_CATEGORIES VARIANT               COMMENT 'JSON array of permitted document categories, e.g. ["AML","BASEL"]',
    DATA_SCOPE             VARCHAR(32)  NOT NULL COMMENT 'Data visibility: own_region | national | all',
    ACTIVE                 BOOLEAN      NOT NULL DEFAULT TRUE COMMENT 'FALSE = account disabled',
    CREATED_AT             TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Account creation timestamp',

    CONSTRAINT PK_USER_PERMISSIONS PRIMARY KEY (USER_ID)
);

CREATE TABLE IF NOT EXISTS AUDIT_TRAIL (
    AUDIT_ID               VARCHAR(64)   NOT NULL DEFAULT UUID_STRING() COMMENT 'Auto-generated UUID for each audit record',
    USER_ID                VARCHAR(64)   NOT NULL COMMENT 'User who submitted the query',
    QUERY_TEXT             VARCHAR(4096) NOT NULL COMMENT 'Raw natural-language query text',
    AGENT_ROUTED_TO        VARCHAR(128)           COMMENT 'Name of the agent / tool that handled the query',
    RESPONSE_SUMMARY       VARCHAR(4096)          COMMENT 'Brief summary of the agent response returned to the user',
    RISK_SCORE_RETURNED    NUMBER(5, 2)            COMMENT 'Risk score surfaced in the response, if applicable',
    REGULATORY_CITATIONS   VARIANT                COMMENT 'JSON array of regulatory section references cited',
    QUERY_TIMESTAMP        TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when the query was received',
    SESSION_ID             VARCHAR(128)           COMMENT 'Streamlit or API session identifier for grouping',

    CONSTRAINT PK_AUDIT_TRAIL PRIMARY KEY (AUDIT_ID)
);

CREATE TABLE IF NOT EXISTS REGULATORY_REPORTS (
    REPORT_ID                  VARCHAR(64)   NOT NULL DEFAULT UUID_STRING() COMMENT 'Auto-generated UUID for each report',
    REPORT_TYPE                VARCHAR(32)   NOT NULL COMMENT 'Report category: AML_SUMMARY | BASEL_DISCLOSURE | FINTRAC',
    GENERATED_BY               VARCHAR(128)  NOT NULL COMMENT 'USER_ID or system process that triggered generation',
    GENERATED_AT               TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Generation timestamp',
    PERIOD_START               DATE          NOT NULL COMMENT 'Start of the reporting period',
    PERIOD_END                 DATE          NOT NULL COMMENT 'End of the reporting period',
    TXN_COUNT                  NUMBER(18, 0) NOT NULL DEFAULT 0 COMMENT 'Total transactions analysed in the period',
    HIGH_RISK_COUNT            NUMBER(18, 0) NOT NULL DEFAULT 0 COMMENT 'Number of transactions flagged as high-risk',
    TOTAL_FLAGGED_AMOUNT_INR   NUMBER(18, 2) NOT NULL DEFAULT 0 COMMENT 'Aggregate INR value of flagged transactions',
    REGULATORY_CITATIONS       VARIANT                COMMENT 'JSON array of regulatory references applicable to this report',
    REPORT_STATUS              VARCHAR(8)    NOT NULL DEFAULT 'DRAFT' COMMENT 'Lifecycle state: DRAFT | FINAL',
    REPORT_DATA                VARIANT                COMMENT 'Full structured report payload (JSON)',

    CONSTRAINT PK_REGULATORY_REPORTS PRIMARY KEY (REPORT_ID)
);
