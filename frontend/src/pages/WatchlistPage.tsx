import React, { useEffect, useState } from 'react';
import { AlertCircle, Clock, ExternalLink, RefreshCw, Zap } from 'lucide-react';
import { apiClient } from '../api/client';

interface WatchlistPageProps {
  currentMarket: 'IN' | 'US';
}

export const WatchlistPage: React.FC<WatchlistPageProps> = ({ currentMarket }) => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchWatchlist = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getWatchlist(currentMarket);
      setItems(data || []);
    } catch (e) {
      console.error('Error fetching watchlist:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWatchlist();
    const interval = setInterval(fetchWatchlist, 15000);
    return () => clearInterval(interval);
  }, [currentMarket]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Clock className="w-5 h-5 text-indigo-400" />
            Watchlist & Live Breakout Monitor
          </h1>
          <p className="text-xs text-slate-400">
            Real-time price feed and state monitoring for shortlisted candidates and active positions.
          </p>
        </div>
        <button
          onClick={fetchWatchlist}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Quotes
        </button>
      </div>

      {loading && items.length === 0 ? (
        <div className="h-64 bg-slate-900 border border-slate-800 rounded-xl animate-pulse"></div>
      ) : items.length === 0 ? (
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-12 text-center text-slate-400 text-sm">
          No candidates currently on active watchlist. Run today's scan from the Dashboard to populate candidates.
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 uppercase font-bold border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Symbol</th>
                  <th className="px-4 py-3">Setup</th>
                  <th className="px-4 py-3">State</th>
                  <th className="px-4 py-3">Last Price</th>
                  <th className="px-4 py-3">Trigger</th>
                  <th className="px-4 py-3">Dist to Trigger</th>
                  <th className="px-4 py-3">Stop Loss</th>
                  <th className="px-4 py-3">Dist to Stop</th>
                  <th className="px-4 py-3">Source / Freshness</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {items.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 font-bold text-white font-sans text-sm">
                      {row.symbol}
                    </td>
                    <td className="px-4 py-3 font-sans text-indigo-300">
                      {row.setup}
                    </td>
                    <td className="px-4 py-3 font-sans">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                          row.state === 'TRIGGERED_PROVISIONAL' || row.state === 'TRIGGERED_CONFIRMED'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : row.state === 'APPROACHING'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800 animate-pulse'
                            : 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {row.state}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-bold text-slate-100">
                      {row.last_price?.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-emerald-400">
                      {row.trigger?.toFixed(2)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`font-semibold ${row.distance_to_trigger_pct <= 1.5 ? 'text-amber-400' : 'text-slate-300'}`}>
                        {row.distance_to_trigger_pct > 0 ? `${row.distance_to_trigger_pct.toFixed(2)}% below` : `${Math.abs(row.distance_to_trigger_pct).toFixed(2)}% above`}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-rose-400">
                      {row.stop?.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {row.distance_to_stop_pct?.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 font-sans text-[11px]">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${row.is_stale ? 'bg-amber-500' : 'bg-emerald-400'}`}></span>
                        <span className="text-slate-400">{row.source}</span>
                        {row.is_stale && <span className="text-amber-400 text-[10px]">(STALE)</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

