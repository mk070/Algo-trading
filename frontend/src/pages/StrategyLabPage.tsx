import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity, AlertTriangle, ArrowUpDown, CheckCircle2, ChevronDown, ChevronRight,
  CircleDot, FlaskConical, LayoutList, Loader2, Play, RefreshCw, Send, Trophy, XCircle,
} from 'lucide-react';
import { fetchJson, API_BASE } from '../api/client';
import { TradeCardList } from '../components/TradeCardList';

// ─── Types ───────────────────────────────────────────────────────────────────

interface LabStrategy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  parameters: Record<string, any>;
  config_hash: string;
  min_history_bars: number;
}

interface LabRun {
  id: string;
  strategy_id: string;
  holding_days: number;
  status: 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED';
  progress_pct: number;
  submitted_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

interface LabResult {
  id: number;
  run_id: string;
  strategy_id: string;
  holding_days: number;
  total_trades: number;
  win_rate: number | null;
  expectancy_r: number | null;
  median_net_expectancy: number | null;
  profit_factor: number | null;
  cagr_pct: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  total_pnl: number | null;
  sample_ok: boolean;
  sample_label: string | null;
  rank?: number | null;
  auto_selected?: boolean;
  ranking_note?: string;
  created_at: string | null;
}

interface RankedResult extends LabResult {
  rank: number | null;
  auto_selected: boolean;
  ranking_note: string;
}

interface StudySummary {
  id: string;
  name: string;
  status: string;
  start_date: string;
  capital: number;
  kill_switch_triggered: boolean;
  strategies: Array<{ strategy_id: string; holding_days: number }>;
}

interface DailyRow {
  strategy_id: string;
  date: string;
  total_equity: number;
  drawdown_pct: number;
  cumulative_return_pct: number;
  open_positions: number;
  trades_today: number;
}

interface StudyDetail extends StudySummary {
  daily: DailyRow[];
  holdings: any[];
  recent_trades: any[];
  promotion_checklists: Record<string, any>;
  disclaimer: string;
  last_evaluated_at?: string | null;
  data_through_date?: string | null;
  staleness?: {
    last_data_date?: string | null;
    missed_sessions: number;
    is_stale: boolean;
  };
}

// ─── Constants ───────────────────────────────────────────────────────────────

const HOLDING_OPTIONS = [4, 7, 10, 15];
const DEFAULT_CAPITAL = 500000;
const DEFAULT_RISK = 0.5;
const DEFAULT_MAX_POS = 5;

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmtPct = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
const fmtR = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(3)}R`;
const fmtN = (v: number | null | undefined) =>
  v == null ? '—' : v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
const fmtINR = (v: number | null | undefined) =>
  v == null ? '—' : `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

function statusColor(s: string) {
  if (s === 'DONE') return 'text-emerald-400';
  if (s === 'RUNNING') return 'text-amber-400';
  if (s === 'FAILED') return 'text-red-400';
  return 'text-slate-400';
}

function sampleBadge(ok: boolean, label: string | null) {
  if (ok) return <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-900/50 text-emerald-300">✓ SUFFICIENT</span>;
  return <span className="px-1.5 py-0.5 rounded text-[10px] bg-orange-900/50 text-orange-300">⚠ {label || 'INSUFFICIENT'}</span>;
}

// ─── Disclaimer Banner ───────────────────────────────────────────────────────

const DisclaimerBanner: React.FC = () => (
  <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-amber-950/40 border border-amber-800/40 text-amber-300 text-xs">
    <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
    <span>
      <strong>Survivorship Bias Warning:</strong> Backtest on current Nifty stocks may contain survivorship bias —
      delisted or failed companies are excluded from historical data. Rankings screen ideas only;
      forward paper results provide prospective evidence.
    </span>
  </div>
);

// ─── Tab: Backtest ────────────────────────────────────────────────────────────

