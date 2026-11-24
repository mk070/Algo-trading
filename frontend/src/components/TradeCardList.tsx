/**
 * TradeCardList — paginated list of backtest or paper trade cards with filters.
 *
 * Features:
 * - Filter bar: Strategy, Status (OPEN/CLOSED), Source (Backtest/Paper)
 * - Groups: OPEN first, then CLOSED newest-first
 * - Pagination: 50 per page; manual Refresh (no auto-poll <60s)
 * - Summary header: open count, closed count, win rate, net PnL, expectancy R
 * - Disclaimer and empty/loading/error states
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, ChevronLeft, ChevronRight, Filter,
  Loader2, RefreshCw, TrendingUp,
} from 'lucide-react';
import { TradeCard, TradeCardData } from './TradeCard';
import { API_BASE, fetchJson } from '../api/client';

interface TradeCardListProps {
  /** If set, pre-filter to this study only. */
  studyId?: string;
  /** Initial source filter. */
  defaultSource?: 'all' | 'backtest' | 'paper';
  className?: string;
}

const PAGE_SIZE = 50;
const REFRESH_DEBOUNCE_MS = 60_000;

function computeSummary(trades: TradeCardData[]) {
  const closed = trades.filter(t => !!t.exit_date || (t.side === 'SELL' && !!t.exec_date));
  const open = trades.filter(t => !t.exit_date && !(t.side === 'SELL' && !!t.exec_date));
  const wins = closed.filter(t => (t.net_pnl ?? 0) > 0);
  const totalPnl = closed.reduce((s, t) => s + (t.net_pnl ?? 0), 0);
  const expectancyR =
    closed.length > 0
      ? closed.reduce((s, t) => s + (t.r_multiple ?? 0), 0) / closed.length
      : null;
  return {
    openCount: open.length,
    closedCount: closed.length,
    winRate: closed.length > 0 ? (wins.length / closed.length) * 100 : null,
    totalPnl,
    expectancyR,
  };
}

