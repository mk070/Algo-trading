import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Archive,
  BarChart2,
  CheckCircle2,
  Clock,
  Database,
  FlaskConical,
  KeyRound,
  Layers,
  PauseCircle,
  RefreshCw,
  ShieldAlert,
  ShieldOff,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { AiResearchNotes } from '../components/AiResearchNotes';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StrategyCard {
  id: string;
  name: string;
  status: string;
  buffer_band?: string;
  simulated_capital?: number;
  final_equity?: number | null;
  cagr_pct?: number | null;
  max_drawdown_pct?: number | null;
  sharpe_ratio?: number | null;
  trades_count?: number | null;
  holdings_count?: number | null;
  data_source?: string;
  reason?: string;
}

interface OverviewData {
  disclaimer: string;
  phase_status: string;
  replay_loaded: boolean;
  replay_period?: {
    start_date?: string;
    end_date?: string;
    sessions_count?: number;
    scenario?: string;
  } | null;
  strategies: StrategyCard[];
  benchmark?: {
    cagr_pct?: number | null;
    net_return_pct?: number | null;
    max_drawdown_pct?: number | null;
    data_source?: string;
  };
}

interface AccountState {
  account_id?: string;
  strategy_name?: string;
  initial_capital?: number;
  cash?: number;
  total_equity?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  cumulative_costs?: number;
  cumulative_costs_paid?: number;
  cumulative_slippage?: number;
  holdings?: Record<string, { shares: number; avg_cost: number; invested_cost: number }>;
  last_processed_date?: string;
  trades_count?: number;
  orders_count?: number;
}

