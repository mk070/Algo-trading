# Neon Database Optimization Plan

**Target System**: Personal Swing-Trading & Paper-Trading Platform  
**Target Environment**: Neon Serverless PostgreSQL (Free Tier: 1 GB Storage, 100 CU-Hours/mo, 5 GB Egress/mo)  
**Status**: DRAFT / RECOMMENDATION ONLY (No changes applied without user approval)  

---

## 1. Objectives & Guardrails

### 1.1 Objectives
1. **Prevent Quota Exhaustion**: Target compute consumption strictly below 100 CU-hours/month, public egress below 5.0 GB/month, and storage below 1.0 GB.
2. **Enable Scale-to-Zero**: Allow the Neon compute endpoint to automatically suspend after 5 minutes of inactivity during market-closed hours (nights, weekends, holidays).
3. **Eliminate Unnecessary Database Writes & Churn**: Stop storing high-frequency scheduler heartbeats in the database and implement retention/archival policies for ephemeral logs.
4. **Preserve System Integrity**: Zero disruption to trading strategies, indicators, signal calculations, paper-trading logic, historical bars, or user positions.

> [!CAUTION]
> **No Deletion Authorization**: Per project instructions, **no deletion or modification of existing records is authorized** in this phase. All retention suggestions in this document are design proposals requiring explicit user authorization before implementation.

---

## 2. Optimization Areas & Proposals

### 2.1 Scale-to-Zero & Compute Idle Preservation (Priority: CRITICAL)

#### Problem:
Neon's autosuspend was configured to `suspend_timeout_seconds: 0`, meaning compute remained hot 24/7. In addition, background jobs ran every 60 seconds around the clock, continuously querying the database and resetting any potential idle timer.

#### Proposed Action:
1. **Configure Neon Suspend Timeout**:
   Set `suspend_timeout_seconds = 300` (5 minutes) on the Neon endpoint settings.
2. **Standardized Market-Hours Gating**:
   In `backend/app/scheduler/jobs.py`, gate intraday monitoring jobs so they execute only during active exchange sessions:
   - **Indian Market (`live_monitor_IN`)**:
     - Timezone: `ZoneInfo("Asia/Kolkata")`.
     - Normal Trading Window: Monday through Friday, 09:15 to 15:30 IST.
     - Holiday & Special Sessions: Evaluated using `app.engine.calendars.is_exchange_holiday("IN", today)`. Support special trading sessions (e.g., Muhurat trading) via calendar override.
   - **US Market (`live_monitor_US`)**:
     - Timezone: `ZoneInfo("America/New_York")`.
     - Normal Trading Window: Monday through Friday, 09:30 to 16:00 EST/EDT.
     - Holiday Sessions: Evaluated using US exchange holiday calendar (`is_exchange_holiday("US", today)`).
3. **Crucial Guard Placement (Before Database Access)**:
   - The market-hours check **must execute before opening a database session** or entering `log_job_execution`.
   - If checked inside `job_live_monitor_in(db)`, the database connection and `JobRun` insert have *already occurred*, resetting the idle timer.
   - The wrapper or trigger check must exit immediately if off-market without creating a `SessionLocal()`:
     ```python
     def is_market_open(market: str, dt: datetime.datetime) -> bool:
         # Pure in-memory time and calendar check; zero DB queries
         ...
     ```
4. **Preservation of Core Research & Batch Jobs**:
   Post-market and scheduled batch routines are explicitly **exempt** from intraday market-hours gating and must continue on their designated schedules:
   - `daily_paper_trading`: Monday–Friday 16:00 IST (`Asia/Kolkata`).
   - `eod_scan_IN`: Monday–Friday 16:30 IST (`Asia/Kolkata`).
   - `weekly_paper_reporting`: Friday 17:00 IST (`Asia/Kolkata`).
   - `eod_scan_US`: Monday–Friday 21:45 IST / 16:15 EST (`America/New_York`).
   - `db_backup`: Daily at 23:59 IST (`Asia/Kolkata`).

---

### 2.2 Scheduler Logging & `JobRun` Write Reduction (Priority: CRITICAL)

#### Problem:
The `log_job_execution` wrapper in `backend/app/scheduler/jobs.py` opens a new database session, inserts a row into `job_runs`, commits, and then updates the row upon completion for every single job execution. For `live_monitor` running every 60 seconds, this creates ~5,700 database transactions per day, churning the database and generating constant network egress.

#### Proposed Action:
1. **Separation of Operational Heartbeats vs Research Runs**:
   - For high-frequency monitors (`live_monitor_IN`, `live_monitor_US`), write to `JobRun` **only on failure or state change**, maintaining their latest execution heartbeat in an in-memory dictionary.
   - Preserve full database audit logging for discrete critical workflows: `eod_scan_IN`, `eod_scan_US`, `daily_paper_trading`, `weekly_paper_reporting`, `db_backup`.
2. **Automated Operational Log Retention**:
   - `job_runs` contains ephemeral scheduler runtime logs (no research value).
   - Propose an automated retention job purging `job_runs` older than 7 days:
     ```sql
     DELETE FROM job_runs WHERE started_at < NOW() - INTERVAL '7 days';
     ```

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

