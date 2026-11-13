# Neon Free Database Resource Audit

**Audit Date**: November 13, 2026  
**Auditor**: Senior Database / Backend Engineer  
**Target Project**: `swing-trading` (Neon Project ID: `crimson-mountain-88821720`)  
**Region**: `aws-ap-southeast-1` (AWS Singapore)  
**PostgreSQL Version**: 18 (Serverless k8s-neonvm)  
**Neon Plan Tier**: `free_v3`  

---

## Executive Summary

The database is currently **OFFLINE / LOCKED** with HTTP status **402 Payment Required** (`NeonDbError: Your account or project has exceeded the quota. Upgrade your plan to increase limits.`). Direct client connections via SQLAlchemy and the Neon Management API fail with this error.

The quota breach was caused primarily by **network egress exhaustion** and **compute misconfiguration**, not database storage:
1. **Network Transfer (Public Egress)**: Consumed **6.31 GB** (6,313,725,087 bytes) against the monthly Free tier limit of **5.00 GB** (**126.3% of quota**).
2. **Compute Auto-Suspend Disabled**: The Neon endpoint setting `suspend_timeout_seconds` was configured to `0` (never scale down to zero). Active compute accumulated **92.96 hours** (334,648 seconds) and **25.94 CU-hours** in just 8 days of operation (Nov 1 to Nov 9).
3. **Continuous Off-Market Polling**: Background scheduler jobs (`live_monitor_IN`, `live_monitor_US`) executed database queries and committed execution records to `job_runs` every 60 seconds (previously 30s) 24/7, even during closed market hours, weekends, and holidays.
4. **Unbounded Audit & News Ingestion Growth**: Ingestion pipelines continuously appended unpruned records to `decision_stage_results` (16,317 rows), `news_events` (5,200 rows with raw JSON), and `decision_audits` (2,331 rows), increasing backup snapshot size from **9.63 MB to 28.41 MB in 3 days**.
5. **N+1 Database Query Patterns**: Ingestion of historical bars in `app.providers.manager._cache_bars_to_db` issued individual `SELECT` queries in a row-by-row loop for every single candle, multiplying network roundtrips.

---

## 1. Measured Neon Resource Consumption

Data extracted directly from the Neon Cloud Control Plane API for project `crimson-mountain-88821720` (branch `br-calm-lab-a1yqdtpl`):

| Resource Metric | Measured Value | Neon Free Quota | % of Quota | Status |
|---|---|---|---|---|
| **Public Data Egress** | **6.31 GB** (6,313,725,087 bytes) | 5.00 GB / month | **126.3%** | 🔴 **EXCEEDED (Breached)** |
| **Compute Active Time** | **92.96 hours** (334,648 s) | Dynamic | N/A | ⚠️ **Excessive** |
| **Compute Consumption** | **25.94 CU-hours** (93,383 s) | 100 CU-hours / month | 25.9% (8 days) | 🟡 **Burn Rate High** |
| **Branch Logical Storage** | **191.65 MB** (200,957,952 bytes) | 1.00 GB (1,024 MB) | 18.7% | 🟢 **Within Limits** |
| **Endpoint Suspend Timeout** | **`0 seconds`** (Auto-suspend disabled) | Recommended: 300s | N/A | 🔴 **Misconfigured** |
| **Endpoint Compute Sizing** | Min: 0.25 CU, Max: 2.0 CU | 0.25 CU default | N/A | 🟢 Scaled appropriately |
| **Endpoint State** | `suspended` (since 2026-11-09T08:49:47Z) | `ready` / `idle` | N/A | 🔴 **Blocked by Quota** |

*Note: The quota reset date for this Neon project is `2026-12-01T00:00:00Z`.*

---

## 2. Table-by-Table Storage & Row Counts

Based on verified point-in-time snapshots (`data/backups/neon_pg_backup_*.json`) and Alembic schema inspection:

