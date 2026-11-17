import React, { useEffect, useState } from 'react';
import {
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
  PlayCircle,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldOff,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { AiResearchNotes } from '../components/AiResearchNotes';

// ---------------------------------------------------------------------------
// Types - Historical Replay
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

interface ReplayOverviewData {
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

interface ReplayAccountState {
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

interface ReplayStrategyDetail {
  strategy_id: string;
  data_source?: string;
  phase_status?: string;
  account: ReplayAccountState | null;
  orders_count: number;
  trades_count: number;
  orders_journal: any[];
  trades_journal: any[];
  daily_snapshots: any[];
}

// ---------------------------------------------------------------------------
// Types - Prospective Paper Tracking (Cycle 4)
// ---------------------------------------------------------------------------

interface ProspectivePortfolioState {
  name: string;
  initial_capital: number;
  cash: number;
  holdings: Record<string, { shares: number; avg_cost: number; invested_cost: number }>;
  realized_pnl: number;
  unrealized_pnl: number;
  total_equity: number;
  peak_equity: number;
  cumulative_costs_paid: number;
  cost_pct_of_capital: number;
  last_processed_date?: string | null;
  trades_count: number;
  sessions_count: number;
}

interface ProspectiveOverviewData {
  disclaimer: string;
  study_status: string; // 'AWAITING_OWNER_APPROVAL' | 'RUNNING' | 'NOT_STARTED' | 'PAUSED'
  forward_paper_trading_enabled: boolean;
  data_source: string;
  data_freshness: {
    last_processed_date?: string | null;
    status: string;
    valuation_completeness?: boolean | null;
    missing_price_symbols?: string[];
  };
  candidate: ProspectivePortfolioState | null;
  control: ProspectivePortfolioState | null;
  benchmark?: {
    symbol: string;
    start_close: number;
    latest_close: number;
    cumulative_return_pct: number;
    sessions_count: number;
  } | null;
}

interface ProspectiveStrategyDetail {
  strategy_id: string;
  study_status: string;
  forward_paper_trading_enabled: boolean;
  data_source: string;
  account: ProspectivePortfolioState | null;
  holdings: Record<string, { shares: number; avg_cost: number; invested_cost: number }>;
  orders_count: number;
  trades_count: number;
  daily_history: any[];
  trades_journal: any[];
  orders_journal: any[];
  last_processed_date?: string | null;
  valuation_completeness?: boolean | null;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const NA = <span className="text-slate-500 font-mono">—</span>;

function fmt(v: number | null | undefined, decimals = 2, prefix = '') {
  if (v == null) return NA;
  return (
    <span>
      {prefix}
      {v.toLocaleString('en-IN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
    </span>
  );
}

function fmtPct(v: number | null | undefined, positive_green = true) {
  if (v == null) return NA;
  const cls = positive_green
    ? v >= 0
      ? 'text-emerald-400'
      : 'text-rose-400'
    : v <= 0
    ? 'text-emerald-400'
    : 'text-rose-400';
  const sign = v >= 0 ? '+' : '';
  return <span className={`font-bold font-mono ${cls}`}>{sign}{v.toFixed(2)}%</span>;
}

function MetricBox({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
      <span className="text-[10px] text-slate-500 block mb-1 uppercase tracking-wider">{label}</span>
      <div className="text-sm font-bold">{children}</div>
    </div>
  );
}

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
          The API rejected the request with a 401 or 403. Set your session token in Settings. {detail && <span className="font-mono">{detail}</span>}
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

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export const PaperTradingPage: React.FC = () => {
  // Top-level Mode Switcher: 'prospective' (Cycle 4 forward tracking) vs 'replay' (Historical backtest lab)
  const [activeTab, setActiveTab] = useState<'prospective' | 'replay'>('prospective');

  // Prospective State
  const [prospOverview, setProspOverview] = useState<ProspectiveOverviewData | null>(null);
  const [prospLoading, setProspLoading] = useState(true);
  const [prospError, setProspError] = useState<{ message: string; auth: boolean } | null>(null);
  const [selectedProspStrategy, setSelectedProspStrategy] = useState<'candidate' | 'control'>('candidate');
  const [prospDetail, setProspDetail] = useState<ProspectiveStrategyDetail | null>(null);
  const [prospDetailLoading, setProspDetailLoading] = useState(false);
  const [prospDetailError, setProspDetailError] = useState<string | null>(null);

  // Historical Replay State
  const [replayOverview, setReplayOverview] = useState<ReplayOverviewData | null>(null);
  const [replayOverviewLoading, setReplayOverviewLoading] = useState(false);
  const [replayOverviewError, setReplayOverviewError] = useState<{ message: string; auth: boolean } | null>(null);
  const [replay, setReplay] = useState<any>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [isStress, setIsStress] = useState(false);
  const [selectedReplayStratId, setSelectedReplayStratId] = useState<string>('cand1_reg_alpha_buf30');
  const [replayDetail, setReplayDetail] = useState<ReplayStrategyDetail | null>(null);
  const [replayDetailLoading, setReplayDetailLoading] = useState(false);
  const [replayDetailError, setReplayDetailError] = useState<string | null>(null);

  // Shared Research Scrip Thesis
  const [selectedHoldingSymbol, setSelectedHoldingSymbol] = useState<string>('RELIANCE.NS');

  // --- Loaders: Prospective ---

  const loadProspectiveOverview = async () => {
    setProspLoading(true);
    setProspError(null);
    try {
      const data = await apiClient.getProspectivePaperOverview();
      setProspOverview(data);
    } catch (e: any) {
      const msg = e?.message ?? String(e);
      const isAuth = msg.includes('401') || msg.includes('403') || msg.toLowerCase().includes('unauthorized');
      setProspError({ message: msg, auth: isAuth });
    } finally {
      setProspLoading(false);
    }
  };

  const loadProspectiveDetail = async (stratId: 'candidate' | 'control') => {
    setProspDetailLoading(true);
    setProspDetailError(null);
    try {
      const data = await apiClient.getProspectivePaperStrategy(stratId);
      setProspDetail(data);
      const firstHolding = Object.keys(data?.holdings ?? {})[0];
      if (firstHolding) setSelectedHoldingSymbol(firstHolding);
    } catch (e: any) {
      setProspDetailError(e?.message ?? String(e));
    } finally {
      setProspDetailLoading(false);
    }
  };

  // --- Loaders: Historical Replay ---

  const loadReplayOverview = async () => {
    setReplayOverviewLoading(true);
    setReplayOverviewError(null);
    try {
      const data = await apiClient.getPaperTradingOverview();
      setReplayOverview(data);
    } catch (e: any) {
      const msg = e?.message ?? String(e);
      const isAuth = msg.includes('401') || msg.includes('403') || msg.toLowerCase().includes('unauthorized');
      setReplayOverviewError({ message: msg, auth: isAuth });
    } finally {
      setReplayOverviewLoading(false);
    }
  };

  const loadReplayResults = async (stress: boolean) => {
    setReplayError(null);
    try {
      const data = await apiClient.getPaperTradingReplay(stress);
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

  const loadReplayDetail = async (stratId: string) => {
    setReplayDetailLoading(true);
    setReplayDetailError(null);
    try {
      const data = await apiClient.getPaperTradingStrategy(stratId);
      setReplayDetail(data);
      const firstHolding = Object.keys(data?.account?.holdings ?? {})[0];
      if (firstHolding) setSelectedHoldingSymbol(firstHolding);
    } catch (e: any) {
      setReplayDetailError(e?.message ?? String(e));
    } finally {
      setReplayDetailLoading(false);
    }
  };

  // Effects
  useEffect(() => {
    loadProspectiveOverview();
    loadProspectiveDetail(selectedProspStrategy);
  }, []);

  useEffect(() => {
    loadProspectiveDetail(selectedProspStrategy);
  }, [selectedProspStrategy]);

  useEffect(() => {
    if (activeTab === 'replay') {
      if (!replayOverview) loadReplayOverview();
      loadReplayResults(isStress);
      loadReplayDetail(selectedReplayStratId);
    }
  }, [activeTab, isStress]);

  useEffect(() => {
    if (activeTab === 'replay') {
      loadReplayDetail(selectedReplayStratId);
    }
  }, [selectedReplayStratId]);

  return (
    <div className="flex flex-col gap-6">
      {/* Top Header & Navigation Segment */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-indigo-400" />
            Paper-Trading & Strategy Observation Desk
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Controlled environment for prospective forward observation and historical counterfactual replay.
          </p>
        </div>

        {/* Top-Level Mode Tabs */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-xl bg-slate-900 border border-slate-800 p-1 text-xs">
            <button
              onClick={() => setActiveTab('prospective')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-semibold transition-all ${
                activeTab === 'prospective'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <PlayCircle className="w-3.5 h-3.5" />
              Prospective Paper Tracking
              <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950/80 text-amber-300 border border-amber-800">
                Awaiting Approval
              </span>
            </button>
            <button
              onClick={() => setActiveTab('replay')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-semibold transition-all ${
                activeTab === 'replay'
                  ? 'bg-slate-700 text-white shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Archive className="w-3.5 h-3.5" />
              Historical Replay Lab (2022–2026)
            </button>
          </div>

          <button
            onClick={() => {
              if (activeTab === 'prospective') {
                loadProspectiveOverview();
                loadProspectiveDetail(selectedProspStrategy);
              } else {
                loadReplayOverview();
                loadReplayResults(isStress);
                loadReplayDetail(selectedReplayStratId);
              }
            }}
            disabled={prospLoading || replayOverviewLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${prospLoading || replayOverviewLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ======================================================================= */}
      {/* SECTION 1: PROSPECTIVE PAPER TRACKING (CYCLE 4)                         */}
      {/* ======================================================================= */}
      {activeTab === 'prospective' && (
        <div className="flex flex-col gap-6">
          {/* Prospective Governance Banner */}
          <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/50 flex items-start justify-between flex-wrap gap-3">
            <div className="flex items-start gap-3 text-xs text-slate-300 max-w-3xl">
              <PauseCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <strong className="text-amber-300 font-semibold">
                    Forward Paper-Trading Status: AWAITING OWNER APPROVAL
                  </strong>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 font-mono text-slate-300">
                    FORWARD_PAPER_TRADING_ENABLED=False
                  </span>
                </div>
                <p className="text-slate-400 leading-relaxed text-[11px]">
                  Daily background schedulers and manual CLI runners are <strong className="text-slate-200">locked fail-closed</strong>.
                  Displaying saved verification telemetry from the frozen baseline session (2026-11-06).
                  Zero broker orders, automated alerts, or deployable capital orders will be generated until explicit owner sign-off.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 text-[11px] text-slate-400">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-indigo-400" />
                Last Processed: <span className="text-white font-mono">{prospOverview?.data_freshness?.last_processed_date ?? '2026-11-06'}</span>
              </span>
              <span className="flex items-center gap-1">
                <Scale className="w-3.5 h-3.5 text-emerald-400" />
                Capital: ₹17,500.00 / portfolio
              </span>
            </div>
          </div>

          {/* Prospective Error Banner */}
          {!prospLoading && prospError && (
            prospError.auth ? (
              <AuthErrorBanner detail={prospError.message} />
            ) : (
              <ErrorBanner message="Failed to load prospective paper-trading telemetry" detail={prospError.message} />
            )
          )}

          {/* Prospective Loading */}
          {prospLoading && (
            <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading prospective paper-trading telemetry…
            </div>
          )}

          {/* Side-by-Side Candidate vs Control Cards */}
          {!prospLoading && prospOverview && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Candidate Portfolio */}
              <div
                onClick={() => setSelectedProspStrategy('candidate')}
                className={`cursor-pointer rounded-xl p-5 border transition-all ${
                  selectedProspStrategy === 'candidate'
                    ? 'bg-indigo-950/40 border-indigo-500 shadow-lg ring-1 ring-indigo-500'
                    : 'bg-slate-900 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400">Candidate 1 (Active)</span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                      Top 20 Enter / Retain ≤ 30
                    </span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                    {prospOverview.study_status}
                  </span>
                </div>

                <h3 className="text-base font-bold text-white mb-1">Market-Sector Regression-Alpha</h3>
                <p className="text-xs text-slate-400 mb-4">Purged idiosyncratic 12-1 momentum · Whole-share delivery sizing</p>

                {prospOverview.candidate ? (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-slate-800/80">
                    <div>
                      <span className="text-[10px] text-slate-500 block">Total Equity</span>
                      <span className="font-mono font-bold text-white text-sm">
                        ₹{prospOverview.candidate.total_equity.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Cash Balance</span>
                      <span className="font-mono text-slate-300 text-xs">
                        ₹{prospOverview.candidate.cash.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Unrealized P&L</span>
                      <span className="font-mono font-bold text-emerald-400 text-xs">
                        +₹{prospOverview.candidate.unrealized_pnl.toFixed(2)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Fees Paid</span>
                      <span className="font-mono text-amber-400 text-xs">
                        ₹{prospOverview.candidate.cumulative_costs_paid.toFixed(2)} ({prospOverview.candidate.cost_pct_of_capital}%)
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 py-2">No candidate state recorded.</div>
                )}
              </div>

              {/* Control Portfolio */}
              <div
                onClick={() => setSelectedProspStrategy('control')}
                className={`cursor-pointer rounded-xl p-5 border transition-all ${
                  selectedProspStrategy === 'control'
                    ? 'bg-indigo-950/40 border-indigo-500 shadow-lg ring-1 ring-indigo-500'
                    : 'bg-slate-900 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Control Portfolio</span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800">
                      C1b Baseline Comparator
                    </span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded font-semibold bg-blue-950 text-blue-400 border border-blue-800">
                    {prospOverview.study_status}
                  </span>
                </div>

                <h3 className="text-base font-bold text-white mb-1">C1b Baseline 12-1 Momentum</h3>
                <p className="text-xs text-slate-400 mb-4">Unpurged 12-1 momentum · Identical ₹17,500 scale & Zerodha fees</p>

                {prospOverview.control ? (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-slate-800/80">
                    <div>
                      <span className="text-[10px] text-slate-500 block">Total Equity</span>
                      <span className="font-mono font-bold text-white text-sm">
                        ₹{prospOverview.control.total_equity.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Cash Balance</span>
                      <span className="font-mono text-slate-300 text-xs">
                        ₹{prospOverview.control.cash.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Unrealized P&L</span>
                      <span className="font-mono font-bold text-emerald-400 text-xs">
                        +₹{prospOverview.control.unrealized_pnl.toFixed(2)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 block">Fees Paid</span>
                      <span className="font-mono text-amber-400 text-xs">
                        ₹{prospOverview.control.cumulative_costs_paid.toFixed(2)} ({prospOverview.control.cost_pct_of_capital}%)
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 py-2">No control state recorded.</div>
                )}
              </div>
            </div>
          )}

          {/* Benchmark Synchronous Comparison Strip */}
          {prospOverview?.benchmark && (
            <div className="flex items-center justify-between flex-wrap gap-4 px-4 py-3 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-300">
              <div className="flex items-center gap-3">
                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                  Synchronous Passive Benchmark: {prospOverview.benchmark.symbol}
                </span>
                <span>Base: ₹{prospOverview.benchmark.start_close.toFixed(2)}</span>
                <span>Latest: ₹{prospOverview.benchmark.latest_close.toFixed(2)}</span>
                <span>Net Return: {fmtPct(prospOverview.benchmark.cumulative_return_pct)}</span>
              </div>
              <span className="text-[10px] text-slate-500">
                Identical Sessions: {prospOverview.benchmark.sessions_count} sessions
              </span>
            </div>
          )}

          {/* Detailed Workspace for Selected Prospective Strategy */}
          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-5">
            <div className="flex items-center justify-between flex-wrap gap-3 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                <div>
                  <h3 className="text-base font-bold text-white">
                    {selectedProspStrategy === 'candidate'
                      ? 'Candidate 1: Market-Sector Regression-Alpha'
                      : 'Control: C1b Baseline Momentum'}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Source: <code className="text-slate-400">research/cycle4/state/{selectedProspStrategy === 'candidate' ? 'candidate_reg_alpha_buf30' : 'control_c1b_buf30'}_*</code>
                  </p>
                </div>
              </div>

              {prospDetail?.account && (
                <div className="flex items-center gap-4 text-xs font-mono">
                  <div className="text-right">
                    <span className="text-[10px] text-slate-500 block font-sans">Simulated Capital</span>
                    <span className="text-white">₹{prospDetail.account.initial_capital.toFixed(2)}</span>
                  </div>
                  <div className="text-right pl-3 border-l border-slate-800">
                    <span className="text-[10px] text-slate-500 block font-sans">Current Equity</span>
                    <span className="text-emerald-400 font-bold">₹{prospDetail.account.total_equity.toFixed(2)}</span>
                  </div>
                </div>
              )}
            </div>

            {prospDetailLoading && (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <RefreshCw className="w-4 h-4 animate-spin" />
                Loading prospective strategy detail…
              </div>
            )}

            {!prospDetailLoading && prospDetail && (
              <>
                {/* Active Holdings Table */}
                <div className="flex flex-col gap-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span>Portfolio Holdings ({Object.keys(prospDetail.holdings).length})</span>
                    <span className="text-[10px] text-slate-500">Whole shares · No fractional positions</span>
                  </h4>

                  {Object.keys(prospDetail.holdings).length > 0 ? (
                    <div className="overflow-x-auto rounded-lg border border-slate-800">
                      <table className="w-full text-left text-xs text-slate-300">
                        <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400">
                          <tr>
                            <th className="px-3 py-2">Symbol</th>
                            <th className="px-3 py-2 text-right">Shares</th>
                            <th className="px-3 py-2 text-right">Avg Cost</th>
                            <th className="px-3 py-2 text-right">Invested Value</th>
                            <th className="px-3 py-2 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono">
                          {Object.entries(prospDetail.holdings).map(([sym, pos]) => (
                            <tr key={sym} className="hover:bg-slate-800/40 transition-colors">
                              <td className="px-3 py-2 font-bold text-white">{sym}</td>
                              <td className="px-3 py-2 text-right text-slate-200">{pos.shares}</td>
                              <td className="px-3 py-2 text-right text-slate-300">₹{pos.avg_cost.toFixed(2)}</td>
                              <td className="px-3 py-2 text-right font-bold text-emerald-400">
                                ₹{pos.invested_cost.toFixed(2)}
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
                      label="No active holdings in this prospective state."
                      reason="Portfolio is 100% cash or no positions currently allocated."
                    />
                  )}
                </div>

                {/* Trade Execution Ledger */}
                <div className="flex flex-col gap-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span>Trade Execution Ledger ({prospDetail.trades_count} trades)</span>
                    <span className="text-[10px] text-slate-500">Includes exact Zerodha delivery fee breakdown</span>
                  </h4>

                  {prospDetail.trades_journal.length > 0 ? (
                    <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-56 overflow-y-auto">
                      <table className="w-full text-left text-xs text-slate-300">
                        <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400 sticky top-0">
                          <tr>
                            <th className="px-3 py-2">Date</th>
                            <th className="px-3 py-2">Symbol</th>
                            <th className="px-3 py-2">Side</th>
                            <th className="px-3 py-2">Action</th>
                            <th className="px-3 py-2 text-right">Shares</th>
                            <th className="px-3 py-2 text-right">Fill Price</th>
                            <th className="px-3 py-2 text-right">Gross Turnover</th>
                            <th className="px-3 py-2 text-right">Net Cash Delta</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                          {prospDetail.trades_journal.map((trd: any, idx: number) => (
                            <tr key={idx} className="hover:bg-slate-800/40">
                              <td className="px-3 py-1.5 text-slate-400 font-sans">{trd.exec_date}</td>
                              <td className="px-3 py-1.5 font-bold text-white">{trd.symbol}</td>
                              <td className="px-3 py-1.5">
                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                  trd.side === 'BUY' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                                }`}>
                                  {trd.side}
                                </span>
                              </td>
                              <td className="px-3 py-1.5 font-sans text-slate-400">{trd.action}</td>
                              <td className="px-3 py-1.5 text-right text-slate-200">{trd.shares}</td>
                              <td className="px-3 py-1.5 text-right text-slate-300">₹{Number(trd.fill_price).toFixed(2)}</td>
                              <td className="px-3 py-1.5 text-right text-slate-200">₹{Number(trd.gross_turnover).toFixed(2)}</td>
                              <td className="px-3 py-1.5 text-right text-rose-300 font-semibold">₹{Number(trd.net_cash_delta).toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <NoDataBanner label="No prospective trades executed yet." />
                  )}
                </div>

                {/* Daily Mark-to-Market History */}
                <div className="flex flex-col gap-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span>Daily Mark-to-Market Ledger ({prospDetail.daily_history.length} sessions)</span>
                    <span className="text-[10px] text-slate-500">Reconciled EOD equity, drawdown & valuation status</span>
                  </h4>

                  {prospDetail.daily_history.length > 0 ? (
                    <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-56 overflow-y-auto">
                      <table className="w-full text-left text-xs text-slate-300">
                        <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400 sticky top-0">
                          <tr>
                            <th className="px-3 py-2">Session Date</th>
                            <th className="px-3 py-2 text-right">Total Equity</th>
                            <th className="px-3 py-2 text-right">Cash</th>
                            <th className="px-3 py-2 text-right">Invested Value</th>
                            <th className="px-3 py-2 text-right">Drawdown</th>
                            <th className="px-3 py-2 text-right">Cum Return</th>
                            <th className="px-3 py-2">Regime Status</th>
                            <th className="px-3 py-2">Valuation</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                          {prospDetail.daily_history.map((row: any, idx: number) => (
                            <tr key={idx} className="hover:bg-slate-800/40">
                              <td className="px-3 py-1.5 text-slate-400 font-sans">{row.date}</td>
                              <td className="px-3 py-1.5 text-right font-bold text-white">₹{Number(row.total_equity).toFixed(2)}</td>
                              <td className="px-3 py-1.5 text-right text-slate-300">₹{Number(row.cash).toFixed(2)}</td>
                              <td className="px-3 py-1.5 text-right text-slate-300">₹{Number(row.invested_value).toFixed(2)}</td>
                              <td className="px-3 py-1.5 text-right text-slate-400">{Number(row.drawdown_pct).toFixed(2)}%</td>
                              <td className="px-3 py-1.5 text-right font-bold text-emerald-400">+{Number(row.cumulative_return_pct).toFixed(2)}%</td>
                              <td className="px-3 py-1.5 font-sans text-[10px] text-slate-400">{row.regime_status}</td>
                              <td className="px-3 py-1.5">
                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold ${
                                  row.is_complete_valuation ? 'bg-emerald-950 text-emerald-400' : 'bg-amber-950 text-amber-300'
                                }`}>
                                  {row.is_complete_valuation ? 'COMPLETE' : 'INCOMPLETE'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <NoDataBanner label="No daily ledger entries recorded." />
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {/* ======================================================================= */}
      {/* SECTION 2: HISTORICAL REPLAY LAB (2022–2026)                           */}
      {/* ======================================================================= */}
      {activeTab === 'replay' && (
        <div className="flex flex-col gap-6">
          {/* Replay Notice */}
          <div className="p-3.5 rounded-xl bg-slate-900/90 border border-indigo-900/60 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2.5 text-xs text-slate-300">
              <Archive className="w-4 h-4 text-indigo-400 shrink-0" />
              <span>
                <strong className="text-white">Historical Replay Lab:</strong> Evaluates strategies over frozen historical market bars (2022–2026).
                Simulated capital: <strong className="text-emerald-400">₹20,000.00</strong> per strategy.
              </span>
            </div>

            {/* Stress Toggle */}
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
          </div>

          {/* Replay Overview Cards */}
          {replayOverview && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {replayOverview.strategies.map((strat) => (
                <div
                  key={strat.id}
                  onClick={() => strat.status !== 'UNAVAILABLE' && setSelectedReplayStratId(strat.id)}
                  className={`rounded-xl p-4 border transition-all ${
                    strat.status === 'UNAVAILABLE'
                      ? 'bg-slate-900/50 border-slate-800/60 opacity-70'
                      : selectedReplayStratId === strat.id
                      ? 'cursor-pointer bg-indigo-950/40 border-indigo-500 shadow-lg ring-1 ring-indigo-500'
                      : 'cursor-pointer bg-slate-900 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {strat.name}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${
                      strat.status === 'UNAVAILABLE'
                        ? 'bg-rose-950/80 text-rose-400 border-rose-800'
                        : 'bg-emerald-950 text-emerald-400 border-emerald-800'
                    }`}>
                      {strat.status === 'UNAVAILABLE' ? 'Unavailable' : 'Historical Replay'}
                    </span>
                  </div>

                  {strat.status === 'UNAVAILABLE' ? (
                    <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-400 mt-2">
                      {strat.reason || 'Unavailable'}
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-800 mt-2">
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
                        <span className="font-mono text-white">{strat.sharpe_ratio?.toFixed(2) ?? '—'}</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-500 block">Trades</span>
                        <span className="font-mono text-white">{strat.trades_count ?? '—'}</span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Historical Replay Comparative Table */}
          {replay && replay.status !== 'NO_DATA' && (
            <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-4">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-indigo-400" />
                Historical Performance Matrix ({isStress ? '2× Stress Costs' : 'Normal Costs'})
              </h3>

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
                    {(['candidate1', 'candidate2', 'candidate3'] as const).map((key) => {
                      const c = replay?.[key];
                      if (!c) return null;
                      const m = c.metrics ?? {};
                      const labels: Record<string, string> = {
                        candidate1: 'C1 · Reg-Alpha',
                        candidate2: 'C2 · C1b Momentum',
                        candidate3: 'C3 · Dual Strength',
                      };
                      return (
                        <tr key={key} className="hover:bg-slate-800/40 transition-colors">
                          <td className="px-3 py-2 font-sans font-semibold text-white">{labels[key]}</td>
                          <td className="px-3 py-2 text-right">{fmt(c.final_equity, 2, '₹')}</td>
                          <td className="px-3 py-2 text-right">{fmtPct(m.net_return_pct)}</td>
                          <td className="px-3 py-2 text-right">{fmtPct(m.cagr_pct)}</td>
                          <td className="px-3 py-2 text-right">{fmtPct(m.max_drawdown_pct, false)}</td>
                          <td className="px-3 py-2 text-right">{m.sharpe_ratio?.toFixed(2) ?? '—'}</td>
                          <td className="px-3 py-2 text-right">{m.total_trades ?? '—'}</td>
                          <td className="px-3 py-2 text-right">{fmtPct(m.win_rate_pct)}</td>
                          <td className="px-3 py-2 text-right">{m.profit_factor?.toFixed(2) ?? '—'}</td>
                        </tr>
                      );
                    })}
                    {replay?.benchmark && (
                      <tr className="bg-slate-950/50">
                        <td className="px-3 py-2 font-sans text-slate-400 italic">NIFTYBEES (Benchmark)</td>
                        <td className="px-3 py-2 text-right text-slate-500">—</td>
                        <td className="px-3 py-2 text-right">{fmtPct(replay.benchmark.net_return_pct)}</td>
                        <td className="px-3 py-2 text-right">{fmtPct(replay.benchmark.cagr_pct)}</td>
                        <td className="px-3 py-2 text-right">{fmtPct(replay.benchmark.max_drawdown_pct, false)}</td>
                        <td colSpan={4} className="px-3 py-2 text-slate-600 text-center text-[10px]">
                          Passive ETF Benchmark
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Archived Broker Detail */}
          {replayDetail?.account && (
            <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-4">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                Archived Broker Accounting: {selectedReplayStratId}
              </h3>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricBox label="Realized P&L">
                  <span className={(replayDetail.account.realized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                    ₹{(replayDetail.account.realized_pnl ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </MetricBox>
                <MetricBox label="Unrealized P&L">
                  <span className={(replayDetail.account.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                    ₹{(replayDetail.account.unrealized_pnl ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </MetricBox>
                <MetricBox label="Statutory Fees">
                  <span className="text-amber-400 font-mono">
                    ₹{(replayDetail.account.cumulative_costs ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </MetricBox>
                <MetricBox label="Orders / Trades">
                  <span className="text-white font-mono">
                    {replayDetail.orders_count} / {replayDetail.trades_count}
                  </span>
                </MetricBox>
              </div>
            </section>
          )}
        </div>
      )}

      {/* Opposing Thesis & AI Research Notes Layer */}
      <AiResearchNotes selectedSymbol={selectedHoldingSymbol} />
    </div>
  );
};
