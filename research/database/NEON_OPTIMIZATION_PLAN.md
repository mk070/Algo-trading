# Neon Database Optimization Plan

**Target System**: Personal Swing-Trading & Paper-Trading Platform  
**Target Environment**: Neon Serverless PostgreSQL (Free Tier: 1 GB Storage, 100 CU-Hours/mo, 5 GB Egress/mo)  
**Status**: Ready for Review (No changes applied without user approval)  

---

## 1. Objectives & Guardrails

### 1.1 Objectives
1. **Prevent Quota Exhaustion**: Ensure compute stays strictly below 100 CU-hours/month, public egress below 5.0 GB/month, and storage below 1.0 GB.
2. **Enable Scale-to-Zero**: Allow the Neon compute endpoint to automatically suspend after 5 minutes of inactivity during market-closed hours (nights, weekends, holidays).
3. **Eliminate Unnecessary Database Writes & Churn**: Stop storing high-frequency scheduler heartbeats in the database and implement automated retention for ephemeral audits.
4. **Preserve System Integrity**: Zero disruption to trading strategies, indicators, signal calculations, paper-trading logic, historical bars, or user positions.

---

## 2. Optimization Areas & Proposals

### 2.1 Scale-to-Zero & Compute Idle Preservation (Priority: CRITICAL)

#### Problem:
Neon's autosuspend was configured to `suspend_timeout_seconds: 0`, meaning compute remained hot 24/7. In addition, background jobs ran every 60 seconds around the clock, continuously querying the database and resetting any potential idle timer.

#### Proposed Action:
1. **Configure Neon Suspend Timeout**:
   Set `suspend_timeout_seconds = 300` (5 minutes) on the Neon endpoint settings.
2. **Implement Market-Hours Gating in Schedulers**:
   In `backend/app/scheduler/jobs.py`, gate `live_monitor_IN` and `live_monitor_US` so they only execute when their respective exchange is active:
   - **Indian Market (NSE/BSE)**: Mon-Fri, 09:15 to 15:30 IST. Outside these hours, do not query the database.
   - **US Market (NYSE/NASDAQ)**: Mon-Fri, 09:30 to 16:00 EST. Outside these hours, do not query the database.
   - **Exchange Holidays**: Skip execution if `is_exchange_holiday(market, today)` evaluates to `True`.

*Impact*: Eliminates ~18 hours of compute activity per weekday and 48 hours every weekend. Reduces active compute hours by **~75%**.

---

### 2.2 Scheduler Logging & `JobRun` Write Reduction (Priority: CRITICAL)

#### Problem:
The `log_job_execution` wrapper in `backend/app/scheduler/jobs.py` opens a new database session, inserts a row into `job_runs`, commits, and then updates the row upon completion for every single job execution. For `live_monitor` running every 60 seconds, this creates ~5,700 database transactions per day, churning the database and generating constant network egress.

#### Proposed Action:
1. **Tiered Job Logging**:
   - For high-frequency jobs (`live_monitor_IN`, `live_monitor_US`), write to `JobRun` **only on status change or failure**, or maintain their latest execution heartbeat in memory (e.g., Python dictionary / in-process state).
   - Continue full audit logging for discrete critical workflows: `eod_scan_IN`, `eod_scan_US`, `daily_paper_trading`, `weekly_paper_reporting`, `db_backup`.
2. **Automated Cleanup Cron**:
   - Add a lightweight daily maintenance task (`job_db_cleanup`) at 23:45 IST that purges `job_runs` older than 7 days:
     ```sql
     DELETE FROM job_runs WHERE started_at < NOW() - INTERVAL '7 days';
     ```

*Impact*: Eliminates over **80,000 unnecessary row writes and commits per month**, dramatically decreasing write I/O and egress traffic.

---

### 2.3 Eliminating N+1 Query Patterns in Market Bar Ingestion (Priority: HIGH)

#### Problem:
`app.providers.manager._cache_bars_to_db` iterates through every candle in a Pandas DataFrame and executes a single-row `SELECT` followed by single-row insert/update:
```python
for _, row in df.iterrows():
    existing = db.query(DailyBar).filter(DailyBar.symbol == symbol, DailyBar.date == row_date).first()
    ...
```
Ingesting 300 days of data for 50 symbols generates 15,000 separate SQL roundtrips across the public internet.

#### Proposed Action:
Replace the row-by-row iteration with PostgreSQL bulk upsert using `sqlalchemy.dialects.postgresql.insert`:
```python
from sqlalchemy.dialects.postgresql import insert

records = [
    {
        "symbol": symbol,
        "date": row_date,
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "adj_close": float(row.get("adj_close", row["close"])),
        "volume": float(row["volume"]),
        "source": str(row.get("source", "unknown")),
        "split_adj_open": float(row.get("split_adj_open", row["open"])),
        "split_adj_high": float(row.get("split_adj_high", row["high"])),
        "split_adj_low": float(row.get("split_adj_low", row["low"])),
        "split_adj_close": float(row.get("split_adj_close", row["close"])),
        "dividend_factor": float(row.get("dividend_factor", 1.0)),
        "is_split_adjusted": bool(row.get("is_split_adjusted", True)),
    }
    for _, row in df.iterrows()
]

if records:
    stmt = insert(DailyBar).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "date"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "adj_close": stmt.excluded.adj_close,
            "volume": stmt.excluded.volume,
            "source": stmt.excluded.source,
            "split_adj_open": stmt.excluded.split_adj_open,
            "split_adj_high": stmt.excluded.split_adj_high,
            "split_adj_low": stmt.excluded.split_adj_low,
            "split_adj_close": stmt.excluded.split_adj_close,
            "dividend_factor": stmt.excluded.dividend_factor,
            "is_split_adjusted": stmt.excluded.is_split_adjusted,
        }
    )
    db.execute(stmt)
    db.commit()
```