| Table Name | Approx. Row Count (Nov 6) | Growth Trend (3-Day Delta) | Primary Data Carried | Egress / Storage Impact |
|---|---|---|---|---|
| `decision_stage_results` | **16,317** | +11,151 rows (+215%) | Verbose stage checks JSON, rejection reasons | 🔴 HIGH (Rapid data inflation) |
| `news_events` | **5,200** | +3,726 rows (+252%) | Raw article JSON (`raw_json`), full summaries | 🔴 HIGH (Heavy JSON payloads) |
| `decision_audits` | **2,331** | +1,593 rows (+215%) | Trade evaluation parameters, regime state | 🟡 MEDIUM |
| `job_runs` | **~23,000+** (est.) | ~2,880 rows / day | Cron execution logs, status, error trace | 🔴 HIGH (Continuous write churn) |
| `bars_daily` | Cached universe | Daily incremental | Split-adjusted & unadjusted OHLCV bars | 🟡 MEDIUM (N+1 query load) |
| `signals` | **108** | Stable (+2 rows) | VCP/Breakout signal records, setup reasons | 🟢 LOW |
| `alerts` | **3** | Stable (+2 rows) | System and trigger notifications | 🟢 LOW |
| `positions` | **1** | Stable | Active paper/manual positions | 🟢 LOW |
| `fills` | **2** | Stable | Order execution fills | 🟢 LOW |
| `journal` | **1** | Stable | Trade journal logs and reflections | 🟢 LOW |
| `news_source_state` | **4** | Stable | Feed health and ETag checkpoints | 🟢 LOW |
| `earnings_filings` | **1** | Stable | Corporate earnings metadata | 🟢 LOW |
| `settings_kv` | **1** | Stable | System operational settings | 🟢 LOW |
| `instruments` | Universe Master | Synced weekly | Instrument tokens and sector tags | 🟢 LOW |

### Storage Growth Analysis from Historical Snapshots:
- **Nov 3, 2026**: `neon_pg_backup_20261103_182900.json` = **9.63 MB**
- **Nov 4, 2026**: `neon_pg_backup_20261104_182900.json` = **11.49 MB**
- **Nov 5, 2026**: `neon_pg_backup_20261105_182900.json` = **18.81 MB**
- **Nov 6, 2026**: `neon_pg_backup_20261106_182900.json` = **28.41 MB**
- **Nov 9, 2026**: Neon logical branch size reached **191.65 MB**.

Without automated retention pruning, storage growth was approximately **20-30 MB per day**, projecting to reach the 1 GB Free Tier limit in under 30 days.

---

## 3. Database Architecture & Connection Review

### 3.1 Connection Configuration (`backend/app/db.py`)
```python
engine_kwargs = {
    "poolclass": QueuePool,
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30.0,
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
```
**Issues identified**:
- **Oversized Client Pool for Serverless**: `QueuePool(pool_size=10, max_overflow=20)` creates up to 30 persistent connections per backend process. In a single-instance Render setup connecting through Neon PgBouncer (`-pooler`), a client pool this large is unnecessary and holds connection slots open.
- **PgBouncer Pooling Port**: The application connects to `ep-jolly-dust-a1lsoqu5-pooler.ap-southeast-1.aws.neon.tech` (transaction pooling port 5432). However, maintaining persistent connections with `pool_recycle=300` combined with frequent queries prevents Neon compute from scaling down.

### 3.2 Neon Compute Configuration (`crimson-mountain-88821720`)
- **`suspend_timeout_seconds: 0`**: Auto-suspend was completely disabled. Once woken, the compute node ran perpetually, continuously accruing active compute time.
- Standard Neon Free default is `300 seconds` (5 minutes of inactivity before scale-to-zero).

---

## 4. Workload & Query Pattern Audit

### 4.1 Background Schedulers (`backend/app/scheduler/jobs.py`)
1. **Unconstrained 24/7 Monitoring**:
   - `live_monitor_IN`: Interval 60s (previously 30s)
   - `live_monitor_US`: Interval 60s (previously 30s)
   - Both jobs run 24 hours a day, 7 days a week, regardless of whether exchanges (NSE/BSE, NYSE/NASDAQ) are open.
   - At 60s intervals, 2,880 job runs execute per day.
2. **Every Execution Writes to Database**:
   - The decorator `log_job_execution` creates a `JobRun` record with status `RUNNING`, performs the job, and updates `JobRun` to `SUCCESS` or `FAILED`.
   - Result: Over 5,700 database transactions per day exclusively to log scheduler heartbeats.
   - Result: Compute never reaches 5 minutes of idle time.
3. **High-Frequency Media & RSS Ingestion**:
   - `news_media_poll` runs every 5 minutes.
   - `kite_sync` runs every 5 minutes.
   - `news_poll_P0` runs every 15 minutes.
   - `news_poll_P1` runs every 30 minutes.