interface StrategyDetail {
  strategy_id: string;
  data_source?: string;
  phase_status?: string;
  account: AccountState | null;
  orders_count: number;
  trades_count: number;
  orders_journal: any[];
  trades_journal: any[];
  daily_snapshots: any[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const NA = <span className="text-slate-500 font-mono">—</span>;

function fmt(v: number | null | undefined, decimals = 2, prefix = '') {
  if (v == null) return NA;
  return <span>{prefix}{v.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}</span>;
}

function fmtPct(v: number | null | undefined, positive_green = true) {
  if (v == null) return NA;
  const cls = positive_green ? (v >= 0 ? 'text-emerald-400' : 'text-rose-400') : (v <= 0 ? 'text-emerald-400' : 'text-rose-400');
  const sign = v >= 0 ? '+' : '';
  return <span className={`font-bold font-mono ${cls}`}>{sign}{v.toFixed(2)}%</span>;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ErrorBanner({ message, detail }: { message: string; detail?: string }) {
  return (
    <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-700/50 flex items-start gap-3">
      <XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
      <div>
        <p className="text-sm font-semibold text-rose-300">{message}</p>
        {detail && <p className="text-xs text-rose-400/80 mt-1 font-mono break-all">{detail}</p>}
      </div>
    </div>
  );
}

function AuthErrorBanner({ detail }: { detail?: string }) {
  return (
    <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-700/50 flex items-start gap-3">
      <KeyRound className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
      <div>
        <p className="text-sm font-semibold text-amber-300">Authentication Error</p>
        <p className="text-xs text-amber-400/80 mt-1">
          The API rejected the request with a 401 or 403. Ensure your session token is set in
          Settings. {detail && <span className="font-mono">{detail}</span>}
        </p>
      </div>
    </div>
  );
}

function NoDataBanner({ label, reason }: { label: string; reason?: string }) {
  return (
    <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-start gap-3">
      <Database className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
      <div>
        <p className="text-sm text-slate-400 font-medium">{label}</p>
        {reason && <p className="text-xs text-slate-500 mt-1">{reason}</p>}
      </div>
    </div>
  );
}

function FreezeStatusBanner() {
  return (
    <div className="p-3.5 rounded-xl bg-slate-900/90 border border-amber-800/40 flex items-start gap-3">
      <PauseCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
      <div className="flex-1 text-xs text-slate-300">
        <strong className="text-amber-300 block mb-1">Phase 4 Validation Freeze — Prospective Paper Trading PAUSED</strong>
        No new paper-trading sessions, strategy scheduler, or replay re-execution are running. This
        page displays <strong className="text-white">existing saved results only</strong>: pre-computed
        historical replay data from frozen research artifacts. No live orders have been or will be placed.
      </div>
    </div>
  );
}

function MetricBox({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
      <span className="text-[10px] text-slate-500 block mb-1 uppercase tracking-wider">{label}</span>
      <div className="text-sm font-bold">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Strategy overview card
// ---------------------------------------------------------------------------

function StrategyOverviewCard({
  strat,
  selected,
  onClick,
}: {
  strat: StrategyCard;
  selected: boolean;
  onClick: () => void;
}) {
  const isUnavailable = strat.status === 'UNAVAILABLE';
  const hasData = strat.data_source === 'HISTORICAL_REPLAY';

  return (
    <div
      onClick={isUnavailable ? undefined : onClick}
      className={`rounded-xl p-4 border transition-all ${
        isUnavailable
          ? 'bg-slate-900/50 border-slate-800/60 opacity-70'
          : selected
          ? 'cursor-pointer bg-indigo-950/40 border-indigo-500 shadow-lg ring-1 ring-indigo-500'
          : 'cursor-pointer bg-slate-900 border-slate-800 hover:border-slate-700'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className={`text-[10px] font-bold uppercase tracking-wider ${
          isUnavailable ? 'text-slate-500' : selected ? 'text-indigo-400' : 'text-slate-400'
        }`}>
          {strat.name}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${
          isUnavailable
            ? 'bg-rose-950/80 text-rose-400 border-rose-800'
            : strat.status === 'ACTIVE'
            ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
            : 'bg-slate-800 text-slate-400 border-slate-700'
        }`}>
          {isUnavailable ? 'Unavailable' : hasData ? 'Historical Replay' : 'No Data'}
        </span>
      </div>

      {strat.buffer_band && (
        <p className="text-[11px] text-slate-400 mb-3">{strat.buffer_band}</p>
      )}

      {isUnavailable ? (
        <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-400">
          {strat.reason || 'Unavailable — see strategy notes.'}
        </div>
      ) : !hasData ? (
        <div className="text-[11px] text-slate-500 py-2">No saved results available.</div>
      ) : (
        <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-800">
          <div>
            <span className="text-[10px] text-slate-500 block">CAGR</span>
            {fmtPct(strat.cagr_pct)}
          </div>
          <div>
            <span className="text-[10px] text-slate-500 block">Max DD</span>
            {fmtPct(strat.max_drawdown_pct, false)}
          </div>
          <div>
            <span className="text-[10px] text-slate-500 block">Sharpe</span>
            {strat.sharpe_ratio != null
              ? <span className="font-mono text-white">{strat.sharpe_ratio.toFixed(2)}</span>
              : NA}
          </div>
          <div>
            <span className="text-[10px] text-slate-500 block">Trades</span>
            {strat.trades_count != null
              ? <span className="font-mono text-white">{strat.trades_count}</span>
              : NA}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export const PaperTradingPage: React.FC = () => {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [overviewError, setOverviewError] = useState<{ message: string; auth: boolean } | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);

  const [replay, setReplay] = useState<any>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [isStress, setIsStress] = useState(false);

  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('cand1_reg_alpha_buf30');
  const [strategyDetail, setStrategyDetail] = useState<StrategyDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [selectedHoldingSymbol, setSelectedHoldingSymbol] = useState<string>('RELIANCE.NS');

  // --- data loaders ---

  const loadOverview = async () => {
    setOverviewLoading(true);
    setOverviewError(null);
    try {
      const data = await apiClient.getPaperTradingOverview();
      setOverview(data);
    } catch (e: any) {
      const msg = e?.message ?? String(e);
      const isAuth = msg.includes('401') || msg.includes('403') || msg.toLowerCase().includes('unauthorized');
      setOverviewError({ message: msg, auth: isAuth });
    } finally {
      setOverviewLoading(false);
    }
  };

  const loadReplay = async (stress: boolean) => {
    setReplayError(null);
    try {
      const data = await apiClient.getPaperTradingReplay(stress);
      // If backend returned a no-data sentinel, treat as empty
      if (data?.status === 'NO_DATA') {
        setReplay(null);
        setReplayError(data.message ?? 'No replay data available.');
      } else {
        setReplay(data);
      }
    } catch (e: any) {
      setReplayError(e?.message ?? String(e));
      setReplay(null);
    }
  };

  const loadStrategyDetail = async (stratId: string) => {
    setDetailLoading(true);
    setDetailError(null);
    setStrategyDetail(null);
    try {
      const data: StrategyDetail = await apiClient.getPaperTradingStrategy(stratId);
      setStrategyDetail(data);
      const firstHolding = Object.keys(data?.account?.holdings ?? {})[0];
      if (firstHolding) setSelectedHoldingSymbol(firstHolding);
    } catch (e: any) {
      setDetailError(e?.message ?? String(e));
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    loadOverview();
  }, []);

  useEffect(() => {
    loadReplay(isStress);
  }, [isStress]);

  useEffect(() => {
    // Only load detail for strategies that exist in the backend
    const supported = ['cand1_reg_alpha_buf30', 'cand2_c1b_buf30', 'cand3_dual_momentum_buf30'];
    if (supported.includes(selectedStrategyId)) {
      loadStrategyDetail(selectedStrategyId);
    }
  }, [selectedStrategyId]);

  // --- derived display values ---

  const replayPeriod = overview?.replay_period;
  const selectedStrat = overview?.strategies.find(s => s.id === selectedStrategyId);

  const account = strategyDetail?.account;
  const cumCosts = account?.cumulative_costs ?? account?.cumulative_costs_paid ?? null;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-indigo-400" />
            Cycle 4 — Historical Replay Lab
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Displays saved historical replay results only. No prospective paper trading is active.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Stress / Normal toggle — applies only to replay display */}
          <div className="flex items-center rounded-lg bg-slate-900 border border-slate-800 p-1 text-xs">
            <button
              onClick={() => setIsStress(false)}
              className={`px-3 py-1 rounded font-medium transition-all ${
                !isStress ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              Normal Costs (1×)
            </button>
            <button
              onClick={() => setIsStress(true)}
              className={`px-3 py-1 rounded font-medium transition-all ${
                isStress ? 'bg-rose-600 text-white shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              2× Stress Costs
            </button>
          </div>

          <button
            onClick={() => { loadOverview(); loadReplay(isStress); }}
            disabled={overviewLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${overviewLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Phase 4 Freeze Status */}
      <FreezeStatusBanner />

      {/* Disclaimer + Replay Period */}
      <div className="p-3.5 rounded-xl bg-slate-900/90 border border-indigo-900/60 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5 text-xs text-slate-300">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            <strong className="text-white">Simulated Research Capital:</strong>{' '}
            Each strategy operates with an independent simulated allocation of{' '}
            <strong className="text-emerald-400">₹20,000.00</strong>. This research capital is tracked
            in isolated ledgers and is{' '}
            <strong className="text-amber-300">not deployable broker funds</strong>.
          </span>
        </div>
        {replayPeriod && (
          <div className="flex items-center gap-3 text-[11px] text-slate-400">
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              Replay: {replayPeriod.start_date} → {replayPeriod.end_date}
            </span>
            {replayPeriod.sessions_count && (
              <span className="flex items-center gap-1">
                <BarChart2 className="w-3.5 h-3.5 text-indigo-400" />
                {replayPeriod.sessions_count} sessions
              </span>
            )}
          </div>
        )}
      </div>

      {/* Overview loading / error */}
      {overviewLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Loading overview…
        </div>
      )}

      {!overviewLoading && overviewError && (
        overviewError.auth
          ? <AuthErrorBanner detail={overviewError.message} />
          : <ErrorBanner message="Failed to load overview from API" detail={overviewError.message} />
      )}

      {/* Replay error (non-fatal — shown as callout) */}
      {replayError && (
        <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-800/40 flex items-start gap-2 text-xs">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="text-amber-300 font-semibold block">Replay data unavailable</span>
            <span className="text-amber-400/80">{replayError}</span>
          </div>
        </div>
      )}

      {/* 4-Strategy Overview Cards */}
      {!overviewLoading && overview && (
        <>
          {/* Benchmark summary */}
          {overview.benchmark && overview.benchmark.data_source === 'HISTORICAL_REPLAY' && (
            <div className="flex items-center gap-6 px-4 py-3 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-300">
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                Benchmark — NIFTYBEES.NS
              </span>
              <span>CAGR {fmtPct(overview.benchmark.cagr_pct)}</span>
              <span>Net Return {fmtPct(overview.benchmark.net_return_pct)}</span>
              <span>Max DD {fmtPct(overview.benchmark.max_drawdown_pct, false)}</span>
              <span className="ml-auto text-[10px] text-slate-500">Source: Historical Replay</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {overview.strategies.map(strat => (
              <StrategyOverviewCard
                key={strat.id}
                strat={strat}
                selected={selectedStrategyId === strat.id}
                onClick={() => setSelectedStrategyId(strat.id)}
              />
            ))}
          </div>
        </>
      )}

      {/* Historical Replay Detail — Stress or Normal */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2 pb-3 border-b border-slate-800">
          <Archive className="w-4 h-4 text-indigo-400" />
          <div>
            <h3 className="text-base font-bold text-white">
              Historical Replay — {isStress ? '2× Stress Costs' : 'Normal Costs'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Pre-computed replay over frozen snapshot. Source:{' '}
              <code className="text-slate-400">
                research/cycle4/replay_state/replay_{isStress ? 'stress' : 'normal'}_results.json
              </code>
            </p>
          </div>
        </div>

        {!replay && !replayError && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Loading replay…
          </div>
        )}

        {replay && replay.status !== 'NO_DATA' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2">Strategy</th>
                  <th className="px-3 py-2 text-right">Final Equity</th>
                  <th className="px-3 py-2 text-right">Net Return</th>
                  <th className="px-3 py-2 text-right">CAGR</th>
                  <th className="px-3 py-2 text-right">Max DD</th>
                  <th className="px-3 py-2 text-right">Sharpe</th>
                  <th className="px-3 py-2 text-right">Trades</th>
                  <th className="px-3 py-2 text-right">Win%</th>
                  <th className="px-3 py-2 text-right">PF</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {(['candidate1', 'candidate2', 'candidate3'] as const).map(key => {
                  const c = replay?.[key];
                  if (!c) return null;
                  const m = c.metrics ?? {};
                  const labels: Record<string, string> = {
                    candidate1: 'C1 · Reg-Alpha',
                    candidate2: 'C2 · C1b Momentum',
                    candidate3: 'C3 · Dual Strength',
                  };
                  const isUnavail = c.status === 'UNAVAILABLE';
                  return (
                    <tr key={key} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-3 py-2 font-sans font-semibold text-white">{labels[key]}</td>
                      <td className="px-3 py-2 text-right">
                        {isUnavail ? NA : fmt(c.final_equity, 2, '₹')}
                      </td>
                      <td className="px-3 py-2 text-right">{isUnavail ? NA : fmtPct(m.net_return_pct)}</td>
                      <td className="px-3 py-2 text-right">{isUnavail ? NA : fmtPct(m.cagr_pct)}</td>
                      <td className="px-3 py-2 text-right">{isUnavail ? NA : fmtPct(m.max_drawdown_pct, false)}</td>
                      <td className="px-3 py-2 text-right">
                        {isUnavail ? NA : m.sharpe_ratio != null ? m.sharpe_ratio.toFixed(2) : NA}
                      </td>
                      <td className="px-3 py-2 text-right">{isUnavail ? NA : (m.total_trades ?? NA)}</td>
                      <td className="px-3 py-2 text-right">
                        {isUnavail ? NA : fmtPct(m.win_rate_pct)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {isUnavail ? NA : m.profit_factor != null ? m.profit_factor.toFixed(2) : NA}
                      </td>
                    </tr>
                  );
                })}
                {/* Benchmark row */}
                {replay?.benchmark && (
                  <tr className="bg-slate-950/50">
                    <td className="px-3 py-2 font-sans text-slate-400 italic">NIFTYBEES (Benchmark)</td>
                    <td className="px-3 py-2 text-right text-slate-500">—</td>
                    <td className="px-3 py-2 text-right">{fmtPct(replay.benchmark.net_return_pct)}</td>
                    <td className="px-3 py-2 text-right">{fmtPct(replay.benchmark.cagr_pct)}</td>
                    <td className="px-3 py-2 text-right">{fmtPct(replay.benchmark.max_drawdown_pct, false)}</td>
                    <td colSpan={4} className="px-3 py-2 text-slate-600 text-center text-[10px]">Passive ETF — no trades</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Strategy Deep-Dive */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-5">
        <div className="flex items-center gap-2 pb-3 border-b border-slate-800">
          <Layers className="w-4 h-4 text-indigo-400" />
          <div>
            <h3 className="text-base font-bold text-white">
              Strategy Detail — Archived Broker State
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Source:{' '}
              <code className="text-slate-400">
                research/cycle4/replay_state/broker_normal_run/{selectedStrategyId}.*
              </code>
            </p>
          </div>
        </div>

        {detailLoading && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Loading strategy detail…
          </div>
        )}

        {!detailLoading && detailError && (
          detailError.includes('401') || detailError.includes('403')
            ? <AuthErrorBanner detail={detailError} />
            : <ErrorBanner message="Failed to load strategy detail" detail={detailError} />
        )}

        {!detailLoading && strategyDetail && !account && (
          <NoDataBanner
            label="No archived broker state found for this strategy."
            reason={`File not found: research/cycle4/replay_state/broker_normal_run/${selectedStrategyId}_state.json`}
          />
        )}

        {!detailLoading && account && (
          <>
            {/* Prospective Cycle 4 state note */}
            {strategyDetail?.phase_status && (
              <div className="p-2.5 rounded-lg bg-indigo-950/30 border border-indigo-800/40 text-[11px] text-indigo-300 flex items-center gap-2">
                <ShieldOff className="w-3.5 h-3.5 shrink-0" />
                {strategyDetail.phase_status}
              </div>
            )}

            {/* Account summary header */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <h4 className="text-sm font-bold text-white">
                  {account.strategy_name ?? selectedStrategyId}
                </h4>
                {account.last_processed_date && (
                  <span className="text-[11px] text-slate-500">
                    Last processed: <span className="text-slate-300">{account.last_processed_date}</span>
                    {' · '}Source: {strategyDetail.data_source ?? 'HISTORICAL_REPLAY'}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right">
                  <span className="text-[10px] text-slate-500 block">Total Equity</span>
                  <span className="text-base font-bold font-mono text-emerald-400">
                    ₹{(account.total_equity ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="text-right pl-3 border-l border-slate-800">
                  <span className="text-[10px] text-slate-500 block">Cash</span>
                  <span className="text-base font-bold font-mono text-white">
                    ₹{(account.cash ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </div>

            {/* KPI Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <MetricBox label="Realized P&L">
                <span className={(account.realized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  ₹{(account.realized_pnl ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </MetricBox>
              <MetricBox label="Unrealized P&L">
                <span className={(account.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                  ₹{(account.unrealized_pnl ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </MetricBox>
              <MetricBox label="Statutory Fees">
                <span className="text-amber-400 font-mono">
                  {cumCosts != null
                    ? `₹${cumCosts.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                    : '—'}
                </span>
              </MetricBox>
              <MetricBox label="Slippage">
                <span className="text-slate-300 font-mono">
                  {account.cumulative_slippage != null
                    ? `₹${account.cumulative_slippage.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                    : '—'}
                </span>
              </MetricBox>
              <MetricBox label="Holdings">
                <span className="text-white font-mono">
                  {Object.keys(account.holdings ?? {}).length} scrips
                </span>
              </MetricBox>
              <MetricBox label="Orders / Trades">
                <span className="text-white font-mono">
                  {strategyDetail.orders_count} / {strategyDetail.trades_count}
                </span>
              </MetricBox>
            </div>

            {/* Holdings Table */}
            <div className="flex flex-col gap-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Portfolio Holdings ({Object.keys(account.holdings ?? {}).length})</span>
                <span className="text-[10px] text-slate-500">Whole shares · No fractional ownership · Archived state</span>
              </h4>

              {account.holdings && Object.keys(account.holdings).length > 0 ? (
                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400">
                      <tr>
                        <th className="px-3 py-2">Symbol</th>
                        <th className="px-3 py-2 text-right">Shares</th>
                        <th className="px-3 py-2 text-right">Avg Cost</th>
                        <th className="px-3 py-2 text-right">Invested</th>
                        <th className="px-3 py-2 text-right">Research</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {Object.entries(account.holdings).map(([sym, pos]) => (
                        <tr key={sym} className="hover:bg-slate-800/40 transition-colors">
                          <td className="px-3 py-2 font-bold text-white">{sym}</td>
                          <td className="px-3 py-2 text-right text-slate-200">{pos.shares}</td>
                          <td className="px-3 py-2 text-right text-slate-300">₹{pos.avg_cost?.toFixed(2)}</td>
                          <td className="px-3 py-2 text-right font-bold text-emerald-400">
                            ₹{(pos.invested_cost ?? pos.shares * pos.avg_cost)?.toFixed(2)}
                          </td>
                          <td className="px-3 py-2 text-right font-sans">
                            <button
                              onClick={() => setSelectedHoldingSymbol(sym)}
                              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300"
                            >
                              Thesis
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <NoDataBanner
                  label="No holdings in archived state."
                  reason="Strategy is 100% cash or no archived positions exist for this period."
                />
              )}
            </div>

            {/* Orders Journal */}
            <div className="flex flex-col gap-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Order Audit Journal (Latest 100)</span>
                <span className="text-[10px] text-slate-500">Deterministic rejection reasons recorded</span>
              </h4>

              {strategyDetail.orders_journal.length > 0 ? (
                <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-56 overflow-y-auto">
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400 sticky top-0">
                      <tr>
                        <th className="px-3 py-2">Date</th>
                        <th className="px-3 py-2">Symbol</th>
                        <th className="px-3 py-2">Side</th>
                        <th className="px-3 py-2">Shares</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Fill / Rejection Note</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                      {[...strategyDetail.orders_journal].reverse().map((ord: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-800/40">
                          <td className="px-3 py-1.5 text-slate-400 font-sans">{ord.date}</td>
                          <td className="px-3 py-1.5 font-bold text-white">{ord.symbol}</td>
                          <td className="px-3 py-1.5">
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                              ord.side === 'BUY' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                            }`}>
                              {ord.side}
                            </span>
                          </td>
                          <td className="px-3 py-1.5 text-slate-300">{ord.shares}</td>
                          <td className="px-3 py-1.5">
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                              ord.status === 'FILLED' ? 'bg-emerald-950 text-emerald-400' : 'bg-amber-950 text-amber-400'
                            }`}>
                              {ord.status}
                            </span>
                          </td>
                          <td className="px-3 py-1.5 font-sans text-slate-400">
                            {ord.rejection_reason ? (
                              <span className="text-rose-300 font-semibold">{ord.rejection_reason}</span>
                            ) : ord.fill_price ? (
                              <span className="text-slate-500">Filled @ ₹{Number(ord.fill_price).toFixed(2)}</span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <NoDataBanner label="No orders found in archived broker state for this strategy." />
              )}
            </div>
          </>
        )}
      </section>

      {/* AI Research Notes — informational layer only */}
      <AiResearchNotes selectedSymbol={selectedHoldingSymbol} />
    </div>
  );
};