*Impact*: Compresses 300 roundtrips per symbol into **1 single batched SQL statement**. Decreases bar ingestion latency by ~95% and cuts network transmission overhead drastically.

---

### 2.4 Data Retention & Table Pruning Policies (Priority: HIGH)

#### Problem:
`decision_stage_results` (16,317 rows) and `news_events` (5,200 rows) represent ~90% of the database storage and backup snapshot size. These tables grow without bound because there is no cleanup mechanism.

#### Proposed Action:
Implement automated retention rules in a scheduled maintenance job:
1. **`decision_stage_results` & `decision_audits`**:
   - Detailed per-stage JSON checks are operational telemetry needed only for recent signal verification.
   - Retention policy: Keep the last 14 days of audits during live trading; purge older records:
     ```sql
     DELETE FROM decision_stage_results 
     WHERE audit_id IN (SELECT id FROM decision_audits WHERE asof_date < NOW() - INTERVAL '14 days');
     
     DELETE FROM decision_audits WHERE asof_date < NOW() - INTERVAL '14 days';
     ```
2. **`news_events`**:
   - `raw_json` contains redundant third-party payload dumps.
   - Nullify `raw_json` after 7 days, and delete news articles older than 30 days:
     ```sql
     UPDATE news_events SET raw_json = NULL WHERE ingested_at < NOW() - INTERVAL '7 days' AND raw_json IS NOT NULL;
     DELETE FROM news_events WHERE published_at < NOW() - INTERVAL '30 days';
     ```
3. **`bars_daily`**:
   - Maintain full history for symbols in active universe (historical indicators depend on 300+ days).
   - Only remove non-universe stale symbols if storage ever approaches 700 MB.

*Impact*: Caps long-term table storage well below **250 MB** indefinitely, ensuring the project never approaches the 1 GB Free tier ceiling.

---

### 2.5 Connection Pool Tuning for Serverless (`backend/app/db.py`) (Priority: MEDIUM)

#### Problem:
`pool_size=10, max_overflow=20` is sized for traditional persistent servers. On serverless Neon behind PgBouncer (`-pooler`), keeping up to 30 idle connections in a single client process is wasteful and can prevent backend instances from shutting down connections cleanly.

#### Proposed Action:
Optimize SQLAlchemy `engine_kwargs`:
```python
engine_kwargs = {
    "poolclass": QueuePool,
    "pool_size": 3,           # Reduced from 10
    "max_overflow": 5,        # Reduced from 20
    "pool_timeout": 20.0,
    "pool_recycle": 180,      # Recycle every 3 minutes
    "pool_pre_ping": True,    # Ensure healthy reconnect after suspend
    "echo": False,
}
```
*Impact*: Reduces peak concurrent connection footprint by ~70%, preventing connection exhaustion errors.

---

### 2.6 Frontend Polling Optimization (Priority: MEDIUM)

#### Problem:
Frontend components (`MarketPulseWidget`, `WatchlistPage`, `Sidebar`) poll the API at 2.0s to 4.0s intervals via `setInterval`. When browser tabs are left open in the background, requests continue indefinitely.

#### Proposed Action:
1. **Visibility-Aware Polling**:
   Add `document.visibilityState === 'visible'` checks to frontend polling timers so polling halts when the user switches tabs or minimizes the browser.
2. **Off-Market Polling Backoff**:
   When markets are closed, back off UI polling intervals from 2.5s to 30s or 60s.

*Impact*: Eliminates millions of unnecessary HTTP requests and downstream database cache queries when the user is not actively watching the screen.

---

## 3. Projected Resource Reduction Summary

| Resource Metric | Current Trajectory (8 Days) | Projected with Optimizations (Monthly) | Free Tier Allowance | Safety Margin |
|---|---|---|---|---|
| **Monthly Compute** | ~95 CU-hours (run-rate ~350 CU-hr) | **~15 - 25 CU-hours** | 100 CU-hours | **75% Headroom** |
| **Public Data Egress** | 6.31 GB (Breached in 8 days) | **~0.8 - 1.5 GB** | 5.00 GB | **70% Headroom** |
| **Database Storage** | 191.65 MB (+30 MB/day) | **~120 - 200 MB (Capped)** | 1,024 MB (1 GB) | **80% Headroom** |
| **Daily DB Transactions** | ~6,500+ writes/day | **< 300 writes/day** | Unlimited | **~95% Reduction** |

---

## 4. Implementation Phasing

1. **Step 1 (Pre-requisite)**: Provision fresh Neon Free project or restore connectivity (Migration Plan).
2. **Step 2**: Configure Neon compute autosuspend (`suspend_timeout_seconds: 300`).
3. **Step 3**: Update `app/db.py` connection pool settings.
4. **Step 4**: Update `app/scheduler/jobs.py` to add market-hours gating and throttle `JobRun` writes.
5. **Step 5**: Update `app/providers/manager.py` bulk upsert for bars.
6. **Step 6**: Add daily retention pruning job (`job_db_cleanup`).
7. **Step 7**: Update frontend components with tab visibility guards.