### 4.2 Query Patterns & Inefficiencies

1. **N+1 Query Loop in `_cache_bars_to_db` (`backend/app/providers/manager.py:181-192`)**:
   ```python
   for _, row in df.iterrows():
       existing = (
           db.query(DailyBar)
           .filter(DailyBar.symbol == symbol, DailyBar.date == row_date)
           .first()
       )
   ```
   *Impact*: Ingesting 300 daily bars for a single stock runs 300 sequential `SELECT` queries across the network to Neon, followed by 300 single-row inserts/updates. For 50 stocks, this causes 15,000 distinct roundtrips, generating significant egress traffic and query latency.

2. **Verbose JSON Ingestion in `DecisionAudit` and `DecisionStageResult` (`backend/app/engine/pipeline.py:655-663`)**:
   - Every stock evaluation stores full `checks_json` and `rejection_reasons_json` across 7 pipeline stages.
   - 2,331 audits generated 16,317 stage rows, consuming the vast majority of database storage.

3. **Frontend Polling Frequencies**:
   - `MarketPulseWidget.tsx:56`: Polls `/api/quotes` every **2.5 seconds**.
   - `WatchlistPage.tsx:398`: Polls `/api/watchlists` items every **2.5 seconds**.
   - `Sidebar.tsx:67`: Polls pinned quotes every **4.0 seconds**.
   - `CandleChart.tsx:294`: Polls intraday quotes every **2.0 seconds**.
   - While quote fetching relies on in-memory provider caching, any fallback to DB cache (`get_daily_bars`) is multiplied by rapid frontend polling.

---

## 5. Root Cause Classification & Severity

| Severity | Root Cause | Evidence | Impact |
|---|---|---|---|
| 🔴 **CRITICAL** | **Endpoint Auto-Suspend Disabled** (`suspend_timeout_seconds: 0`) | Neon API response on project `crimson-mountain-88821720` | Compute remained continuously active (334,648s), exhausting monthly compute allowances and generating steady egress. |
| 🔴 **CRITICAL** | **Scheduler Off-Market 24/7 Execution** | `backend/app/scheduler/jobs.py:284-295` | `live_monitor` queries `Signal` and `Position` and writes to `JobRun` every 60s, preventing Neon compute from ever idling down. |
| 🔴 **CRITICAL** | **Data Transfer Egress Breach** | 6.31 GB measured vs 5.00 GB free limit | Triggered HTTP 402 quota lock from Neon control plane, taking entire database offline. |
| 🟡 **HIGH** | **Unbounded Table Growth & No Retention Pruning** | `decision_stage_results` (16k rows), `news_events` (5.2k rows), `job_runs` | Grew database size from 9 MB to 200 MB in 8 days; would breach 1 GB storage limit within a month. |
| 🟡 **HIGH** | **N+1 Query Pattern in Daily Bar Ingestion** | `backend/app/providers/manager.py:189` | Row-by-row iteration generates hundreds of queries per ticker during backfill or cache updates. |
| 🟡 **MEDIUM** | **Heavy `raw_json` Storage in `NewsEvent`** | `backend/app/models.py:284` | Storing uncompressed external JSON payloads bloats table size and backup snapshots. |
| 🟢 **LOW** | **SQLAlchemy Connection Pool Sizing** | `backend/app/db.py:33` | `pool_size=10, max_overflow=20` is slightly oversized for a single-dyno Render app on serverless Postgres. |

---

## 6. Conclusion & Recommendation

The database went down strictly because **data egress (6.31 GB > 5.00 GB)** breached the Neon Free quota due to auto-suspend being disabled and continuous round-the-clock polling.

To restore and guarantee long-term stability within the Neon Free tier:
1. **Auto-suspend must be set to 300 seconds** (5 minutes).
2. **Scheduler monitoring must only execute during open market hours** (09:15-15:30 IST for NSE; 09:30-16:00 EST for US).
3. **`JobRun` writes must be throttled or purged** on a 7-day rolling window.
4. **`decision_stage_results` and `decision_audits` must have automated retention policies** (e.g. 14-day retention).
5. **A fresh Neon Free project must be provisioned** (or current quota reset) to regain active database connectivity, since the current project is suspended until the next monthly billing cycle.