const BacktestTab: React.FC = () => {
  const [strategies, setStrategies] = useState<LabStrategy[]>([]);
  const [runs, setRuns] = useState<LabRun[]>([]);
  const [results, setResults] = useState<LabResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedHolding, setSelectedHolding] = useState<number[]>([7]);
  const [capital, setCapital] = useState(DEFAULT_CAPITAL);
  const [riskPct, setRiskPct] = useState(DEFAULT_RISK);
  const [maxPos, setMaxPos] = useState(DEFAULT_MAX_POS);
  const [runningAll, setRunningAll] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [strats, runsData, resData] = await Promise.all([
        fetchJson<LabStrategy[]>(`${API_BASE}/lab/strategies`),
        fetchJson<LabRun[]>(`${API_BASE}/lab/runs?limit=100`),
        fetchJson<LabResult[]>(`${API_BASE}/lab/results`),
      ]);
      setStrategies(strats);
      setRuns(runsData);
      setResults(resData);
    } catch (e: any) {
      setError(e.message || 'Failed to load');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll while any run is pending/running
  useEffect(() => {
    const hasActive = runs.some(r => r.status === 'PENDING' || r.status === 'RUNNING');
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(load, 3000);
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [runs, load]);

  const syncRegistry = async () => {
    setSyncing(true);
    try {
      await fetchJson(`${API_BASE}/lab/strategies/sync`, { method: 'POST' });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  const runStrategy = async (strategyId: string, hd: number) => {
    setRunningId(`${strategyId}-${hd}`);
    try {
      await fetchJson(`${API_BASE}/lab/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_id: strategyId, holding_days: hd, capital, risk_pct: riskPct, max_positions: maxPos }),
      });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunningId(null);
    }
  };

  const runAll = async () => {
    setRunningAll(true);
    try {
      await fetchJson(`${API_BASE}/lab/run-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ holding_days: selectedHolding, capital, risk_pct: riskPct, max_positions: maxPos }),
      });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunningAll(false);
    }
  };

  // Map result by strategy+holding
  const resultMap: Record<string, LabResult> = {};
  for (const r of results) {
    resultMap[`${r.strategy_id}-${r.holding_days}`] = r;
  }
  const runMap: Record<string, LabRun> = {};
  for (const r of runs) {
    const key = `${r.strategy_id}-${r.holding_days}`;
    if (!runMap[key] || new Date(r.submitted_at || '') > new Date(runMap[key].submitted_at || '')) {
      runMap[key] = r;
    }
  }

  return (
    <div className="space-y-5">
      <DisclaimerBanner />

      {/* Config row */}
      <div className="flex flex-wrap items-end gap-4 p-4 rounded-lg bg-slate-900/60 border border-slate-800">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Holding Days</label>
          <div className="flex gap-2">
            {HOLDING_OPTIONS.map(hd => (
              <button
                key={hd}
                onClick={() => setSelectedHolding(prev => prev.includes(hd) ? prev.filter(x => x !== hd) : [...prev, hd])}
                className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${selectedHolding.includes(hd) ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}
              >{hd}d</button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Capital (₹)</label>
          <input
            type="number"
            value={capital}
            onChange={e => setCapital(Number(e.target.value))}
            className="w-28 px-2 py-1.5 rounded bg-slate-800 border border-slate-700 text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Risk %</label>
          <input
            type="number"
            step="0.1"
            value={riskPct}
            onChange={e => setRiskPct(Number(e.target.value))}
            className="w-20 px-2 py-1.5 rounded bg-slate-800 border border-slate-700 text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Max Pos</label>
          <input
            type="number"
            value={maxPos}
            onChange={e => setMaxPos(Number(e.target.value))}
            className="w-16 px-2 py-1.5 rounded bg-slate-800 border border-slate-700 text-white text-sm"
          />
        </div>
        <div className="flex gap-2 ml-auto">
          <button onClick={syncRegistry} disabled={syncing} className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-white text-sm">
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} /> Sync Registry
          </button>
          <button onClick={runAll} disabled={runningAll || strategies.length === 0} className="flex items-center gap-1.5 px-4 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium">
            {runningAll ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Run All
          </button>
        </div>
      </div>

      {error && <div className="px-4 py-3 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-sm">{error}</div>}
      {loading && strategies.length === 0 && <div className="text-center text-slate-400 py-8"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" /> Loading strategies…</div>}

      {/* Strategy grid */}
      <div className="space-y-2">
        {strategies.map(s => (
          <div key={s.id} className="rounded-lg bg-slate-900/60 border border-slate-800 overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3">
              <span className="text-xs font-mono text-indigo-400 w-8 flex-shrink-0">{s.id}</span>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm text-white truncate">{s.name}</div>
                <div className="text-xs text-slate-400 truncate">{s.description?.split('\n')[0] || ''}</div>
              </div>
              <div className="flex gap-2 flex-wrap justify-end">
                {selectedHolding.map(hd => {
                  const key = `${s.id}-${hd}`;
                  const run = runMap[key];
                  const res = resultMap[key];
                  const isRunning = run && (run.status === 'RUNNING' || run.status === 'PENDING');
                  return (
                    <div key={hd} className="flex flex-col items-center gap-1">
                      <button
                        onClick={() => runStrategy(s.id, hd)}
                        disabled={!!isRunning || runningId === key}
                        className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${isRunning ? 'bg-amber-900/50 text-amber-300' : 'bg-slate-700 hover:bg-slate-600 text-white'}`}
                      >
                        {isRunning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                        {hd}d
                      </button>
                      {res && (
                        <div className="text-center">
                          <div className={`text-[10px] font-medium ${(res.expectancy_r || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {fmtR(res.expectancy_r)}
                          </div>
                          <div className="text-[10px] text-slate-500">{res.total_trades}tr</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Expanded results row */}
            {selectedHolding.some(hd => resultMap[`${s.id}-${hd}`]) && (
              <div className="border-t border-slate-800 px-4 py-2 flex gap-6 flex-wrap">
                {selectedHolding.map(hd => {
                  const res = resultMap[`${s.id}-${hd}`];
                  if (!res) return null;
                  return (
                    <div key={hd} className="text-xs space-y-0.5">
                      <div className="text-slate-400 font-medium">{hd}d</div>
                      <div>Trades: <span className="text-white">{res.total_trades}</span></div>
                      <div>Win%: <span className="text-white">{res.win_rate ? `${(res.win_rate * 100).toFixed(1)}%` : '—'}</span></div>
                      <div>Exp R: <span className={`font-medium ${(res.expectancy_r || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fmtR(res.expectancy_r)}</span></div>
                      <div>CAGR: <span className="text-white">{fmtPct(res.cagr_pct)}</span></div>
                      <div>MDD: <span className="text-red-400">{fmtPct(res.max_drawdown_pct)}</span></div>
                      <div>{sampleBadge(res.sample_ok, res.sample_label)}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Tab: Rank & Send to Paper ────────────────────────────────────────────────

const RankTab: React.FC = () => {
  const [ranked, setRanked] = useState<RankedResult[]>([]);
  const [disclaimer, setDisclaimer] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [studyName, setStudyName] = useState('');
  const [duration, setDuration] = useState(90); // days
  const [capital, setCapital] = useState(DEFAULT_CAPITAL);
  const [riskPct, setRiskPct] = useState(DEFAULT_RISK);
  const [maxPos, setMaxPos] = useState(DEFAULT_MAX_POS);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [sortField, setSortField] = useState<string>('rank');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJson<{ ranked: RankedResult[]; disclaimer: string }>(`${API_BASE}/lab/rank`);
      setRanked(data.ranked || []);
      setDisclaimer(data.disclaimer || '');
      // Auto-select top-5
      const autoIds = new Set(
        data.ranked.filter(r => r.auto_selected).map(r => `${r.strategy_id}-${r.holding_days}`)
      );
      setSelected(autoIds);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleSelect = (key: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else if (next.size < 5) next.add(key);
      return next;
    });
  };

  const sendToPaper = async () => {
    if (!studyName.trim()) { setError('Enter a study name'); return; }
    if (selected.size === 0) { setError('Select at least 1 strategy'); return; }
    setSending(true);
    setError(null);
    try {
      const strategies = [...selected].map(key => {
        const [sid, hd] = key.split('-');
        return { strategy_id: sid, holding_days: parseInt(hd) };
      });
      const endDate = new Date();
      endDate.setDate(endDate.getDate() + duration);
      await fetchJson(`${API_BASE}/lab/study`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: studyName,
          strategies,
          capital,
          risk_pct: riskPct,
          max_positions: maxPos,
          planned_end_date: endDate.toISOString().slice(0, 10),
        }),
      });
      setSent(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  const sortedRanked = [...ranked].sort((a, b) => {
    if (sortField === 'rank') return (a.rank || 999) - (b.rank || 999);
    if (sortField === 'expectancy') return (b.median_net_expectancy || 0) - (a.median_net_expectancy || 0);
    if (sortField === 'trades') return (b.total_trades || 0) - (a.total_trades || 0);
    if (sortField === 'cagr') return (b.cagr_pct || 0) - (a.cagr_pct || 0);
    return 0;
  });

  if (loading) return <div className="text-center py-10 text-slate-400"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" /> Loading rankings…</div>;

  return (
    <div className="space-y-5">
      <DisclaimerBanner />
      {error && <div className="px-4 py-3 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-sm">{error}</div>}
      {sent && <div className="px-4 py-3 rounded-lg bg-emerald-950/40 border border-emerald-800/40 text-emerald-300 text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Paper study created successfully. View it in the Paper tab.</div>}

      {/* Sort control */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-slate-400">Sort by:</span>
        {['rank', 'expectancy', 'trades', 'cagr'].map(f => (
          <button key={f} onClick={() => setSortField(f)}
            className={`px-2.5 py-1 rounded capitalize transition-colors ${sortField === f ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {f === 'expectancy' ? 'Exp R' : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-500">{selected.size}/5 selected</span>
      </div>

      {/* Results table */}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm text-slate-200">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/80 text-xs text-slate-400">
              <th className="px-3 py-2.5 text-left w-8"></th>
              <th className="px-3 py-2.5 text-left">Rank</th>
              <th className="px-3 py-2.5 text-left">Strategy</th>
              <th className="px-3 py-2.5 text-center">Hold</th>
              <th className="px-3 py-2.5 text-right">Trades</th>
              <th className="px-3 py-2.5 text-right">Win%</th>
              <th className="px-3 py-2.5 text-right">Exp R</th>
              <th className="px-3 py-2.5 text-right">PF</th>
              <th className="px-3 py-2.5 text-right">CAGR</th>
              <th className="px-3 py-2.5 text-right">MDD</th>
              <th className="px-3 py-2.5 text-left">Sample</th>
            </tr>
          </thead>
          <tbody>
            {sortedRanked.length === 0 && (
              <tr><td colSpan={11} className="px-4 py-8 text-center text-slate-500">No results yet. Run backtests in the Backtest tab.</td></tr>
            )}
            {sortedRanked.map(r => {
              const key = `${r.strategy_id}-${r.holding_days}`;
              const isSel = selected.has(key);
              return (
                <tr key={key}
                  onClick={() => r.sample_ok && toggleSelect(key)}
                  className={`border-b border-slate-800/60 transition-colors cursor-pointer
                    ${isSel ? 'bg-indigo-950/40' : 'hover:bg-slate-800/40'}
                    ${!r.sample_ok ? 'opacity-50 cursor-not-allowed' : ''}`}>
                  <td className="px-3 py-2.5 text-center">
                    {isSel ? <CheckCircle2 className="w-4 h-4 text-indigo-400" /> : <CircleDot className="w-4 h-4 text-slate-600" />}
                  </td>
                  <td className="px-3 py-2.5 text-slate-400">
                    {r.rank ? <span className="flex items-center gap-1">{r.rank === 1 && <Trophy className="w-3.5 h-3.5 text-amber-400" />}#{r.rank}</span> : '—'}
                    {r.auto_selected && <span className="ml-1 text-[10px] text-indigo-400">●auto</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="text-indigo-400 font-mono text-xs">{r.strategy_id}</span>
                    <span className="text-slate-300 ml-2">{r.ranking_note?.includes('Rank') ? '' : r.ranking_note}</span>
                  </td>
                  <td className="px-3 py-2.5 text-center text-slate-300">{r.holding_days}d</td>
                  <td className="px-3 py-2.5 text-right">{fmtN(r.total_trades)}</td>
                  <td className="px-3 py-2.5 text-right">{r.win_rate ? `${(r.win_rate * 100).toFixed(1)}%` : '—'}</td>
                  <td className={`px-3 py-2.5 text-right font-medium ${(r.expectancy_r || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fmtR(r.expectancy_r)}</td>
                  <td className="px-3 py-2.5 text-right">{r.profit_factor?.toFixed(2) || '—'}</td>
                  <td className={`px-3 py-2.5 text-right ${(r.cagr_pct || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fmtPct(r.cagr_pct)}</td>
                  <td className="px-3 py-2.5 text-right text-red-400">{fmtPct(r.max_drawdown_pct)}</td>
                  <td className="px-3 py-2.5">{sampleBadge(r.sample_ok, r.sample_label)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Send to paper */}
      <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 space-y-4">
        <h3 className="font-semibold text-white flex items-center gap-2"><Send className="w-4 h-4 text-indigo-400" /> Freeze & Send to Forward Paper</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="col-span-2">
            <label className="block text-xs text-slate-400 mb-1">Study Name *</label>
            <input
              value={studyName}
              onChange={e => setStudyName(e.target.value)}
              placeholder="e.g. Swing Lab 2027-Q1"
              className="w-full px-3 py-2 rounded bg-slate-800 border border-slate-700 text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Duration (days)</label>
            <input type="number" value={duration} onChange={e => setDuration(Number(e.target.value))}
              className="w-full px-3 py-2 rounded bg-slate-800 border border-slate-700 text-white text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Capital (₹)</label>
            <input type="number" value={capital} onChange={e => setCapital(Number(e.target.value))}
              className="w-full px-3 py-2 rounded bg-slate-800 border border-slate-700 text-white text-sm" />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-400">
            {selected.size > 0 ? (
              <span>Selected: {[...selected].join(', ')}</span>
            ) : (
              <span className="text-orange-400">Select strategies from the table above (max 5)</span>
            )}
          </div>
          <button
            onClick={sendToPaper}
            disabled={sending || selected.size === 0 || !studyName.trim()}
            className="flex items-center gap-2 px-5 py-2 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm disabled:opacity-50"
          >
            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Freeze & Create Study
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Tab: Paper & Manual Plan ─────────────────────────────────────────────────

const PaperTab: React.FC = () => {
  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [selectedStudyId, setSelectedStudyId] = useState<string | null>(null);
  const [studyDetail, setStudyDetail] = useState<StudyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<any[]>([]);
  const [planLoading, setPlanLoading] = useState(false);

  const loadStudies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJson<StudySummary[]>(`${API_BASE}/lab/study`);
      setStudies(data);
      if (data.length > 0 && !selectedStudyId) setSelectedStudyId(data[0].id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedStudyId]);

  useEffect(() => { loadStudies(); }, []);

  useEffect(() => {
    if (!selectedStudyId) return;
    setDetailLoading(true);
    fetchJson<StudyDetail>(`${API_BASE}/lab/study/${selectedStudyId}`)
      .then(setStudyDetail)
      .catch(e => setError(e.message))
      .finally(() => setDetailLoading(false));
  }, [selectedStudyId]);

  useEffect(() => {
    setPlanLoading(true);
    fetchJson<{ items: any[] }>(`${API_BASE}/lab/plan`)
      .then(d => setPlan(d.items || []))
      .catch(() => {})
      .finally(() => setPlanLoading(false));
  }, []);

  const executeItem = async (id: number, price: number, qty: number) => {
    try {
      await fetchJson(`${API_BASE}/lab/plan/${id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ executed_price: price, executed_qty: qty }),
      });
      const d = await fetchJson<{ items: any[] }>(`${API_BASE}/lab/plan`);
      setPlan(d.items || []);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const skipItem = async (id: number) => {
    try {
      await fetchJson(`${API_BASE}/lab/plan/${id}/skip`, { method: 'POST' });
      const d = await fetchJson<{ items: any[] }>(`${API_BASE}/lab/plan`);
      setPlan(d.items || []);
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (loading) return <div className="text-center py-10 text-slate-400"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" /></div>;

  return (
    <div className="space-y-5">
      <DisclaimerBanner />
      {error && <div className="px-4 py-3 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-sm">{error}</div>}

      {/* Study selector */}
      {studies.length === 0 ? (
        <div className="text-center py-10 text-slate-400 space-y-2">
          <FlaskConical className="w-10 h-10 mx-auto text-slate-600" />
          <p>No forward paper studies yet.</p>
          <p className="text-sm">Complete backtests and use the <strong>Rank & Send</strong> tab to create a study.</p>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 flex-wrap">
            {studies.map(s => (
              <button
                key={s.id}
                onClick={() => setSelectedStudyId(s.id)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${selectedStudyId === s.id ? 'bg-indigo-600 text-white' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'}`}
              >
                <span className={`w-2 h-2 rounded-full ${s.status === 'ACTIVE' ? 'bg-emerald-400' : 'bg-slate-400'}`} />
                {s.name}
                {s.kill_switch_triggered && <AlertTriangle className="w-3.5 h-3.5 text-red-400" />}
              </button>
            ))}
          </div>

          {detailLoading && <div className="text-center py-6 text-slate-400"><Loader2 className="w-5 h-5 animate-spin mx-auto" /></div>}

          {studyDetail && !detailLoading && (
            <div className="space-y-5">
              {/* Stale data warning banner */}
              {studyDetail.staleness?.is_stale && (
                <div className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-950/40 border border-amber-800/80 text-amber-300 text-xs">
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-400" />
                  <div>
                    <strong>Stale Market Data Notice:</strong> Market data is through{' '}
                    <span className="font-mono font-bold text-white">{studyDetail.staleness.last_data_date || 'N/A'}</span>{' '}
                    ({studyDetail.staleness.missed_sessions} missed trading session{studyDetail.staleness.missed_sessions !== 1 ? 's' : ''}). Forward paper evaluation is suspended until market bars are refreshed.
                  </div>
                </div>
              )}

              {/* Study summary */}
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                {[
                  { label: 'Status', value: studyDetail.status },
                  { label: 'Start Date', value: studyDetail.start_date },
                  { label: 'Capital', value: fmtINR(studyDetail.capital) },
                  { label: 'Kill Switch', value: studyDetail.kill_switch_triggered ? '🛑 TRIGGERED' : '✓ OK' },
                  { label: 'Data Through', value: studyDetail.data_through_date || '—' },
                  { label: 'Last Evaluated', value: studyDetail.last_evaluated_at ? new Date(studyDetail.last_evaluated_at).toLocaleDateString() : '—' },
                ].map(({ label, value }) => (
                  <div key={label} className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                    <div className="text-xs text-slate-400 mb-1">{label}</div>
                    <div className="font-semibold text-white text-sm">{value}</div>
                  </div>
                ))}
              </div>

              {/* Equity curves per strategy */}
              {studyDetail.strategies.map(entry => {
                const sid = entry.strategy_id;
                const dailyRows = studyDetail.daily.filter(d => d.strategy_id === sid);
                const checklist = studyDetail.promotion_checklists?.[sid];
                const lastRow = dailyRows[dailyRows.length - 1];
                return (
                  <div key={sid} className="rounded-lg bg-slate-900/60 border border-slate-800 overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
                      <div>
                        <span className="text-indigo-400 font-mono text-sm mr-2">{sid}</span>
                        <span className="text-white text-sm">{entry.holding_days}d hold</span>
                      </div>
                      {lastRow && (
                        <div className="flex gap-4 text-sm">
                          <span className="text-slate-400">Equity: <span className="text-white">{fmtINR(lastRow.total_equity)}</span></span>
                          <span className={lastRow.cumulative_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                            {fmtPct(lastRow.cumulative_return_pct)}
                          </span>
                          <span className="text-red-400">MDD: {fmtPct(lastRow.drawdown_pct)}</span>
                        </div>
                      )}
                    </div>
                    <div className="px-4 py-3">
                      {dailyRows.length === 0 ? (
                        <p className="text-slate-500 text-sm">No daily data yet — waiting for first EOD evaluation.</p>
                      ) : (
                        <div className="text-xs text-slate-400">{dailyRows.length} sessions tracked</div>
                      )}
                      {/* Promotion checklist */}
                      {checklist && (
                        <div className="mt-3 space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-slate-300">Promotion Checklist:</span>
                            <span className={`text-xs px-2 py-0.5 rounded font-bold
                              ${checklist.overall === 'GREEN' ? 'bg-emerald-900/50 text-emerald-300' :
                                checklist.overall === 'AMBER' ? 'bg-amber-900/50 text-amber-300' :
                                'bg-red-900/50 text-red-300'}`}>
                              {checklist.overall}
                            </span>
                            <span className="text-xs text-slate-500">(owner can override)</span>
                          </div>
                          {Object.entries(checklist.gates || {}).map(([k, g]: [string, any]) => (
                            <div key={k} className="flex items-center gap-2 text-xs">
                              {g.passed === true ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" /> :
                               g.passed === false ? <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" /> :
                               <CircleDot className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />}
                              <span className="text-slate-300">{g.label}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Recent trades */}
              {studyDetail.recent_trades.length > 0 && (
                <div className="rounded-lg bg-slate-900/60 border border-slate-800 overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-800 font-semibold text-sm text-white">Recent Paper Trades</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400">
                          <th className="px-3 py-2 text-left">Date</th>
                          <th className="px-3 py-2 text-left">Strategy</th>
                          <th className="px-3 py-2 text-left">Symbol</th>
                          <th className="px-3 py-2 text-center">Side</th>
                          <th className="px-3 py-2 text-right">Qty</th>
                          <th className="px-3 py-2 text-right">Fill</th>
                          <th className="px-3 py-2 text-right">PnL</th>
                          <th className="px-3 py-2 text-right">R</th>
                          <th className="px-3 py-2 text-left">Exit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {studyDetail.recent_trades.slice(0, 20).map((t, i) => (
                          <tr key={i} className="border-b border-slate-800/40 hover:bg-slate-800/20">
                            <td className="px-3 py-2 text-slate-400">{t.exec_date}</td>
                            <td className="px-3 py-2 text-indigo-400 font-mono">{t.strategy_id}</td>
                            <td className="px-3 py-2 text-white font-medium">{t.symbol}</td>
                            <td className={`px-3 py-2 text-center font-medium ${t.side === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>{t.side}</td>
                            <td className="px-3 py-2 text-right text-slate-300">{t.qty}</td>
                            <td className="px-3 py-2 text-right text-slate-300">{fmtINR(t.fill_price)}</td>
                            <td className={`px-3 py-2 text-right font-medium ${(t.realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fmtINR(t.realized_pnl)}</td>
                            <td className={`px-3 py-2 text-right font-medium ${(t.r_multiple || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fmtR(t.r_multiple)}</td>
                            <td className="px-3 py-2 text-slate-400">{t.exit_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Today's Manual Plan */}
      <div className="rounded-lg bg-slate-900/60 border border-slate-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <span className="font-semibold text-sm text-white">Today's Manual Trading Plan</span>
          <span className="text-xs text-orange-400 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Manual execution only. No broker orders.</span>
        </div>
        {planLoading ? (
          <div className="px-4 py-6 text-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin mx-auto" /></div>
        ) : plan.length === 0 ? (
          <div className="px-4 py-6 text-center text-slate-500 text-sm">No plan items for today. Items are added by the system when signals trigger.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-xs text-slate-400">
                <th className="px-3 py-2 text-left">Strategy</th>
                <th className="px-3 py-2 text-left">Symbol</th>
                <th className="px-3 py-2 text-center">Action</th>
                <th className="px-3 py-2 text-right">Entry</th>
                <th className="px-3 py-2 text-right">Stop</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2 text-center">Status</th>
                <th className="px-3 py-2 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {plan.map(item => (
                <tr key={item.id} className="border-b border-slate-800/40 hover:bg-slate-800/20">
                  <td className="px-3 py-2.5 text-indigo-400 font-mono text-xs">{item.strategy_id}</td>
                  <td className="px-3 py-2.5 font-semibold text-white">{item.symbol}</td>
                  <td className={`px-3 py-2.5 text-center font-medium ${item.action === 'BUY' ? 'text-emerald-400' : item.action === 'SELL' ? 'text-red-400' : 'text-amber-400'}`}>{item.action}</td>
                  <td className="px-3 py-2.5 text-right text-slate-300">{fmtINR(item.suggested_entry)}</td>
                  <td className="px-3 py-2.5 text-right text-red-400">{fmtINR(item.suggested_stop)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-300">{item.suggested_qty || '—'}</td>
                  <td className="px-3 py-2.5 text-center">
                    <span className={`text-xs px-2 py-0.5 rounded ${item.status === 'EXECUTED' ? 'bg-emerald-900/50 text-emerald-300' : item.status === 'SKIPPED' ? 'bg-slate-800 text-slate-500' : 'bg-amber-900/50 text-amber-300'}`}>
                      {item.status}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {item.status === 'PENDING' && (
                      <div className="flex items-center gap-2 justify-center">
                        <button onClick={() => { const p = prompt('Fill price?'); const q = prompt('Qty?'); if (p && q) executeItem(item.id, parseFloat(p), parseInt(q)); }} className="text-xs px-2 py-1 rounded bg-emerald-800 hover:bg-emerald-700 text-white">Execute</button>
                        <button onClick={() => skipItem(item.id)} className="text-xs px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-300">Skip</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

// ─── Main Page ────────────────────────────────────────────────────────────────

type TabId = 'backtest' | 'rank' | 'paper' | 'cards';

const TABS: Array<{ id: TabId; label: string; icon: React.ReactNode }> = [
  { id: 'backtest', label: 'Backtest', icon: <Activity className="w-4 h-4" /> },
  { id: 'rank', label: 'Rank & Send to Paper', icon: <ArrowUpDown className="w-4 h-4" /> },
  { id: 'paper', label: 'Paper & Manual Promotion', icon: <FlaskConical className="w-4 h-4" /> },
  { id: 'cards', label: 'Trade Cards', icon: <LayoutList className="w-4 h-4" /> },
];

export const StrategyLabPage: React.FC = () => {
  const [tab, setTab] = useState<TabId>('backtest');

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-indigo-400" />
          Strategy Lab
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Backtest 10 swing strategies on historical Indian NSE data, rank by evidence, and track forward paper performance.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-lg bg-slate-900/60 border border-slate-800 w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors
              ${tab === t.id ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {tab === 'backtest' && <BacktestTab />}
        {tab === 'rank' && <RankTab />}
        {tab === 'paper' && <PaperTab />}
        {tab === 'cards' && <TradeCardList />}
      </div>
    </div>
  );
};
