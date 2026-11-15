# Neon Free Database Migration Report: Quota Recovery & Cutover Guide

**Document Version**: 1.1 (Target Migration Executed & Verified)  
**Date**: November 14, 2026  
**Target Environment**: Neon Serverless PostgreSQL (Free Tier)  
**Target Project Name**: `Swing-trading-v2` (`ancient-morning-39123986`)  
**Status**: MIGRATION EXECUTED & VERIFIED ON NEW PROJECT — READY FOR RENDER CUTOVER  
*(All non-negotiable constraints enforced: Manual-only execution, zero strategy logic changes, zero deletion/pruning of research evidence, old database untouched)*

---

## 1. Executive Summary & Cutover Readiness

The existing swing-trading platform database on Neon Free (`swing-trading`, project `crimson-mountain-88821720`) was suspended on November 9, 2026, due to exceeding the 5.0 GB public data egress quota (HTTP 402: Payment Required). 

To restore production functionality without incurring paid services or waiting for the monthly billing cycle reset:
1. **Target Project Connected**: Successfully connected to new Neon Free project `Swing-trading-v2` (`ancient-morning-39123986`).
2. **Schema Generation & Application**: Applied Alembic migrations 001 through `005_universe_watchlists_funds` (latest head), creating all 30 database tables with 100% schema alignment against SQLAlchemy `Base.metadata`.
3. **Data Restoration**: Restored all **23,969 operational records** from verified backup snapshot `data/backups/neon_pg_backup_20261106_182900.json` (SHA-256: `76fd605b94ed554e7ead7c3949d81f5eab1e6b64d6f54eff539b49457ecae9da`) using native bulk upserts with zero data loss.
4. **Missing Data Reconstruction**: Reconstructed **2,745 active instruments** into the target database via scrip master synchronization.
5. **Post-Restoration Assertions Verified**: Verified representative records directly on the live target Neon instance (TCS position, TCS journal entry with net PnL ₹1,836.26, 2 fills, 2,331 decision audits, 16,317 stage results, 5,200 news events).
6. **Day-1 Quota Protection**: Deployed wire-level telemetry, in-memory caching, market-hours scheduler guards, background-tab polling pauses, and relaxed polling intervals to keep monthly egress under 1.5 GB and CU-hours under 25.

**Production Cutover Status**: Target database is fully migrated and healthy. Ready for user to update `DATABASE_URL` in Render.

---

## 2. Target Neon Free Project Configuration Guidelines