---

### 2.4 Data Retention & Archival Policies (Priority: HIGH)

#### Problem:
`decision_stage_results` (16,317 rows) and `news_events` (5,200 rows) represent ~90% of the database storage and backup snapshot size. These tables grow without bound because there is no cleanup mechanism.

#### Proposed Policy & Architectural Boundaries:
1. **Foreign-Key Hierarchy Consideration**:
   - `decision_stage_results.audit_id` is a Foreign Key referencing `decision_audits.id`.
   - Any archival or pruning must respect referential integrity: child `decision_stage_results` rows must be handled in lockstep with parent `decision_audits` rows.
2. **Research Evidence Preservation vs Raw Telemetry**:
   - `decision_audits` records trade decisions, setup classifications, and regime states, serving as quantitative audit evidence. They should **not be deleted outright**.
   - Instead, propose a dual-tier policy:
     - Keep active 30-day window in primary PostgreSQL.
     - For records older than 30 days, export/archive to cold compressed JSON/CSV files in `data/research_archive/` before removal from active Neon storage.
3. **`news_events` Payload Sanitization**:
   - `raw_json` contains bulky raw third-party API payloads.
   - Propose nullifying `raw_json` after 7 days while preserving structured metadata (`title`, `published_at`, `severity`, `summary`, `materiality`, `price_change_day_pct`), which reclaims >80% of storage without losing historical sentiment context.

---

### 2.5 Connection Pool Tuning Based on Actual Concurrency (Priority: MEDIUM)

#### Concurrency Architecture:
Inspection of `render.yaml` confirms that Render runs a single Uvicorn process (`workers=1`) on a 0.1 vCPU / 512 MB dyno. Fast API processes web requests asynchronously, while APScheduler executes jobs on background threads. Peak concurrent database queries are **1 to 2 concurrent connections**.

#### Proposed Action:
Tune SQLAlchemy `engine_kwargs` to match actual concurrency rather than arbitrary defaults:
```python
engine_kwargs = {
    "poolclass": QueuePool,
    "pool_size": 3,           # Accommodates 1 web worker + 1-2 scheduler threads
    "max_overflow": 2,        # Small overflow headroom for brief bursts
    "pool_timeout": 20.0,
    "pool_recycle": 180,      # Recycle every 3 minutes to handle serverless timeouts
    "pool_pre_ping": True,    # Required for graceful reconnect after Neon scale-to-zero
    "echo": False,
}
```
*Rationale*: Sized precisely to peak concurrency (max 5 simultaneous connections), avoiding connection slot saturation on Neon's PgBouncer transaction pooler (`-pooler`).

---

### 2.6 Frontend Polling Optimization (Priority: MEDIUM)

#### Problem:
Frontend components (`MarketPulseWidget`, `WatchlistPage`, `Sidebar`) poll the API at 2.0s to 4.0s intervals via `setInterval`. When browser tabs are left open in the background, requests continue indefinitely.

#### Proposed Action:
1. **Tab Visibility Guards**:
   Wrap polling intervals with `document.visibilityState === 'visible'` checks to pause polling when tabs are minimized or hidden.
2. **Off-Market Polling Backoff**:
   When markets are closed, back off UI polling intervals from 2.5s to 30s or 60s.

---

## 3. Projected Resource Targets & Measurements Needed

### 3.1 Target Models (Engineering Estimates, Not Measured Results)

| Resource Metric | Current Extrapolated Monthly (8-Day Rate) | Proposed Monthly Target Model | Neon Free Allowance | Target Headroom |
|---|---|---|---|---|
| **Monthly Compute** | ~97.3 CU-hours (unconstrained) | **~15 - 25 CU-hours** | 100 CU-hours | **75% Headroom** |
| **Public Data Egress** | ~23.7 GB (unconstrained) | **~0.8 - 1.5 GB** | 5.00 GB | **70% Headroom** |
| **Database Storage** | ~720 MB (unconstrained) | **~120 - 200 MB (Capped)** | 1,024 MB (1 GB) | **80% Headroom** |

> [!WARNING]
> The target numbers above (15–25 CU-hours, 0.8–1.5 GB egress) are **theoretical engineering target models**, NOT measured savings. They assume successful implementation of auto-suspend, off-market gating, and N+1 query elimination.

### 3.2 Measurements Still Needed to Support Proposed Targets:
Before these targets can be validated as measured facts, the following empirical measurements must be taken on a live test database:
1. **Idle Autosuspend Measurement**: Measure time-to-suspend on a fresh Neon endpoint with `suspend_timeout_seconds: 300` when the backend is idle to verify it suspends within 5 minutes.
2. **Off-Market Egress Profiling**: Measure actual byte transmission over a 24-hour weekend period with scheduler gating enabled vs disabled.
3. **Bulk Upsert Bandwidth Comparison**: Profile network transfer (in KB) of a 300-bar DataFrame ingestion using the existing N+1 loop vs the PostgreSQL bulk upsert.
4. **Browser Visibility Impact**: Measure API request count and downstream DB queries generated by an inactive browser tab over a 1-hour window.
