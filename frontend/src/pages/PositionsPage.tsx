import React, { useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, BarChart2, CheckCircle2, Clock, Edit3, LogOut, RefreshCw, ShieldAlert, Wallet } from 'lucide-react';
import { apiClient } from '../api/client';
import { RecordExitModal } from '../components/RecordExitModal';
import { Position } from '../types';

interface PositionsPageProps {
  currentMarket: 'IN' | 'US';
}

export const PositionsPage: React.FC<PositionsPageProps> = ({ currentMarket }) => {
  const [positions, setPositions] = useState<Position[]>([]);
  const [valuation, setValuation] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [exitModalPos, setExitModalPos] = useState<Position | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [posData, valData] = await Promise.all([
        apiClient.getPositions('OPEN', currentMarket),
        apiClient.getPortfolioValuation(),
      ]);
      setPositions(posData || []);
      setValuation(valData);
    } catch (e) {
      console.error('Error loading positions & valuation:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSyncKite = async () => {
    try {
      setSyncing(true);
      await apiClient.syncPortfolio();
      await loadData();
    } catch (e) {
      alert('Error syncing portfolio: ' + e);
    } finally {
      setSyncing(false);
    }
  };

  const handleRecordExitSubmit = async (data: any) => {
    try {
      await apiClient.closePosition(data.position_id, data);
      setExitModalPos(null);
      await loadData();
      alert('Exit logged successfully and saved to Trade Journal!');
    } catch (e) {
      alert('Error closing position: ' + e);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentMarket]);

  return (
    <div className="flex flex-col gap-6">
      {/* Header & Sync */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-indigo-400" />
            Active Positions & Portfolio Valuation
          </h1>
          <p className="text-xs text-slate-400">
            Track active swing trades and compare broker-reported vs live Angel One estimated P&L.
          </p>
        </div>
        <button
          onClick={handleSyncKite}
          disabled={syncing}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-semibold text-white shadow"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing Kite...' : 'Sync Zerodha Holdings'}
        </button>
      </div>

      {/* Portfolio Valuation Cards (Provenance Highlight) */}
      {valuation && valuation.summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Total Capital Invested</span>
            <span className="text-xl font-bold font-mono text-white">
              ₹{valuation.summary.total_invested?.toLocaleString('en-IN')}
            </span>
            <span className="text-[10px] text-slate-500 block mt-1">Source: Zerodha Personal</span>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Broker-Reported Value</span>
            <span className="text-xl font-bold font-mono text-slate-200">
              ₹{valuation.summary.broker_reported_value?.toLocaleString('en-IN')}
            </span>
            <span className="text-[10px] text-slate-500 block mt-1">Zerodha EOD/Snapshot</span>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Calculated Live Estimated Value</span>
            <span className="text-xl font-bold font-mono text-indigo-300">
              ₹{valuation.summary.calculated_live_value?.toLocaleString('en-IN')}
            </span>
            <span className={`text-xs font-bold block mt-1 ${valuation.summary.calculated_live_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              Estimated P&L: ₹{valuation.summary.calculated_live_pnl >= 0 ? '+' : ''}{valuation.summary.calculated_live_pnl?.toFixed(2)}
            </span>
          </div>
        </div>
      )}

      {/* Active Swing Positions Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            Active Swing Positions ({positions.length})
          </h2>
          <span className="text-xs text-slate-400">Orders placed manually at broker</span>
        </div>

        {positions.length === 0 ? (
          <div className="p-10 text-center text-slate-400 text-xs">
            No active open swing positions. When you take a trade from the Dashboard, click "I Took This Trade" to log it here.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 uppercase font-bold border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Symbol</th>
                  <th className="px-4 py-3">Entry Date</th>
                  <th className="px-4 py-3">Entry Price</th>
                  <th className="px-4 py-3">Qty</th>
                  <th className="px-4 py-3">Active Stop</th>
                  <th className="px-4 py-3">Target 1</th>
                  <th className="px-4 py-3">Live Price</th>
                  <th className="px-4 py-3">Unrealized P&L</th>
                  <th className="px-4 py-3">R-Multiple</th>
                  <th className="px-4 py-3">Days</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {positions.map((pos) => {
                  const isProfit = pos.unrealized_pnl >= 0;
                  return (
                    <tr key={pos.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-4 py-3 font-bold text-white font-sans text-sm">
                        {pos.symbol}
                        <span className="text-[10px] text-slate-500 block font-normal">{pos.source}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-400">{pos.entry_date}</td>
                      <td className="px-4 py-3 text-slate-200">{pos.entry_price.toFixed(2)}</td>
                      <td className="px-4 py-3 text-indigo-300 font-semibold">{pos.qty}</td>
                      <td className="px-4 py-3 text-rose-400 font-semibold">{pos.active_stop.toFixed(2)}</td>
                      <td className="px-4 py-3 text-cyan-400">{pos.target1.toFixed(2)}</td>
                      <td className="px-4 py-3 text-slate-100 font-bold">{pos.current_price?.toFixed(2)}</td>
                      <td className={`px-4 py-3 font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {isProfit ? '+' : ''}{pos.unrealized_pnl?.toFixed(2)} ({pos.unrealized_pct?.toFixed(1)}%)
                      </td>
                      <td className={`px-4 py-3 font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {pos.unrealized_r >= 0 ? '+' : ''}{pos.unrealized_r?.toFixed(2)}R
                      </td>
                      <td className="px-4 py-3 text-slate-400 font-sans">{pos.days_held}d</td>
                      <td className="px-4 py-3 text-right font-sans">
                        <button
                          onClick={() => setExitModalPos(pos)}
                          className="flex items-center gap-1 ml-auto px-2.5 py-1 rounded bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 text-xs font-semibold transition-colors"
                        >
                          <LogOut className="w-3 h-3" /> Record Exit
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Record Exit Modal */}
      {exitModalPos && (
        <RecordExitModal
          position={exitModalPos}
          onClose={() => setExitModalPos(null)}
          onSubmit={handleRecordExitSubmit}
        />
      )}
    </div>
  );
};

