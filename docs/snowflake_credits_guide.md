# ❄️ Snowflake Credits Guide — RegIQ Hackathon
### How to spend your $400 wisely and not run out mid-build

---

## 📋 Table of Contents
1. [Your $400 Budget — The Big Picture](#1-your-400-budget--the-big-picture)
2. [Is CoCo CLI Paid?](#2-is-coco-cli-paid)
3. [Local vs Snowflake — What Runs Where](#3-local-vs-snowflake--what-runs-where)
4. [Storage Costs — Synthetic Data](#4-storage-costs--synthetic-data)
5. [Expected Credit Expenditure](#5-expected-credit-expenditure)
6. [The #1 Credit Killer — Idle Warehouses](#6-the-1-credit-killer--idle-warehouses)
7. [Cortex LLM Model Selection](#7-cortex-llm-model-selection)
8. [Tips to Stay Within Budget](#8-tips-to-stay-within-budget)
9. [Quick Reference Cheatsheet](#9-quick-reference-cheatsheet)

---

## 1. Your $400 Budget — The Big Picture

You have **$400 in Snowflake credits** provided by the hackathon. Here's the honest summary of how that will be consumed:

| Category | Will it hurt your budget? |
|---|---|
| Storage (synthetic data + PDFs) | 🟢 Almost free — ~$0.004/month |
| CoCo CLI usage | 🟡 Minor — ~$10–20 total |
| Cortex Search indexing | 🟢 Cheap — ~$1–2 one-time |
| Cortex LLM inference (dev + testing) | 🔴 Biggest cost — ~$50–150 |
| Snowflake compute (queries, procedures) | 🟡 Minor if auto-suspend is on |
| Demo day runs | 🟢 Minimal — ~$5–10 |
| **Estimated total** | **~$70–200 out of $400** |

> ✅ $400 is comfortably enough for a hackathon prototype **if** you follow the tips in this doc. The main risk is not the cost of running things — it's leaving warehouses idle and using large LLM models during development when smaller ones work fine.

---

## 2. Is CoCo CLI Paid?

**CoCo CLI the tool itself is free** — you install it locally on your machine, no subscription required.

**What CoCo CLI does costs credits** — because under the hood, every prompt you type into CoCo CLI:

```
You type a prompt into CoCo CLI
    ↓
CoCo CLI calls Snowflake Cortex LLM to generate the code
    ↓  (this consumes Cortex credits)
CoCo CLI executes validation queries against your Snowflake account
    ↓  (this consumes compute credits)
You get the generated code back
```

However, CoCo CLI calls are lightweight. Generating a stored procedure or SQL schema is a small, focused LLM call — not a long multi-turn conversation. It should account for maybe **$10–20** of your total budget across the full build. Don't avoid using it to save credits — that's not the right trade-off. It's there to speed up your build significantly.

---

## 3. Local vs Snowflake — What Runs Where

Understanding this is important for your dev workflow — you don't need to be connected to Snowflake (and spending credits) every time you write a line of code.

| Component | Run locally? | Costs credits? | Notes |
|---|---|---|---|
| CoCo CLI (the tool) | ✅ Yes | 🟡 Minor | Installed on your machine |
| Writing Python / SQL code | ✅ Yes | ❌ No | Just a text editor — free |
| Streamlit UI (during dev) | ✅ Yes | 🟡 Only when querying Snowflake | Run `streamlit run app.py` locally |
| Snowpark Python logic | ✅ Partially | 🟡 When it hits Snowflake | Can mock Snowflake calls locally |
| Cortex LLM inference | ❌ Snowflake only | 🔴 Yes — every call costs | No local equivalent |
| Cortex Search queries | ❌ Snowflake only | 🟡 Minor | Index lives in Snowflake |
| Snowflake tables / data | ❌ Snowflake only | 🟡 Compute when queried | Storage itself is near-free |
| Snowflake Alerts | ❌ Snowflake only | 🟡 Minor | SQL-defined, runs in Snowflake |

### Recommended Dev Workflow

```
Phase 1 — Write & iterate locally (zero credits)
    Write Python agent logic
    Write SQL schemas
    Build Streamlit UI layout
    Mock Snowflake/Cortex responses with static test data

Phase 2 — Integration test on Snowflake (credits start here)
    Deploy tables and load synthetic data
    Index PDFs into Cortex Search
    Run agent logic against real Cortex LLM
    Test Streamlit against real Snowflake data

Phase 3 — Final deployment (minimal credits)
    Deploy Streamlit into Snowflake
    Run demo walkthrough once end-to-end
    Record demo video
```

> 💡 Most of your code-writing time should be in Phase 1. Only move to Phase 2 when a feature is ready to test end-to-end, not for every small change.

---

## 4. Storage Costs — Synthetic Data

Storage on Snowflake costs approximately **$23 per TB per month** on-demand. Your synthetic dataset will be tiny:

| Data | Estimated Size |
|---|---|
| 10,000 synthetic transaction records | ~5 MB |
| 500 synthetic KYC customer records | ~1 MB |
| AML watchlist (OFAC public list) | ~2 MB |
| RBI + Basel III/IV PDFs (10–15 docs) | ~50 MB |
| Cortex Search index of those PDFs | ~100 MB |
| ACL / permissions table | < 1 MB |
| **Total** | **~160 MB** |

### Cost calculation

```
160 MB = 0.000156 TB
0.000156 TB × $23/month = $0.004/month

For a 2-month hackathon period: ~$0.008 total
```

**Storage is essentially free for this project.** Don't spend any mental energy optimising it.

---

## 5. Expected Credit Expenditure

### Breakdown by Activity

| Activity | When | Frequency | Est. Cost |
|---|---|---|---|
| Setting up tables + loading data | Week 1, once | One-time | ~$1 |
| Cortex Search indexing of PDFs | Week 1, once | One-time | ~$1–2 |
| CoCo CLI code generation | Throughout build | ~50–100 prompts | ~$10–20 |
| Cortex LLM calls (dev testing, small model) | Weeks 2–4 | Many times | ~$30–80 |
| Cortex LLM calls (final model, integration tests) | Week 4–5 | Moderate | ~$20–50 |
| Streamlit + stored procedure compute | Throughout | Frequent | ~$5–15 |
| Demo day runs | Week 5 | 3–5 full runs | ~$5–10 |
| **Total Estimate** | | | **~$72–178** |

### Conservative vs Aggressive Usage

| Scenario | Estimated Spend |
|---|---|
| 🟢 Careful (small models, local mocking, auto-suspend on) | ~$70–100 |
| 🟡 Moderate (mix of models, reasonable testing) | ~$100–180 |
| 🔴 Careless (large models always, no auto-suspend, constant testing on Snowflake) | ~$250–400+ |

You have enough runway in all scenarios **except** careless usage. The tips in the next sections keep you in the green.

---

## 6. The #1 Credit Killer — Idle Warehouses

A Snowflake Virtual Warehouse **consumes credits even when it's not running a query**, as long as it's in a "running" state. Forgetting to suspend a warehouse after a dev session can burn $10–30 overnight doing absolutely nothing.

### Fix — Always set AUTO_SUSPEND

```sql
-- Run this when you create your warehouse
CREATE WAREHOUSE regiq_dev
  WAREHOUSE_SIZE = 'X-SMALL'   -- cheapest size, sufficient for dev
  AUTO_SUSPEND = 60             -- suspends after 60 seconds of inactivity
  AUTO_RESUME = TRUE;           -- resumes automatically when a query runs
```

```sql
-- Or alter an existing warehouse
ALTER WAREHOUSE regiq_dev SET AUTO_SUSPEND = 60;
```

### Warehouse Size Guide

| Size | Credits/hour | Use for |
|---|---|---|
| X-SMALL | 1 credit/hr | Development, testing — use this always |
| SMALL | 2 credits/hr | Only if queries are noticeably slow |
| MEDIUM+ | 4+ credits/hr | Never needed for this project |

> ✅ Stay on X-SMALL with AUTO_SUSPEND = 60 for the entire hackathon. You will never need anything bigger for a prototype with synthetic data at this scale.

---

## 7. Cortex LLM Model Selection

Cortex LLM inference is your biggest variable cost. Snowflake Cortex supports multiple models at different price points. **Use smaller models during development and switch up only for the final demo if needed.**

### Model Tiers (approximate, check Snowflake docs for current pricing)

| Model | Speed | Cost | Use when |
|---|---|---|---|
| `snowflake-arctic-instruct` | Fast | 🟢 Cheapest | Dev testing, basic logic validation |
| `mistral-7b` | Fast | 🟢 Cheap | Dev testing, unit testing agents |
| `mistral-large` | Medium | 🟡 Moderate | Integration testing, demo prep |
| `llama3.1-70b` | Slower | 🟡 Moderate | When quality matters |
| `llama3.1-405b` | Slow | 🔴 Expensive | Final demo only if needed |

### Recommended model strategy

```
Week 1–3 (building + unit testing)  →  use snowflake-arctic-instruct or mistral-7b
Week 4 (integration testing)         →  switch to mistral-large
Week 5 (demo + submission)           →  use mistral-large or llama3.1-70b
```

### In your code, make the model configurable

```python
# config.py — change this one line to switch models
CORTEX_MODEL = "snowflake-arctic-instruct"  # dev
# CORTEX_MODEL = "mistral-large"            # demo

# agent code
from config import CORTEX_MODEL
response = Complete(model=CORTEX_MODEL, prompt=prompt)
```

This way you never have to hunt through files to switch models.

---

## 8. Tips to Stay Within Budget

### 🔴 High Impact — Do These First

**1. Set AUTO_SUSPEND = 60 on your warehouse immediately**
Do this before you do anything else. A single forgotten overnight session can cost $10–20 for nothing.

**2. Mock Cortex LLM calls during local development**
Don't hit the real Cortex API every time you're tweaking UI layout or fixing a Python bug. Write a simple mock:

```python
# mock_cortex.py — use this during local dev
def Complete(model, prompt):
    return "MOCK RESPONSE: This is a placeholder for Cortex output."

# In your agent code
import os
if os.getenv("ENV") == "local":
    from mock_cortex import Complete
else:
    from snowflake.cortex import Complete
```

**3. Use small models during development**
`snowflake-arctic-instruct` or `mistral-7b` during dev. Only upgrade for integration tests and the final demo.

---

### 🟡 Medium Impact — Good Habits

**4. Test agents individually, not end-to-end every time**
When building the Fraud Agent, only test the Fraud Agent. Don't run the full orchestrator → all 3 agents → Streamlit flow just to check one small logic change.

**5. Keep your synthetic dataset small**
10,000 transactions is more than enough to demo. Don't generate 1M rows thinking it looks more impressive — it just costs more to query and doesn't help the demo.

**6. Cache repeated RAG results during testing**
If you're testing the same regulatory query 20 times, cache the Cortex Search result locally so you're not hitting the vector index on every run:

```python
import json, os

def cached_search(query, user_role):
    cache_key = f"cache_{hash(query+user_role)}.json"
    if os.path.exists(cache_key):
        return json.load(open(cache_key))
    result = cortex_search(query, user_role)  # real call
    json.dump(result, open(cache_key, "w"))
    return result
```

**7. Index PDFs only once**
Cortex Search indexing is a one-time cost per document set. Don't re-index unless you actually add new documents. Use `IF NOT EXISTS` guards in your setup scripts.

---

### 🟢 Low Impact — Nice to Have

**8. Monitor your credit usage weekly**
In Snowflake UI: `Admin → Cost Management → Credits Used`. Set a mental checkpoint — if you've used more than $100 by end of Week 3, you're burning too fast.

**9. Use a separate warehouse for Streamlit vs heavy queries**
If Streamlit UI queries and heavy agent logic share a warehouse, the UI feels slow when the agent is running. Two X-SMALL warehouses (one for UI, one for compute) gives better isolation with minimal cost difference.

**10. Suspend your warehouse manually at end of each dev session**
Even with AUTO_SUSPEND = 60, build the habit of running this at the end of each session:

```sql
ALTER WAREHOUSE regiq_dev SUSPEND;
```

---

## 9. Quick Reference Cheatsheet

```
┌─────────────────────────────────────────────────────────┐
│              REGIQ CREDITS CHEATSHEET                   │
├─────────────────────────────────────────────────────────┤
│ Total budget          $400                              │
│ Expected spend        $70–180                           │
│ Safe buffer           $220–330 remaining                │
├─────────────────────────────────────────────────────────┤
│ WAREHOUSE SETTINGS                                      │
│   Size                X-SMALL (1 credit/hr)             │
│   AUTO_SUSPEND        60 seconds                        │
│   AUTO_RESUME         TRUE                              │
├─────────────────────────────────────────────────────────┤
│ LLM MODEL BY PHASE                                      │
│   Dev / unit tests    snowflake-arctic-instruct         │
│   Integration tests   mistral-large                     │
│   Final demo          mistral-large / llama3.1-70b      │
├─────────────────────────────────────────────────────────┤
│ STORAGE                                                 │
│   Synthetic data      ~160 MB total                     │
│   Cost                ~$0.004/month (ignore this)       │
├─────────────────────────────────────────────────────────┤
│ BIGGEST CREDIT RISKS                                    │
│   🔴 Idle warehouse   Set AUTO_SUSPEND = 60 NOW         │
│   🔴 Large LLM dev    Use arctic/mistral-7b in dev      │
│   🔴 Repeat indexing  Index PDFs once, cache results    │
├─────────────────────────────────────────────────────────┤
│ MONITOR SPEND                                           │
│   Snowflake UI → Admin → Cost Management → Credits Used │
│   Check weekly. Alert if > $100 by end of Week 3.       │
└─────────────────────────────────────────────────────────┘
```

---

*Guide version: Hackathon build stage · RegIQ · Oct 2026*