export const TradeCardList: React.FC<TradeCardListProps> = ({
  studyId,
  defaultSource = 'all',
  className = '',
}) => {
  const [trades, setTrades] = useState<TradeCardData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [lastRefresh, setLastRefresh] = useState(0);

  // Filters
  const [sourceFilter, setSourceFilter] = useState<'all' | 'backtest' | 'paper'>(defaultSource);
  const [strategyFilter, setStrategyFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'closed'>('all');

  const load = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastRefresh < REFRESH_DEBOUNCE_MS) return;

    setLoading(true);
    setError(null);
    try {
      const results: TradeCardData[] = [];
      let paperTotal = 0;
      let backtestTotal = 0;

      if (sourceFilter !== 'backtest') {
        // Load paper trades
        const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
        if (studyId) qs.set('study_id', studyId);
        if (strategyFilter) qs.set('strategy_id', strategyFilter);
        const r = await fetchJson<{ total: number; items: TradeCardData[] }>(
          `${API_BASE}/lab/trades/paper?${qs}`
        );
        paperTotal = r.total;
        results.push(...r.items);
      }

      setTrades(results);
      setTotal(paperTotal + backtestTotal);
      setLastRefresh(Date.now());
    } catch (e: any) {
      setError(e.message || 'Failed to load trades');
    } finally {
      setLoading(false);
    }
  }, [studyId, sourceFilter, strategyFilter, statusFilter, page, lastRefresh]);

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId, sourceFilter, strategyFilter, statusFilter, page]);

  // Apply client-side status filter
  const filtered = trades.filter(t => {
    const isExited = !!t.exit_date || (t.side === 'SELL' && !!t.exec_date);
    if (statusFilter === 'open' && isExited) return false;
    if (statusFilter === 'closed' && !isExited) return false;
    return true;
  });

  // Sort: open first, then newest
  const sorted = [...filtered].sort((a, b) => {
    const aExited = !!a.exit_date || (a.side === 'SELL' && !!a.exec_date);
    const bExited = !!b.exit_date || (b.side === 'SELL' && !!b.exec_date);
    if (!aExited && bExited) return -1;
    if (aExited && !bExited) return 1;
    const dateA = a.exit_date || a.exec_date || a.signal_date || '';
    const dateB = b.exit_date || b.exec_date || b.signal_date || '';
    return dateB.localeCompare(dateA);
  });

  const summary = computeSummary(sorted);
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Disclaimer */}
      <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-950/30 border border-amber-900/40 text-amber-300 text-xs">
        <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        <span>
          ⚠ <strong>Survivorship bias:</strong> results use the current NSE universe, not the universe
          as it existed on the signal date. Past strategy performance does not guarantee future results.
          No broker orders are placed. Manual execution only.
        </span>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex items-center gap-1.5 text-slate-400 text-xs">
          <Filter className="w-3.5 h-3.5" />
          <span>Filter:</span>
        </div>

        <select
          value={sourceFilter}
          onChange={e => { setSourceFilter(e.target.value as any); setPage(1); }}
          className="text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded-md px-2 py-1"
        >
          <option value="all">All sources</option>
          <option value="paper">Paper only</option>
          <option value="backtest">Backtest only</option>
        </select>

        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value as any); setPage(1); }}
          className="text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded-md px-2 py-1"
        >
          <option value="all">All status</option>
          <option value="open">Open only</option>
          <option value="closed">Closed only</option>
        </select>

        <input
          type="text"
          value={strategyFilter}
          onChange={e => { setStrategyFilter(e.target.value); setPage(1); }}
          placeholder="Strategy (S01…)"
          className="text-xs bg-slate-800 border border-slate-700 text-slate-200 rounded-md px-2 py-1 w-28"
        />

        <button
          onClick={() => load(true)}
          disabled={loading}
          className="ml-auto flex items-center gap-1 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 rounded-md px-2.5 py-1 transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Refresh
        </button>
      </div>

      {/* Summary */}
      {sorted.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-center">
            <div className="text-blue-400 font-bold text-lg">{summary.openCount}</div>
            <div className="text-slate-500 text-xs mt-0.5">Open</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-center">
            <div className="text-slate-300 font-bold text-lg">{summary.closedCount}</div>
            <div className="text-slate-500 text-xs mt-0.5">Closed</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-center">
            <div className={`font-bold text-lg ${(summary.winRate ?? 0) >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
              {summary.winRate != null ? `${summary.winRate.toFixed(0)}%` : '—'}
            </div>
            <div className="text-slate-500 text-xs mt-0.5">Win rate</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-center">
            <div className={`font-bold text-lg font-mono ${summary.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {summary.totalPnl >= 0 ? '+' : ''}₹{Math.abs(summary.totalPnl).toFixed(0)}
            </div>
            <div className="text-slate-500 text-xs mt-0.5">Net PnL</div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 rounded-lg bg-red-950/30 border border-red-900/40 text-red-300 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12 text-slate-500">
          <Loader2 className="w-6 h-6 animate-spin mr-2" />
          <span>Loading trades…</span>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && sorted.length === 0 && (
        <div className="text-center py-16 text-slate-500">
          <TrendingUp className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="font-medium">No paper trades yet</p>
          <p className="text-sm mt-1 text-slate-600">
            Start a study and trigger an evaluation to see trade cards here.
          </p>
        </div>
      )}

      {/* Trade cards */}
      {!loading && sorted.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {sorted.map(trade => (
            <TradeCard key={`${trade.source}-${trade.id}`} trade={trade} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 disabled:opacity-30 transition-colors"
          >
            <ChevronLeft className="w-4 h-4 text-slate-300" />
          </button>
          <span className="text-sm text-slate-400">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 disabled:opacity-30 transition-colors"
          >
            <ChevronRight className="w-4 h-4 text-slate-300" />
          </button>
        </div>
      )}
    </div>
  );
};
