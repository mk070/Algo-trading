import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  BarChart2,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  FolderPlus,
  LineChart,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  Zap,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { ChartModal } from '../components/ChartModal';

interface WatchlistPageProps {
  currentMarket: 'IN' | 'US';
}

interface WatchlistInfo {
  id: number;
  name: string;
  market: string;
  is_default: boolean;
  items_count: number;
}

interface WatchlistItemData {
  id: number;
  symbol: string;
  exchange: string;
  notes?: string;
  source: string;
  last_price?: number | null;
  day_change_pct: number;
  day_volume: number;
  freshness: string;
  is_realtime: boolean;
  setup: string;
  state: string;
  filter_category?: string;
  first_failing_check?: string;
  is_already_held?: boolean;
  trigger?: number | null;
  stop?: number | null;
  dist_trigger_pct?: number | null;
  dist_stop_pct?: number | null;
  added_at?: string;
}

export const WatchlistPage: React.FC<WatchlistPageProps> = ({ currentMarket }) => {
  const [watchlists, setWatchlists] = useState<WatchlistInfo[]>([]);
  const [activeListId, setActiveListId] = useState<number | null>(null);
  const [items, setItems] = useState<WatchlistItemData[]>([]);
  const [activeFilter, setActiveFilter] = useState<string>('ALL');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Add symbol state
  const [newSymbol, setNewSymbol] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [addingSymbol, setAddingSymbol] = useState(false);

  // New Watchlist modal
  const [isNewListModalOpen, setIsNewListModalOpen] = useState(false);
  const [newListName, setNewListName] = useState('');

  // Import modal
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [importSource, setImportSource] = useState('MANUAL_PASTE');
  const [importReport, setImportReport] = useState<any | null>(null);
  const [importing, setImporting] = useState(false);

  // Chart modal
  const [chartSymbol, setChartSymbol] = useState<string | null>(null);

  const fetchWatchlists = async () => {
    try {
      const data = await apiClient.getWatchlists(currentMarket);
      setWatchlists(data || []);
      if (data && data.length > 0) {
        if (!activeListId || !data.some((w: any) => w.id === activeListId)) {
          setActiveListId(data[0].id);
        }
      }
    } catch (e) {
      console.error('Error loading watchlists:', e);
    }
  };

  const fetchItems = async (wlId: number) => {
    try {
      setRefreshing(true);
      const res = await apiClient.getWatchlistItems(wlId);
      setItems(res?.items || []);
    } catch (e) {
      console.error('Error fetching watchlist items:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchWatchlists();
  }, [currentMarket]);

  useEffect(() => {
    if (activeListId) {
      fetchItems(activeListId);
    }
  }, [activeListId]);

  // Periodic price polling every 15s
  useEffect(() => {
    if (!activeListId) return;
    const interval = setInterval(() => {
      fetchItems(activeListId);
    }, 15000);
    return () => clearInterval(interval);
  }, [activeListId]);

  const handleCreateList = async () => {
    if (!newListName.trim()) return;
    try {
      const res = await apiClient.createWatchlist(newListName.trim(), currentMarket);
      if (res?.watchlist) {
        await fetchWatchlists();
        setActiveListId(res.watchlist.id);
        setNewListName('');
        setIsNewListModalOpen(false);
      }
    } catch (e) {
      alert('Error creating watchlist: ' + e);
    }
  };

  const handleDeleteList = async (id: number) => {
    if (!confirm('Are you sure you want to delete this watchlist?')) return;
    try {
      await apiClient.deleteWatchlist(id);
      await fetchWatchlists();
    } catch (e) {
      alert('Error deleting watchlist: ' + e);
    }
  };

  const handleAddSymbol = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim()) return;

    let targetListId = activeListId;
    try {
      setAddingSymbol(true);

      // If no watchlist exists yet, create default focus list on-the-fly
      if (!targetListId) {
        const createRes = await apiClient.createWatchlist('Default Focus', currentMarket);
        if (createRes?.watchlist?.id) {
          targetListId = createRes.watchlist.id;
          setActiveListId(targetListId);
        } else {
          throw new Error('Please create a watchlist first');
        }
      }

      if (targetListId) {
        await apiClient.addWatchlistItem(targetListId, {
          symbol: newSymbol.trim().toUpperCase(),
          notes: newNotes.trim() || undefined,
          source: 'APP_MANUAL',
        });
        setNewSymbol('');
        setNewNotes('');
        await fetchWatchlists();
        await fetchItems(targetListId);
      }
    } catch (e: any) {
      alert('Error adding symbol: ' + (e?.message || e));
    } finally {
      setAddingSymbol(false);
    }
  };

  const handleRemoveItem = async (itemId: number) => {
    if (!activeListId) return;
    try {
      await apiClient.removeWatchlistItem(activeListId, itemId);
      await fetchItems(activeListId);
      await fetchWatchlists();
    } catch (e) {
      alert('Error removing item: ' + e);
    }
  };

  const handleRunImport = async () => {
    if (!activeListId || !importText.trim()) return;
    try {
      setImporting(true);
      const res = await apiClient.importWatchlistSymbols(activeListId, importText, importSource);
      setImportReport(res);
      await fetchItems(activeListId);
      await fetchWatchlists();
    } catch (e) {
      alert('Import failed: ' + e);
    } finally {
      setImporting(false);
    }
  };

  const activeWatchlist = watchlists.find((w) => w.id === activeListId);

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Clock className="w-5 h-5 text-indigo-400" />
            Watchlists & Opportunity Monitor
          </h1>
          <p className="text-xs text-slate-400">
            Named opportunity lists, CSV/Paste imports, live price feeds, and breakout distance tracking.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setIsImportModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition-all"
          >
            <Upload className="w-3.5 h-3.5 text-indigo-400" />
            Import (CSV / Paste)
          </button>
          <button
            onClick={() => setIsNewListModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow transition-all"
          >
            <FolderPlus className="w-3.5 h-3.5" />
            New Watchlist
          </button>
        </div>
      </div>

      {/* Watchlist Tabs Bar */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {watchlists.map((wl) => {
            const isActive = wl.id === activeListId;
            return (
              <div
                key={wl.id}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all border ${
                  isActive
                    ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/50 shadow'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white hover:bg-slate-800'
                }`}
                onClick={() => setActiveListId(wl.id)}
              >
                <span>{wl.name}</span>
                <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] text-slate-400 font-mono">
                  {wl.items_count}
                </span>
                {!wl.is_default && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteList(wl.id);
                    }}
                    className="text-slate-500 hover:text-rose-400 ml-1"
                    title="Delete watchlist"
                  >
                    ×
                  </button>
                )}
              </div>
            );
          })}
        </div>

        <button
          onClick={() => activeListId && fetchItems(activeListId)}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1 rounded bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:text-white"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-indigo-400' : ''}`} />
          {refreshing ? 'Updating...' : 'Refresh Quotes'}
        </button>
      </div>

      {/* Add Symbol Input Bar */}
      <form
        onSubmit={handleAddSymbol}
        className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 flex items-center gap-3 flex-wrap text-xs shadow-sm"
      >
        <span className="font-semibold text-slate-300 flex items-center gap-1.5">
          <Plus className="w-4 h-4 text-indigo-400" /> Add to {activeWatchlist?.name}:
        </span>
        <input
          type="text"
          placeholder={currentMarket === 'IN' ? 'Symbol (e.g. RELIANCE, TATAMOTORS)' : 'Symbol (e.g. NVDA, AAPL)'}
          value={newSymbol}
          onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
          className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-white font-mono uppercase focus:outline-none focus:border-indigo-500"
        />
        <input
          type="text"
          placeholder="Note (e.g. 3-week tight base, cup with handle)"
          value={newNotes}
          onChange={(e) => setNewNotes(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-300 flex-1 min-w-[200px] focus:outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={addingSymbol || !newSymbol.trim()}
          className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold rounded-lg transition-all"
        >
          {addingSymbol ? 'Adding...' : 'Add Stock'}
        </button>
      </form>

      {/* Table Section */}
      {items.length > 0 && (
        <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 p-1.5 rounded-xl text-xs font-semibold overflow-x-auto">
          {[
            { id: 'ALL', label: 'All', count: items.length },
            { id: 'NEAR_BREAKOUT', label: 'Near Breakout (<1.5%)', count: items.filter((i) => i.filter_category === 'NEAR_BREAKOUT').length },
            { id: 'VALID_SETUP', label: 'Valid Setup', count: items.filter((i) => i.filter_category === 'VALID_SETUP').length },
            { id: 'WAITING_CONFIRMATION', label: 'Waiting Confirmation', count: items.filter((i) => i.filter_category === 'WAITING_CONFIRMATION').length },
            { id: 'BLOCKED', label: 'Blocked', count: items.filter((i) => i.filter_category === 'BLOCKED').length },
            { id: 'NO_SETUP', label: 'No Setup', count: items.filter((i) => i.filter_category === 'NO_SETUP').length },
            { id: 'ALREADY_HELD', label: 'Already Held', count: items.filter((i) => i.filter_category === 'ALREADY_HELD' || i.is_already_held).length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveFilter(tab.id)}
              className={`px-3 py-1.5 rounded-lg whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                activeFilter === tab.id
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <span>{tab.label}</span>
              <span className="px-1.5 py-0.2 rounded-full bg-slate-800/80 text-[10px] text-slate-300 font-mono">
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="h-64 bg-slate-900 border border-slate-800 rounded-xl animate-pulse flex items-center justify-center text-slate-500">
          Loading watchlist candidates...
        </div>
      ) : items.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400 text-xs flex flex-col items-center gap-3">
          <Sparkles className="w-8 h-8 text-indigo-400" />
          <h3 className="font-bold text-base text-white">Watchlist is Empty</h3>
          <p className="max-w-md text-slate-500">
            Type a stock symbol above or click <strong>Import (CSV / Paste)</strong> to bring in symbols from Zerodha or your personal trading lists.
          </p>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 uppercase font-bold border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Symbol</th>
                  <th className="px-4 py-3">Live Price</th>
                  <th className="px-4 py-3">Day %</th>
                  <th className="px-4 py-3">Opportunity State</th>
                  <th className="px-4 py-3">Trigger Price</th>
                  <th className="px-4 py-3">Dist to Trigger</th>
                  <th className="px-4 py-3">Stop Loss</th>
                  <th className="px-4 py-3">Guardrail / Failing Check</th>
                  <th className="px-4 py-3">Feed Lane</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {items
                  .filter((row) => {
                    if (activeFilter === 'ALL') return true;
                    if (activeFilter === 'ALREADY_HELD') return row.filter_category === 'ALREADY_HELD' || row.is_already_held;
                    return row.filter_category === activeFilter;
                  })
                  .map((row) => (
                  <tr key={row.id} className="hover:bg-slate-850/50 transition-colors">
                    <td className="px-4 py-3 font-sans">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-sm font-mono">{row.symbol}</span>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                          {row.exchange}
                        </span>
                      </div>
                      {row.notes && <div className="text-[11px] text-slate-400 font-sans mt-0.5 line-clamp-1">{row.notes}</div>}
                    </td>

                    <td className="px-4 py-3 font-bold text-slate-100 text-sm">
                      {row.last_price != null ? `${currentMarket === 'IN' ? '₹' : '$'}${row.last_price.toFixed(2)}` : '—'}
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded font-bold text-xs ${
                          row.day_change_pct >= 0
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-rose-950 text-rose-400 border border-rose-800'
                        }`}
                      >
                        {row.day_change_pct >= 0 ? '+' : ''}
                        {row.day_change_pct.toFixed(2)}%
                      </span>
                    </td>

                    <td className="px-4 py-3 font-sans">
                      {row.is_already_held || row.filter_category === 'ALREADY_HELD' ? (
                        <span className="px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800 text-[10px] font-bold">
                          ALREADY HELD
                        </span>
                      ) : row.filter_category === 'NEAR_BREAKOUT' || row.state === 'APPROACHING' ? (
                        <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 text-[10px] font-bold">
                          NEAR BREAKOUT
                        </span>
                      ) : row.filter_category === 'VALID_SETUP' ? (
                        <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-bold">
                          VALID SETUP
                        </span>
                      ) : row.filter_category === 'WAITING_CONFIRMATION' ? (
                        <span className="px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 text-[10px] font-bold">
                          WAITING CONFIRMATION
                        </span>
                      ) : row.filter_category === 'BLOCKED' ? (
                        <span className="px-2 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-900/60 text-[10px] font-bold">
                          BLOCKED
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">
                          NO SETUP
                        </span>
                      )}
                    </td>

                    <td className="px-4 py-3 text-emerald-400 font-bold">
                      {row.trigger != null ? `${currentMarket === 'IN' ? '₹' : '$'}${row.trigger.toFixed(2)}` : '—'}
                    </td>

                    <td className="px-4 py-3">
                      {row.dist_trigger_pct != null ? (
                        <span className={row.dist_trigger_pct <= 2.5 ? 'text-amber-400 font-bold' : 'text-slate-400'}>
                          {row.dist_trigger_pct > 0 ? `${row.dist_trigger_pct.toFixed(1)}% away` : 'Triggered'}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>

                    <td className="px-4 py-3 text-rose-400">
                      {row.stop != null ? `${currentMarket === 'IN' ? '₹' : '$'}${row.stop.toFixed(2)}` : '—'}
                    </td>

                    <td className="px-4 py-3 font-sans text-slate-400 text-[11px] max-w-xs truncate" title={row.first_failing_check || 'Passes baseline filters'}>
                      {row.first_failing_check || 'Passes baseline filters'}
                    </td>

                    <td className="px-4 py-3">
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${
                          row.freshness === 'FRESH'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                            : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                        }`}
                      >
                        {row.freshness}
                      </span>
                    </td>

                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => setChartSymbol(row.symbol)}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white text-[11px] font-sans font-semibold border border-slate-700 transition-colors flex items-center gap-1.5"
                          title="Open Technical Chart"
                        >
                          <LineChart className="w-3.5 h-3.5 text-indigo-400" />
                          <span>Chart</span>
                        </button>
                        <button
                          onClick={() => handleRemoveItem(row.id)}
                          className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                          title="Remove from Watchlist"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* New Watchlist Modal */}
      {isNewListModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-4">
            <h3 className="font-bold text-white text-base">Create New Watchlist</h3>
            <input
              type="text"
              placeholder="e.g. Momentum Breakouts, Power 20"
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-xs"
              autoFocus
            />
            <div className="flex items-center justify-end gap-2 text-xs">
              <button
                onClick={() => setIsNewListModalOpen(false)}
                className="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateList}
                disabled={!newListName.trim()}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CSV / Paste Import Modal */}
      {isImportModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col gap-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-white text-base">Import Symbols into {activeWatchlist?.name}</h3>
                <p className="text-xs text-slate-400">
                  Paste stock tickers (comma, newline, or space separated) or copy from Zerodha Kite / CSV.
                </p>
              </div>
              <button
                onClick={() => {
                  setIsImportModalOpen(false);
                  setImportReport(null);
                  setImportText('');
                }}
                className="text-slate-400 hover:text-white"
              >
                ×
              </button>
            </div>

            <textarea
              rows={6}
              placeholder={`RELIANCE, TCS, INFY\nNSE:HDFCBANK\nBAJFINANCE\nICICIBANK`}
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs text-white font-mono focus:outline-none focus:border-indigo-500"
            />

            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">Prefixes like "NSE:" and suffixes like "-EQ" will be automatically resolved.</span>
              <button
                onClick={handleRunImport}
                disabled={importing || !importText.trim()}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold rounded-lg flex items-center gap-2"
              >
                <Upload className="w-3.5 h-3.5" />
                {importing ? 'Validating & Importing...' : 'Validate & Import'}
              </button>
            </div>

            {/* Import Resolution Report */}
            {importReport && (
              <div className="border border-slate-800 rounded-xl p-4 bg-slate-950 flex flex-col gap-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white">Import Summary:</span>
                  <span className="text-emerald-400 font-bold">
                    ✓ {importReport.added_count} Added Successfully
                  </span>
                </div>

                <div className="max-h-48 overflow-y-auto divide-y divide-slate-800/60 font-mono text-[11px]">
                  {importReport.report.map((r: any, idx: number) => (
                    <div key={idx} className="py-1.5 flex items-center justify-between">
                      <span className="text-slate-200 font-bold">{r.symbol || r.raw}</span>
                      <span
                        className={`px-1.5 py-0.2 rounded font-sans text-[10px] font-bold ${
                          r.status === 'RESOLVED'
                            ? 'bg-emerald-950 text-emerald-400'
                            : r.status === 'DUPLICATE'
                            ? 'bg-slate-800 text-slate-400'
                            : 'bg-rose-950 text-rose-400'
                        }`}
                      >
                        {r.status}: {r.reason}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Chart Modal */}
      <ChartModal
        isOpen={Boolean(chartSymbol)}
        onClose={() => setChartSymbol(null)}
        symbol={chartSymbol}
        market={currentMarket}
      />
    </div>
  );
};
