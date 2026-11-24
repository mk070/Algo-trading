/**
 * TradeCard — reusable card for displaying a single backtest or paper trade.
 *
 * Shows: symbol, strategy, signal/entry/exit dates + prices, stop price,
 * planned exit, net PnL, R-multiple, days held, reason text, status badge.
 * Clicking opens the ChartModal with trade chart data.
 */
import React, { useState } from 'react';
import {
  ArrowUpRight, BarChart3, Calendar, ChevronRight,
  TrendingDown, TrendingUp, X,
} from 'lucide-react';
import { ChartModal } from './ChartModal';

export interface TradeCardData {
  id: number;
  source: 'backtest' | 'paper';
  study_id?: string;
  strategy_id: string;
  symbol: string;
  side?: string;
  qty: number;
  exec_date?: string;    // paper SELL exec date (exit date)
  signal_date?: string;
  entry_date?: string;   // for backtest
  exit_date?: string;    // for backtest
  entry_price?: number;
  fill_price?: number;   // paper entry fill price
  exit_price?: number;   // backtest exit price
  stop_price?: number;
  planned_exit_date?: string;
  holding_days_target?: number;
  net_pnl?: number | null;
  gross_pnl?: number | null;
  r_multiple?: number | null;
  exit_reason?: string | null;
  reason_text?: string | null;
  trade_key?: string;
  data_through_date?: string | null;
  evaluated_at?: string | null;
}

function statusBadge(trade: TradeCardData) {
  const isOpen = !trade.exit_date && !trade.exec_date;
  const isWin = (trade.net_pnl ?? 0) > 0;
  const isExited = !!trade.exit_date || !!trade.exec_date;

  if (!isExited) {
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-900/50 text-blue-300 border border-blue-700">
        OPEN
      </span>
    );
  }
  if (isWin) {
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-900/50 text-emerald-300 border border-emerald-700">
        WIN
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-900/50 text-red-300 border border-red-700">
      LOSS
    </span>
  );
}

function exitReasonLabel(reason?: string | null): string {
  const map: Record<string, string> = {
    STOP_HIT: 'Stop hit',
    GAP_THROUGH_STOP: 'Gap-through stop',
    TIME_EXIT: 'Time exit (plan)',
    MANUAL: 'Manual exit',
  };
  return reason ? (map[reason] || reason) : '—';
}

