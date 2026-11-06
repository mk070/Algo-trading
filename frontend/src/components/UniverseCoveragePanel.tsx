import React, { useEffect, useState } from 'react';
import { Download, RefreshCw, ShieldAlert, CheckCircle2, AlertTriangle, Layers, Database } from 'lucide-react';
import { apiClient } from '../api/client';

interface UniverseCoverageProps {
  market: string;
}

export const UniverseCoveragePanel: React.FC<UniverseCoverageProps> = ({ market }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [downloading, setDownloading] = useState<boolean>(false);

  const fetchCoverage = async () => {
    try {
      setLoading(true);
      const res = await apiClient.getUniverseCoverage(market);
      setData(res);
    } catch (e) {
      console.error('Failed to load universe coverage:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCoverage();
  }, [market]);

  const handleDownloadCsv = async () => {
    try {
      setDownloading(true);
      const blob = await apiClient.exportUniverseCoverageCsv(market);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `universe_coverage_${market.toLowerCase()}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (e) {
      alert(`Download failed: ${e}`);
    } finally {
      setDownloading(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 flex items-center justify-center gap-3 text-slate-400">
        <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
        <span>Loading full-NSE universe coverage census...</span>
      </div>
    );
  }

  const items = data?.items || [];
  const filteredItems = statusFilter === 'ALL'
    ? items
    : items.filter((it: any) => it.status === statusFilter);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold text-white">Full-Universe Coverage Audit</h2>
            <span className="rounded bg-indigo-950 border border-indigo-800 px-2 py-0.5 text-[10px] font-mono text-indigo-300">
              {market === 'IN' ? 'NSE EQUITIES' : 'US EQUITIES'}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Transparent census: every listed instrument evaluated with explicit status. Never drop silently.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchCoverage}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={handleDownloadCsv}
            disabled={downloading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            {downloading ? 'Exporting...' : 'Export Coverage CSV'}
          </button>
        </div>
      </div>

      {/* Pipeline Stage Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
        {(data?.pipeline || []).map((st: any, idx: number) => (
          <div
            key={st.stage}
            className="rounded-lg border border-slate-800/80 bg-slate-950/50 p-2.5 flex flex-col justify-between"
          >
            <div className="flex items-center justify-between text-[10px] text-slate-400 font-medium">
              <span>{idx + 1}. {st.stage}</span>
            </div>
            <div className="mt-1">
              <span className="font-mono text-lg font-bold text-slate-100">{st.count}</span>
            </div>
            <p className="mt-1 text-[9px] text-slate-500 line-clamp-1" title={st.description}>
              {st.description}
            </p>
          </div>
        ))}
      </div>

      {/* Tier Breakdown & Status Pills */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs bg-slate-950/40 border border-slate-800/60 rounded-lg p-3">
        <div className="flex items-center gap-3">
          <span className="text-[10px] uppercase font-bold text-slate-400">Market Tiers:</span>
          <span className="font-mono text-slate-300">Large: <strong>{data?.tier_breakdown?.Large || 0}</strong></span>
          <span className="font-mono text-slate-300">Mid: <strong>{data?.tier_breakdown?.Mid || 0}</strong></span>
          <span className="font-mono text-slate-300">Small: <strong>{data?.tier_breakdown?.Small || 0}</strong></span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {['ALL', 'SCANNED', 'NO_DATA', 'INSUFFICIENT_HISTORY (<252 bars)', 'ILLIQUID', 'PRICE_FLOOR', 'VOLATILITY_CAP', 'SERIES_EXCLUDED'].map((stKey) => {
            const count = stKey === 'ALL'
              ? items.length
              : (data?.status_counts?.[stKey] || 0);
            return (
              <button
                key={stKey}
                onClick={() => setStatusFilter(stKey)}
                className={`px-2 py-1 rounded text-[10px] font-mono transition-colors ${
                  statusFilter === stKey
                    ? 'bg-indigo-600 text-white font-bold'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {stKey.replace(' (<252 bars)', '')} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {/* Symbol Table */}
      <div className="overflow-x-auto max-h-96 border border-slate-800 rounded-lg">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950 text-slate-400 uppercase font-bold sticky top-0 border-b border-slate-800">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Tier</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Price</th>
              <th className="px-3 py-2">20d Turnover</th>
              <th className="px-3 py-2">ATR%</th>
              <th className="px-3 py-2">Bars</th>
              <th className="px-3 py-2">Audit Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono">
            {filteredItems.slice(0, 100).map((it: any) => (
              <tr key={it.symbol} className="hover:bg-slate-800/40 transition-colors">
                <td className="px-3 py-2 font-bold text-slate-100 font-sans">
                  {it.symbol}
                  <span className="ml-1 text-[9px] text-slate-500 font-mono">({it.series})</span>
                </td>
                <td className="px-3 py-2">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                    it.tier === 'Large'
                      ? 'bg-blue-950 text-blue-300 border border-blue-800'
                      : it.tier === 'Mid'
                      ? 'bg-purple-950 text-purple-300 border border-purple-800'
                      : 'bg-slate-800 text-slate-400'
                  }`}>
                    {it.tier}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                    it.status === 'SCANNED'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : it.status === 'NO_DATA'
                      ? 'bg-slate-800 text-slate-400'
                      : it.status.includes('INSUFFICIENT')
                      ? 'bg-amber-950 text-amber-300 border border-amber-800'
                      : 'bg-rose-950/80 text-rose-300 border border-rose-900/60'
                  }`}>
                    {it.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-slate-200">
                  {it.last_price ? `₹${it.last_price.toFixed(2)}` : '—'}
                </td>
                <td className="px-3 py-2 text-slate-300">
                  {it.avg_turnover ? `₹${(it.avg_turnover / 10000000).toFixed(2)} Cr` : '—'}
                </td>
                <td className="px-3 py-2 text-slate-300">
                  {it.atr_pct ? `${it.atr_pct.toFixed(2)}%` : '—'}
                </td>
                <td className="px-3 py-2 text-slate-400">
                  {it.bars_count || 0}
                </td>
                <td className="px-3 py-2 font-sans text-[11px] text-slate-400 max-w-xs truncate" title={it.reason}>
                  {it.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filteredItems.length > 100 && (
        <p className="text-[10px] text-slate-500 font-mono text-center">
          Showing first 100 of {filteredItems.length} records. Download CSV to inspect all entries.
        </p>
      )}
    </div>
  );
};

