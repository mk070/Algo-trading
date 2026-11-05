import React, { useEffect, useState } from 'react';
import { Award, BookOpen, CheckCircle, DollarSign, FileUp, Percent, TrendingUp, Upload } from 'lucide-react';
import { API_BASE, apiClient } from '../api/client';
import { JournalEntry } from '../types';

export const JournalPage: React.FC = () => {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string | null>(null);
  const [fundamentalOutcomes, setFundamentalOutcomes] = useState<any>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [jData, sData] = await Promise.all([
        apiClient.getJournal(),
        apiClient.getStats(),
      ]);
      setEntries(jData || []);
      setStats(sData);
      apiClient.getFundamentalOutcomes('IN').then(setFundamentalOutcomes).catch(() => setFundamentalOutcomes(null));
    } catch (e) {
      console.error('Error loading journal:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);
    setUploadResult(null);

    try {
      const res = await fetch(`${API_BASE}/portfolio/import?kind=TRADEBOOK`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      setUploadResult(`Import completed: ${data.valid_trades_saved || 0} valid trades imported.`);
      await loadData();
    } catch (err) {
      setUploadResult('Upload error: ' + err);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header & Report Upload */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-indigo-400" />
            Trade Journal & Performance Analytics
          </h1>
          <p className="text-xs text-slate-400">
            Disciplined tracking of completed trades, R-multiples, execution slippage, and Console reports.
          </p>
        </div>

        {/* Upload Zerodha Console CSV */}
        <label className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 cursor-pointer text-xs font-semibold text-slate-200 transition-colors">
          <Upload className="w-3.5 h-3.5 text-indigo-400" />
          {uploading ? 'Importing CSV...' : 'Import Zerodha Console CSV'}
          <input
            type="file"
            accept=".csv"
            onChange={handleFileUpload}
            className="hidden"
            disabled={uploading}
          />
        </label>
      </div>

      {uploadResult && (
        <div className="p-3 bg-indigo-950/60 border border-indigo-800 rounded-lg text-xs text-indigo-300">
          {uploadResult}
        </div>
      )}

      {/* Analytics KPI Cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Closed Trades</span>
            <span className="text-xl font-bold font-mono text-white">{stats.total_trades}</span>
            <span className="text-[10px] text-slate-500 block mt-1">Sample size</span>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Win Rate</span>
            <span className="text-xl font-bold font-mono text-emerald-400">{stats.win_rate}%</span>
            <span className="text-[10px] text-slate-500 block mt-1">{stats.winning_trades}W / {stats.losing_trades}L</span>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Profit Factor</span>
            <span className="text-xl font-bold font-mono text-indigo-300">{stats.profit_factor}</span>
            <span className="text-[10px] text-slate-500 block mt-1">Target &gt; 1.3</span>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Expectancy / Trade</span>
            <span className={`text-xl font-bold font-mono ${stats.avg_r_multiple >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {stats.avg_r_multiple >= 0 ? '+' : ''}{stats.avg_r_multiple}R
            </span>
            <span className="text-[10px] text-slate-500 block mt-1">Net of costs</span>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <span className="text-xs text-slate-400 block mb-1">Realized Net P&L</span>
            <span className={`text-xl font-bold font-mono ${stats.total_realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ₹{stats.total_realized_pnl?.toLocaleString('en-IN')}
            </span>
            <span className="text-[10px] text-slate-500 block mt-1">Cumulative</span>
          </div>
        </div>
      )}

      {/* Trade Log Table */}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-sm font-bold text-slate-100">Forward outcomes by fundamental snapshot</h2>
        <p className="mt-1 text-[10px] text-slate-500">Observational journal results grouped by the light snapshot saved on the signal. This is not a causal estimate.</p>
        <div className="mt-3 flex flex-wrap gap-3">{fundamentalOutcomes?.groups?.length ? fundamentalOutcomes.groups.map((group: any) => <div key={group.fundamental_state} className="min-w-[150px] rounded-lg border border-slate-800 bg-slate-950/50 p-3"><div className="text-[10px] text-slate-500">{group.fundamental_state} · {group.trades} trades</div><div className="mt-1 font-mono text-sm text-slate-200">{group.mean_r == null ? '—' : `${group.mean_r}R mean`}</div><div className="text-[10px] text-slate-500">{group.win_rate_pct == null ? '—' : `${group.win_rate_pct}% wins`}</div></div>) : <span className="text-xs text-slate-500">No linked journal outcomes with a stored signal snapshot yet.</span>}</div>
      </section>

      {/* Trade Log Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800">
          <h2 className="text-sm font-bold text-white">Historical Trade Log ({entries.length} Completed)</h2>
        </div>

        {entries.length === 0 ? (
          <div className="p-10 text-center text-slate-400 text-xs">
            No closed trades in journal yet. As positions exit, they will be logged here with complete R-multiple accounting.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 uppercase font-bold border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Symbol</th>
                  <th className="px-4 py-3">Entry</th>
                  <th className="px-4 py-3">Exit</th>
                  <th className="px-4 py-3">Qty</th>
                  <th className="px-4 py-3">Hold Days</th>
                  <th className="px-4 py-3">Exit Reason</th>
                  <th className="px-4 py-3">Net P&L</th>
                  <th className="px-4 py-3">R-Multiple</th>
                  <th className="px-4 py-3">Fees</th>
                  <th className="px-4 py-3">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {entries.map((j) => {
                  const isProfit = j.pnl_amount > 0;
                  return (
                    <tr key={j.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-4 py-3 font-bold text-white font-sans text-sm">{j.symbol}</td>
                      <td className="px-4 py-3 text-slate-300">
                        {j.entry_price?.toFixed(2)}
                        <span className="text-[10px] text-slate-500 block font-normal">{j.entry_date}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">
                        {j.exit_price?.toFixed(2)}
                        <span className="text-[10px] text-slate-500 block font-normal">{j.exit_date}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{j.qty}</td>
                      <td className="px-4 py-3 text-slate-400 font-sans">{j.holding_days}d</td>
                      <td className="px-4 py-3 font-sans text-slate-300">{j.exit_reason}</td>
                      <td className={`px-4 py-3 font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {isProfit ? '+' : ''}₹{j.pnl_amount?.toFixed(2)} ({j.pnl_pct?.toFixed(1)}%)
                      </td>
                      <td className={`px-4 py-3 font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {j.r_multiple >= 0 ? '+' : ''}{j.r_multiple?.toFixed(2)}R
                      </td>
                      <td className="px-4 py-3 text-slate-400">₹{j.fees_total?.toFixed(2)}</td>
                      <td className="px-4 py-3 font-sans text-slate-400 text-[11px] max-w-xs truncate">{j.note || '-'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