export const TradeCard: React.FC<{ trade: TradeCardData; className?: string }> = ({
  trade,
  className = '',
}) => {
  const [chartOpen, setChartOpen] = useState(false);

  const entryPrice = trade.entry_price ?? trade.fill_price;
  const exitPrice = trade.exit_price;
  const entryDate = trade.entry_date ?? (trade.side === 'BUY' ? trade.exec_date : undefined);
  const exitDate = trade.exit_date ?? (trade.side === 'SELL' ? trade.exec_date : undefined);
  const netPnl = trade.net_pnl ?? 0;
  const isExited = !!exitDate;
  const isWin = netPnl > 0;

  return (
    <>
      <div
        className={`relative group bg-slate-900 border border-slate-800 hover:border-slate-600 rounded-xl p-4 cursor-pointer transition-all ${className}`}
        onClick={() => setChartOpen(true)}
      >
        {/* Header row */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-bold text-white font-mono text-sm truncate">{trade.symbol}</span>
            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-800 text-slate-400 border border-slate-700 shrink-0">
              {trade.source === 'paper' ? 'PAPER' : 'BACKTEST'}
            </span>
            <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-indigo-900/40 text-indigo-300 border border-indigo-800 shrink-0">
              {trade.strategy_id}
            </span>
            {trade.holding_days_target && (
              <span className="text-[9px] text-slate-500 shrink-0">H{trade.holding_days_target}</span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {statusBadge(trade)}
            <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-400 transition-colors" />
          </div>
        </div>

        {/* Reason text */}
        {trade.reason_text && (
          <p className="text-xs text-slate-400 mb-3 leading-relaxed line-clamp-2">
            {trade.reason_text}
          </p>
        )}

        {/* Price / date grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-xs mb-3">
          {trade.signal_date && (
            <div>
              <span className="text-slate-500 block">Signal</span>
              <span className="text-slate-300 font-mono">{trade.signal_date}</span>
            </div>
          )}
          {entryDate && (
            <div>
              <span className="text-slate-500 block">Entry</span>
              <span className="text-slate-300 font-mono">{entryDate}</span>
            </div>
          )}
          {entryPrice != null && (
            <div>
              <span className="text-slate-500 block">Entry ₹</span>
              <span className="text-emerald-400 font-mono font-semibold">
                {entryPrice.toFixed(2)}
              </span>
            </div>
          )}
          {trade.stop_price != null && (
            <div>
              <span className="text-slate-500 block">Stop ₹</span>
              <span className="text-red-400 font-mono">
                {trade.stop_price.toFixed(2)}
                {entryPrice && (
                  <span className="text-slate-500 ml-1">
                    ({(((trade.stop_price - entryPrice) / entryPrice) * 100).toFixed(1)}%)
                  </span>
                )}
              </span>
            </div>
          )}
          {trade.planned_exit_date && (
            <div>
              <span className="text-slate-500 block">Planned exit</span>
              <span className="text-amber-400 font-mono">{trade.planned_exit_date}</span>
            </div>
          )}
          {isExited && exitDate && (
            <div>
              <span className="text-slate-500 block">Exited</span>
              <span className="text-slate-300 font-mono">{exitDate}</span>
            </div>
          )}
          {isExited && exitPrice != null && (
            <div>
              <span className="text-slate-500 block">Exit ₹</span>
              <span className="text-slate-300 font-mono">{exitPrice.toFixed(2)}</span>
            </div>
          )}
          {isExited && trade.exit_reason && (
            <div>
              <span className="text-slate-500 block">Reason</span>
              <span className={`text-xs ${trade.exit_reason?.includes('STOP') ? 'text-red-400' : 'text-blue-400'}`}>
                {exitReasonLabel(trade.exit_reason)}
              </span>
            </div>
          )}
        </div>

        {/* PnL / R footer */}
        {isExited && (
          <div className="flex items-center gap-4 pt-2 border-t border-slate-800">
            <div className="flex items-center gap-1.5">
              {isWin ? (
                <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <TrendingDown className="w-3.5 h-3.5 text-red-400" />
              )}
              <span className={`font-bold text-sm font-mono ${isWin ? 'text-emerald-400' : 'text-red-400'}`}>
                {netPnl >= 0 ? '+' : ''}₹{netPnl.toFixed(0)}
              </span>
            </div>
            {trade.r_multiple != null && (
              <span className={`text-xs font-mono ${trade.r_multiple >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                {trade.r_multiple >= 0 ? '+' : ''}{trade.r_multiple.toFixed(2)}R
              </span>
            )}
            <div className="ml-auto flex items-center gap-1 text-slate-500 text-xs">
              <BarChart3 className="w-3 h-3" />
              <span>Click to chart</span>
            </div>
          </div>
        )}
        {!isExited && (
          <div className="flex items-center justify-end gap-1 text-slate-600 text-xs pt-2 border-t border-slate-800">
            <BarChart3 className="w-3 h-3" />
            <span>Click to chart</span>
          </div>
        )}

        {/* Card footer: data through date */}
        <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1.5 border-t border-slate-800/60 mt-2">
          <span>Data through: <span className="text-slate-400 font-mono">{trade.data_through_date || trade.exec_date || trade.entry_date || '—'}</span></span>
          {trade.source === 'paper' && (
            <span className="text-slate-500">Forward Paper</span>
          )}
        </div>
      </div>

      {/* Chart modal */}
      <ChartModal
        isOpen={chartOpen}
        onClose={() => setChartOpen(false)}
        symbol={trade.symbol}
        market="IN"
        tradeContext={{
          tradeId: trade.id,
          tradeType: trade.source,
          signal_date: trade.signal_date,
          entry_date: entryDate,
          entry_price: entryPrice,
          exit_date: exitDate,
          stop_price: trade.stop_price,
          planned_exit_date: trade.planned_exit_date,
          reason_text: trade.reason_text,
        }}
      />
    </>
  );
};