When creating the new project in the [Neon Console](https://console.neon.tech/), use the following specifications:

| Parameter | Recommended Setting | Purpose & Constraint |
|---|---|---|
| **Project Name** | `swing-trading-v2` | Clearly isolates the new database from the suspended legacy instance |
| **Region** | `aws-ap-southeast-1` (Singapore) | Minimizes latency to Indian stock exchanges (NSE/BSE) and Render backend |
| **PostgreSQL Version** | `16` or `18` | Matches tested PostgreSQL compatibility |
| **Compute Sizing** | Min: 0.25 CU, Max: 1.0 CU | Minimal allocation; 0.25 CU is optimal for single-user swing trading |
| **Autosuspend Delay** | **`300 seconds` (5 minutes)** | **MANDATORY**: Enables scale-to-zero compute shutdown when markets are closed |
| **Free Quotas** | 1.0 GB Storage, 100 CU-hr, 5.0 GB Transfer | Hard limits strictly respected by application-level guardrails |

### Connection String Separation:
Neon provides two connection strings:
1. **Pooled Connection (`-pooler`)**:
   - Format: `postgresql://user:pass@ep-xyz-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
   - **Usage**: Used for runtime application operations (`DATABASE_URL` in Render). PgBouncer recycles connections efficiently and prevents connection spikes.
2. **Direct Unpooled Connection (Without `-pooler`)**:
   - Format: `postgresql://user:pass@ep-xyz.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
   - **Usage**: Required for DDL schema migrations (`MIGRATION_DATABASE_URL` and `alembic upgrade head`). `alembic/env.py` and `migrate_new_db.py` automatically strip `-pooler` if passed.

> [!CAUTION]
> **Credential Security**: Never commit database credentials or connection strings to Git, logs, or documentation. Use environment variables exclusively.

---

## 3. Database Migration Inventory (All 30 Tables)

Below is the complete inventory of all 30 SQLAlchemy database tables, primary keys, foreign keys, dependencies, backup status, and recovery paths:

| # | Table Name | Primary Key | Foreign Key Dependencies | Backup Count | Source / Recovery Path |
|---|---|---|---|---|---|
| 1 | `scans` | `id` | None | 0 | Auto-created placeholder for FK integrity (`{38, 39}`); populates on new scans |
| 2 | `signals` | `id` | `scan_id -> scans.id` | 108 | Restored from JSON snapshot (merge upsert) |
| 3 | `positions` | `id` | `signal_id -> signals.id` | 1 | Restored from JSON snapshot (merge upsert) |
| 4 | `fills` | `id` | `position_id -> positions.id` | 2 | Restored from JSON snapshot (merge upsert) |
| 5 | `journal` | `id` | `position_id -> positions.id` | 1 | Restored from JSON snapshot (merge upsert) |
| 6 | `alerts` | `id` | None | 3 | Restored from JSON snapshot (merge upsert) |
| 7 | `settings_kv` | `key` | None | 1 | Restored from JSON snapshot (merge upsert) |
| 8 | `news_source_state` | `source_name` | None | 4 | Restored from JSON snapshot (merge upsert) |
| 9 | `earnings_filings` | `id` | None | 1 | Restored from JSON snapshot (merge upsert) |
| 10 | `decision_audits` | `id` | None | 2,331 | Restored from JSON snapshot (parent table) |
| 11 | `decision_stage_results` | `id` | `audit_id -> decision_audits.id` | 16,317 | Restored from JSON snapshot (child table) |
| 12 | `news_events` | `id` | None | 5,200 | Restored from JSON snapshot (merge upsert) |
| 13 | `instruments` | `id` (or symbol) | None | 0 | Reconstructed from Angel One scrip master (2,745 equities) |
| 14 | `bars_daily` | `(symbol, date)` | None | 0 | Reconstructed on-demand; research reads from local parquet |
| 15 | `job_runs` | `id` | None | 0 | Ephemeral runtime logs; starts clean on startup |
| 16 | `custom_price_alerts` | `id` | None | 0 | User-configured; restored from UI seed |
| 17 | `watchlists` | `id` | None | 0 | Default system watchlist seeded on startup |
| 18 | `watchlist_items` | `id` | `watchlist_id -> watchlists.id` | 0 | Default system watchlist items seeded on startup |
| 19 | `fundamental_snapshots` | `id` | None | 0 | Cached on demand via fundamentals engine |
| 20 | `chart_overlays` | `id` | None | 0 | Re-saved on chart interaction |
| 21 | `system_events` | `id` | None | 0 | Runtime audit log; starts clean |
| 22 | `orders` | `id` | None | 0 | Manual paper trading creates orders as executed |
| 23 | `market_breadth_daily` | `(market, date)`| None | 0 | Re-computed during daily scan |
| 24 | `sector_performance_daily`| `(sector, date)`| None | 0 | Re-computed during daily scan |
| 25 | `backtest_runs` | `id` | None | 0 | Preserved in local artifacts; runs on demand |
| 26 | `backtest_trades` | `id` | `run_id -> backtest_runs.id` | 0 | Preserved in local artifacts; runs on demand |
| 27 | `backtest_daily_equity` | `id` | `run_id -> backtest_runs.id` | 0 | Preserved in local artifacts; runs on demand |
| 28 | `paper_accounts` | `id` | None | 0 | Initialized with default paper balance |
| 29 | `paper_orders` | `id` | None | 0 | Generated during paper execution |
| 30 | `broker_sessions` | `id` | None | 0 | Session restored via OAuth login |

**Total Records Restored from Backup**: **23,969 records**  
**Total Instruments Reconstructed**: **2,745 records**

---

## 4. Schema Migration Results & Gap Resolution

### Alembic Migration Sequence:
1. `001_initial_neon_pg`: Base tables (`instruments`, `bars_daily`, `scans`, `signals`, `positions`, `fills`, `journal`, `alerts`, `job_runs`, `settings_kv`).
2. `002_live_reliability_and_alerts`: Decision audit architecture (`decision_audits`, `decision_stage_results`, `custom_price_alerts`, `news_source_state`, `earnings_filings`, `news_events`).
3. `003_chart_overlays`: Interactive chart overlay persistence.
4. `004_historical_ingestion`: Ingestion telemetry, tracking, and chunking tables.
5. `005_universe_coverage_watchlists_and_fundamentals` *(NEW)*:
   - Added tables: `fundamental_snapshots`, `watchlists`, `watchlist_items`.
   - Added columns to `instruments`: `series`, `universe_tier`, `is_higher_risk`, `status`, `status_reason`, `last_scanned_at`, `avg_turnover_20d`, `last_price`, `atr_pct`.
   - Added column to `signals`: `sources_json`.

### Schema Gap Resolution:
Prior to this migration, models `fundamental_snapshots`, `watchlists`, and `watchlist_items`, as well as 9 universe columns on `instruments`, existed in SQLAlchemy ORM models but lacked Alembic migrations. Attempting to run on a new database would have caused missing table/column runtime exceptions. 

Migration `005` resolved this gap completely. Schema comparison between `Base.metadata.tables` and Alembic generated DDL confirmed **0 discrepancies**.

---

## 5. Backup Integrity & Restoration Metrics

### 5.1 Snapshot Verification
- **File**: `data/backups/neon_pg_backup_20261106_182900.json`
- **File Size**: 29,793,823 bytes (~28.4 MB)
- **SHA-256 Checksum**: `76fd605b94ed554e7ead7c3949d81f5eab1e6b64d6f54eff539b49457ecae9da`
- **Validation Status**: MATCH (100% verified)

### 5.2 Foreign-Key Dependency Handling
In the backup snapshot, `signals` contained 108 records referencing `scan_id in (38, 39)`. However, `scans` table records were not included in the original backup snapshot. In PostgreSQL, restoring child foreign keys without parent records results in a `ForeignKeyViolation`.

`restore_database_backup()` was enhanced to:
1. Inspect foreign-key dependencies dynamically before inserting records.
2. Pre-create synthetic placeholder `Scan` headers (`id=38`, `id=39`) with scan time matching the backup timestamp.
3. Order table restorations strictly by FK topology:
   - `decision_audits` -> `decision_stage_results`
   - `signals` -> `positions` -> `fills` & `journal`
   - Independent tables: `alerts`, `news_events`, `settings_kv`, `news_source_state`, `earnings_filings`
4. Apply SQL merge upsert semantics (`ON CONFLICT DO UPDATE` or key lookup) with explicit type-casting for dates, ISO datetimes, floats, booleans, and JSON dictionaries.

### 5.3 Per-Table Restoration Results

| Table | Status | Records in JSON | Inserted / Upserted | Failed |
|---|---|---|---|---|
| `scans` (placeholders) | SUCCESS | 0 | 2 | 0 |
| `signals` | SUCCESS | 108 | 108 | 0 |
| `positions` | SUCCESS | 1 | 1 | 0 |
| `fills` | SUCCESS | 2 | 2 | 0 |
| `journal` | SUCCESS | 1 | 1 | 0 |
| `alerts` | SUCCESS | 3 | 3 | 0 |
| `settings_kv` | SUCCESS | 1 | 1 | 0 |
| `news_source_state` | SUCCESS | 4 | 4 | 0 |
| `earnings_filings` | SUCCESS | 1 | 1 | 0 |
| `decision_audits` | SUCCESS | 2,331 | 2,331 | 0 |
| `decision_stage_results` | SUCCESS | 16,317 | 16,317 | 0 |
| `news_events` | SUCCESS | 5,200 | 5,200 | 0 |
| **TOTAL** | **SUCCESS** | **23,969** | **23,971** | **0** |

### 5.4 Representative State Verification
Post-restoration verification confirmed the exact integrity of verified historical state:
- **TCS Position**: Restored 1 open position for `TCS.NS`.
- **TCS Journal Entry**: Restored journal entry for `TCS.NS` with entry price 3840.0, exit price 3915.0, gross PnL 2000.0, and net PnL **1836.26** (reflecting DP and broker transaction charges).
- **Execution Fills**: Restored 2 fill records for `TCS.NS` matching execution history.
- **Audit Trails**: Restored 2,331 decision audits and 16,317 stage results, ensuring full historical trade rationale and score visibility.
- **Market Intelligence**: Restored 5,200 categorized news events.

---

## 6. Missing Data Reconstruction Procedure

### 6.1 Instruments Master Reconstruction
The JSON backup contained 0 records for `instruments`. 
- **Method**: Implemented `universe_manager.refresh_instrument_master(market="IN", db=db)`.
- **Source**: `data/cache/angelone/instrument_master.json` containing verified scrip tokens for Indian equities.
- **Result**: Successfully parsed and inserted **2,745 equity instruments** into the `instruments` table with NSE token mapping, tick size (0.05), lot size (1), and active status.
- **Validation**: 0 duplicate symbol violations; all active universe symbols populated.

### 6.2 Daily Bars (`bars_daily`)
- **Source**: Local parquet research snapshot `data/research/research_snapshot_20261106.parquet` (141,040 rows, 114 universe symbols from 2021-07-19 to 2026-11-05).
- **Strategy**: Research workflows and backtests read directly from local parquet via `RESEARCH_DATA_SOURCE=parquet` in `backend/app/engine/research_loader.py`. This provides sub-millisecond query performance while generating **0 bytes of database egress**.
- **Live Operation**: Live daily bars are cached in `bars_daily` on-demand during regular operational scans.

### 6.3 Data That Cannot Be Recovered
- **`job_runs`**: Historical background task execution logs were not included in the JSON backup. These are ephemeral runtime telemetry records; the background scheduler initializes clean job history on first startup with zero operational impact.

---

## 7. Day-1 Egress & Compute Guardrails

To prevent the new Neon Free project from encountering quota exhaustion, the following optimizations are permanently deployed:

1. **Autosuspend Enforcement**:
   - Compute endpoint configured to `suspend_timeout_seconds: 300` (5 minutes).
2. **Scheduler Off-Market Gating**:
   - `backend/app/scheduler/jobs.py` now calls exchange calendars (`is_market_open("IN")` and `is_market_open("US")`) **before** opening a database connection or running queries.
   - Scheduler monitor ticks are silenced outside market hours, allowing Neon compute to sleep.
3. **In-Memory Caching & HTTP 304 ETags**:
   - `backend/app/cache.py` caches heavy database queries (regime, daily bars, universe) with TTL and single-flight request coalescing.
   - API routes return `ETag` headers; frontend requests with `If-None-Match` receive `304 Not Modified`, saving egress.
4. **Kite Session DB Call Elimination**:
   - `kite_provider.is_authenticated()` no longer queries the database on every tick when unauthenticated.
5. **Frontend Polling Throttling & Tab Visibility**:
   - Background tabs suspend all polling via `document.visibilityState`.
   - Polling frequencies lengthened: regime (60s), plan (60s), market pulse (60s), watchlists/charts (10-15s).
6. **Telemetry & Quota Alerts**:
   - `backend/app/telemetry.py` intercepts SQLAlchemy queries, tracking wire bytes, row counts, and HTTP responses, logging daily consumption and alerting when 80% quota is approached.

---

## 8. Deployment and Rollback Procedures (Render Backend)

### 8.1 Production Deployment Steps

Once the new Neon database has been populated using `migrate_new_db.py`:

1. **Retrieve Connection String**:
   - From the Neon Console for `swing-trading-v2`, copy the **pooled connection string** (ends with `-pooler.ap-southeast-1.aws.neon.tech`).
2. **Update Render Environment Variables**:
   - Log in to [Render Dashboard](https://dashboard.render.com/).
   - Navigate to the backend service (`algo-trading-backend`).
   - Open **Environment**.
   - Update `DATABASE_URL` with the new pooled connection string:
     ```env
     DATABASE_URL=postgresql://user:password@ep-xyz-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
     ```
   - Click **Save Changes**. Render will automatically trigger a zero-downtime deployment.
3. **Post-Deployment Verification**:
   - Check Render logs for clean startup:
     ```
     [INFO] Database engine initialized with connection pooling
     [INFO] Egress telemetry hook registered
     [INFO] Application startup complete.
     ```
   - Hit the health check endpoint:
     ```bash
     curl -i https://algo-trading-backend.onrender.com/api/health
     ```
     Verify HTTP 200 with status `ok` and database status `connected`.
   - Open the frontend web app and verify:
     - Dashboard loads TCS position (1 position).
     - Trade Plan displays historical signals (108 signals).
     - Journal reflects completed TCS trade with ₹1,836.26 net PnL.
     - System Telemetry page displays query egress tracking.

### 8.2 Rollback Procedure

If any issue arises during cutover:
1. In the Render Dashboard, revert `DATABASE_URL` to the previous connection string (or backup SQLite instance).
2. The legacy Neon database (`swing-trading`) has remained completely untouched throughout this process.
3. Once the quota resets on December 1, 2026, the old database will resume normal operation if needed.

---

## 9. Verification & Cutover Checklist

- [x] Schema migration `005_universe_watchlists_funds` applied to target project `ancient-morning-39123986`.
- [x] JSON backup SHA-256 checksum verified (`76fd605b...`).
- [x] Dynamic foreign-key placeholder handling executed for `signals.scan_id`.
- [x] Transactional restoration routine executed on all 23,969 operational records on `ancient-morning-39123986`.
- [x] Instrument master reconstruction executed (2,745 equities loaded on target DB).
- [x] Representative records verified on live target database (TCS position, TCS journal net PnL ₹1,836.26, 2 fills, 2,331 audits, 16,317 stage results, 5,200 news events).
- [x] Parquet research loader active for historical bars with zero egress.
- [x] Market-hours scheduler gating implemented for Asia/Kolkata and America/New_York.
- [x] Frontend polling throttled and tab visibility pause added.
- [x] Egress telemetry and wire-size estimation active.
- [x] All 194 backend unit and integration tests passing.
- [x] Frontend builds cleanly with zero TypeScript errors.
- [ ] **Ready for User**: Update Render `DATABASE_URL` with pooled connection string.
