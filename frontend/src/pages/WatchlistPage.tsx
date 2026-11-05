import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  BarChart2,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FolderPlus,
  Info,
  LineChart,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Star,
  Target,
  Trash2,
  TrendingDown,
  TrendingUp,
  Upload,
  X,
  Zap,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { ChartModal } from '../components/ChartModal';
import { FundamentalReport } from '../components/FundamentalReport';

interface WatchlistPageProps {
  currentMarket: 'IN' | 'US';
}

interface WatchlistInfo {
  id: number;
  name: string;
  market: string;
  is_default: boolean;
  items_count: number;
  is_stale?: boolean;
  age_days?: number;
  provenance_label?: string;
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

// ─── Preset watchlist seeds ────────────────────────────────────────────────
const PRESET_LISTS: Record<string, { name: string; market: 'IN' | 'US'; symbols: string[]; description: string }> = {
  'IN_ST': {
    name: 'India — Short-Term Opportunities',
    market: 'IN',
    symbols: ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'AXISBANK', 'BAJFINANCE', 'BHARTIARTL', 'WIPRO'],
    description: 'Swing trading candidates: Nifty 50 leaders with momentum setups',
  },
  'IN_LT': {
    name: 'India — Long-Term Opportunities',
    market: 'IN',
    symbols: ['HDFCBANK', 'TCS', 'INFY', 'RELIANCE', 'LT', 'TITAN', 'ASIANPAINT', 'PIDILITIND', 'DIVISLAB', 'MUTHOOTFIN'],
    description: 'Quality compounders: high ROCE, low debt, consistent earnings growth',
  },
  'US_ST': {
    name: 'US — Short-Term Opportunities',
    market: 'US',
    symbols: ['NVDA', 'AAPL', 'MSFT', 'AMZN', 'META', 'GOOGL', 'AMD', 'TSLA', 'CRM', 'AVGO'],
    description: 'Swing trading candidates: Mega-cap tech with high relative strength',
  },
  'US_LT': {
    name: 'US — Long-Term Opportunities',
    market: 'US',
    symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'BRK.B', 'JPM', 'V', 'MA', 'UNH', 'HD'],
    description: 'Quality compounders: durable moat, FCF positive, low debt',
  },
};

// ─── Helpers ───────────────────────────────────────────────────────────────
function fmtPrice(val: number | null | undefined, market: string): string {
  if (val == null) return '—';
  const sym = market === 'IN' ? '₹' : '$';
  return `${sym}${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function FilterBadge({ category, small }: { category: string; small?: boolean }) {
  const base = small ? 'text-[9px] px-1 py-0.5' : 'text-[10px] px-2 py-0.5';
  switch (category) {
    case 'NEAR_BREAKOUT':
      return <span className={`${base} rounded font-bold bg-amber-950 text-amber-300 border border-amber-800`}>NEAR BREAKOUT</span>;
    case 'VALID_SETUP':
      return <span className={`${base} rounded font-bold bg-emerald-950 text-emerald-300 border border-emerald-800`}>VALID SETUP</span>;
    case 'WAITING_CONFIRMATION':
      return <span className={`${base} rounded font-bold bg-cyan-950 text-cyan-300 border border-cyan-800`}>WAITING</span>;
    case 'ALREADY_HELD':
      return <span className={`${base} rounded font-bold bg-blue-950 text-blue-300 border border-blue-800`}>HELD</span>;
    case 'BLOCKED':
      return <span className={`${base} rounded font-bold bg-rose-950/70 text-rose-300 border border-rose-900`}>BLOCKED</span>;
    default:
      return <span className={`${base} rounded bg-slate-800 text-slate-500`}>MONITORING</span>;
  }
}

// ─── Stock Row (expandable) ────────────────────────────────────────────────
function StockRow({
  row,
  market,
  onOpenChart,
  onRemove,
  onOpenFundamentals,
  expanded,
  onToggleExpand,
  flash,
}: {
  row: WatchlistItemData;
  market: 'IN' | 'US';
  onOpenChart: (sym: string) => void;
  onRemove: (id: number) => void;
  onOpenFundamentals: (sym: string) => void;
  expanded: boolean;
  onToggleExpand: (sym: string) => void;
  flash?: 'UP' | 'DOWN';
}) {
  const isUp = row.day_change_pct >= 0;

  return (
    <>
      <tr
        className={`hover:bg-slate-800/40 transition-colors cursor-pointer ${expanded ? 'bg-slate-800/20' : ''}`}
        onClick={() => onToggleExpand(row.symbol)}
      >
        {/* Symbol */}
        <td className="px-3 py-2.5 font-sans">
          <div className="flex items-center gap-2">
            <ChevronRight
              className={`w-3.5 h-3.5 text-slate-600 flex-shrink-0 transition-transform duration-150 ${expanded ? 'rotate-90 text-indigo-400' : ''}`}
            />
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-slate-100 text-sm font-mono">{row.symbol}</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 border border-slate-700/60">{row.exchange}</span>
                <FilterBadge category={row.filter_category || 'NO_SETUP'} small />
              </div>
              {row.notes && (
                <div className="text-[10px] text-slate-500 font-sans truncate max-w-[180px] mt-0.5" title={row.notes}>
                  {row.notes}
                </div>
              )}
            </div>
          </div>
        </td>

        {/* Price with Real-time Tick Glow Flash */}
        <td className="px-3 py-2.5 text-right">
          <span
            className={`font-mono font-bold text-sm tabular-nums px-2 py-0.5 rounded transition-all duration-300 ${
              flash === 'UP'
                ? 'bg-emerald-500/30 text-emerald-300 ring-1 ring-emerald-400 font-black'
                : flash === 'DOWN'
                ? 'bg-rose-500/30 text-rose-300 ring-1 ring-rose-400 font-black'
                : 'text-slate-100'
            }`}
          >
            {fmtPrice(row.last_price, market)}
          </span>
        </td>

        {/* Day % */}
        <td className="px-3 py-2.5 text-right">
          <span
            className={`inline-flex items-center gap-0.5 font-mono font-bold text-xs tabular-nums px-2 py-0.5 rounded ${
              isUp
                ? 'bg-emerald-950 text-emerald-400 border border-emerald-900'
                : 'bg-rose-950 text-rose-400 border border-rose-900'
            }`}
          >
            {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {isUp ? '+' : ''}{row.day_change_pct.toFixed(2)}%
          </span>
        </td>

        {/* Trigger */}
        <td className="px-3 py-2.5 text-right font-mono text-xs text-emerald-400 tabular-nums">
          {row.trigger != null && row.trigger > 0 && row.filter_category !== 'NO_SETUP' ? fmtPrice(row.trigger, market) : <span className="text-slate-500">—</span>}
        </td>

        {/* Dist to trigger */}
        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums">
          {row.trigger != null && row.trigger > 0 && row.filter_category !== 'NO_SETUP' && row.dist_trigger_pct != null ? (
            <span className={row.dist_trigger_pct <= 2.5 ? 'text-amber-400 font-bold' : 'text-slate-400'}>
              {row.dist_trigger_pct > 0 ? `${row.dist_trigger_pct.toFixed(1)}%` : 'Triggered'}
            </span>
          ) : (
            <span className="text-slate-600 font-sans text-[11px]">Building Base</span>
          )}
        </td>

        {/* Stop */}
        <td className="px-3 py-2.5 text-right font-mono text-xs text-rose-400 tabular-nums">
          {row.stop != null && row.stop > 0 && row.filter_category !== 'NO_SETUP' ? fmtPrice(row.stop, market) : <span className="text-slate-500">—</span>}
        </td>

        {/* Feed */}
        <td className="px-3 py-2.5 text-right">
          <span
            className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${
              row.freshness === 'FRESH'
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
            }`}
          >
            {row.freshness}
          </span>
        </td>

        {/* Actions */}
        <td className="px-3 py-2.5 text-right">
          <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => onOpenChart(row.symbol)}
              className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-indigo-300 border border-slate-700 transition-colors"
              title="Open Chart"
            >
              <LineChart className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onOpenFundamentals(row.symbol)}
              className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-emerald-300 border border-slate-700 transition-colors"
              title="Fundamental Analysis"
            >
              <BookOpen className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onRemove(row.id)}
              className="p-1.5 rounded text-slate-600 hover:text-rose-400 hover:bg-slate-800 transition-colors"
              title="Remove"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </td>
      </tr>

      {/* Expanded row: guardrail reason */}
      {expanded && (
        <tr className="bg-slate-950/60">
          <td colSpan={8} className="px-6 py-3 border-b border-slate-800/60">
            <div className="flex items-start gap-3 flex-wrap">
              {row.first_failing_check ? (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                  <span><strong className="text-slate-300">First failing check:</strong> {row.first_failing_check}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-xs text-emerald-400">
                  <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>Passes all baseline filters</span>
                </div>
              )}
              {row.notes && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Info className="w-3.5 h-3.5 flex-shrink-0" />
                  <span><strong className="text-slate-400">Note:</strong> {row.notes}</span>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────
export const WatchlistPage: React.FC<WatchlistPageProps> = ({ currentMarket }) => {
  const [watchlists, setWatchlists] = useState<WatchlistInfo[]>([]);
  const [activeListId, setActiveListId] = useState<number | null>(null);
  const [items, setItems] = useState<WatchlistItemData[]>([]);
  const [activeFilter, setActiveFilter] = useState<string>('ALL');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  // Add symbol
  const [newSymbol, setNewSymbol] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [addingSymbol, setAddingSymbol] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // New watchlist modal
  const [isNewListModalOpen, setIsNewListModalOpen] = useState(false);
  const [newListName, setNewListName] = useState('');
  const [newListMarket, setNewListMarket] = useState<'IN' | 'US'>(currentMarket);

  // Import modal
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [importSource, setImportSource] = useState('MANUAL_PASTE');
  const [importReport, setImportReport] = useState<any | null>(null);
  const [importing, setImporting] = useState(false);

  // Fundamentals panel
  const [fundamentalSymbol, setFundamentalSymbol] = useState<string | null>(null);

  // Chart modal
  const [chartSymbol, setChartSymbol] = useState<string | null>(null);

  // Search filter
  const [searchQuery, setSearchQuery] = useState('');

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

  const [priceFlashes, setPriceFlashes] = useState<Record<string, 'UP' | 'DOWN'>>({});
  const itemsRef = React.useRef<WatchlistItemData[]>([]);
  itemsRef.current = items;

  const fetchItems = async (wlId: number, isSilent = false) => {
    try {
      if (!isSilent) setRefreshing(true);
      const res = await apiClient.getWatchlistItems(wlId);
      if (res?.items) {
        // Compute live price diffs to flash tickers (Bloomberg Terminal mode)
        const oldItems = itemsRef.current;
        const newFlashes: Record<string, 'UP' | 'DOWN'> = {};
        res.items.forEach((newItem: any) => {
          const oldItem = oldItems.find((it) => it.symbol === newItem.symbol);
          if (oldItem && oldItem.last_price != null && newItem.last_price != null && oldItem.last_price !== newItem.last_price) {
            newFlashes[newItem.symbol] = newItem.last_price > oldItem.last_price ? 'UP' : 'DOWN';
          }
        });

        if (Object.keys(newFlashes).length > 0) {
          setPriceFlashes((prev) => ({ ...prev, ...newFlashes }));
          setTimeout(() => {
            setPriceFlashes((prev) => {
              const copy = { ...prev };
              Object.keys(newFlashes).forEach((k) => delete copy[k]);
              return copy;
            });
          }, 800);
        }

        setItems(res.items);
      }
    } catch (e) {
      if (!isSilent) console.error('Error fetching watchlist items:', e);
    } finally {
      if (!isSilent) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    setLoading(true);
    setItems([]);
    fetchWatchlists();
  }, [currentMarket]);

  useEffect(() => {
    if (activeListId) fetchItems(activeListId, false);
  }, [activeListId]);

  // Real-time 2.5s polling without reload (Bloomberg Terminal & brokerage app mode)
  useEffect(() => {
    if (!activeListId) return;
    const interval = setInterval(() => fetchItems(activeListId, true), 2500);
    return () => clearInterval(interval);
  }, [activeListId]);

  const handleCreateList = async () => {
    if (!newListName.trim()) return;
    try {
      const res = await apiClient.createWatchlist(newListName.trim(), newListMarket);
      if (res?.watchlist) {
        await fetchWatchlists();
        setActiveListId(res.watchlist.id);
        setNewListName('');
        setIsNewListModalOpen(false);
      }
    } catch (e: any) {
      alert('Error creating watchlist: ' + e?.message);
    }
  };

  const handleCreatePreset = async (key: string) => {
    const preset = PRESET_LISTS[key];
    if (!preset) return;
    try {
      const res = await apiClient.createWatchlist(preset.name, preset.market);
      if (res?.watchlist?.id) {
        const wlId = res.watchlist.id;
        // Import symbols
        await apiClient.importWatchlistSymbols(wlId, preset.symbols.join('\n'), 'APP_PRESET');
        await fetchWatchlists();
        setActiveListId(wlId);
      }
    } catch (e: any) {
      alert('Error creating preset list: ' + e?.message);
    }
  };

  const handleDeleteList = async (id: number) => {
    if (!confirm('Delete this watchlist?')) return;
    try {
      await apiClient.deleteWatchlist(id);
      await fetchWatchlists();
    } catch (e: any) {
      alert('Error deleting watchlist: ' + e?.message);
    }
  };

  const handleAddSymbol = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim()) return;
    setAddError(null);
    let targetListId = activeListId;
    try {
      setAddingSymbol(true);
      if (!targetListId) {
        const createRes = await apiClient.createWatchlist('Default Focus', currentMarket);
        if (createRes?.watchlist?.id) {
          targetListId = createRes.watchlist.id;
          setActiveListId(targetListId);
        } else {
          throw new Error('Create a watchlist first');
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
      setAddError(e?.message || String(e));
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
    } catch (e: any) {
      alert('Error removing item: ' + e?.message);
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
    } catch (e: any) {
      alert('Import failed: ' + e?.message);
    } finally {
      setImporting(false);
    }
  };

  const toggleRow = (sym: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  };

  const activeWatchlist = watchlists.find((w) => w.id === activeListId);

  const filteredItems = items
    .filter((row) => {
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        if (!row.symbol.toLowerCase().includes(q) && !row.notes?.toLowerCase().includes(q)) return false;
      }
      if (activeFilter === 'ALL') return true;
      if (activeFilter === 'ALREADY_HELD') return row.filter_category === 'ALREADY_HELD' || row.is_already_held;
      return row.filter_category === activeFilter;
    });

  const tabCounts = {
    ALL: items.length,
    NEAR_BREAKOUT: items.filter((i) => i.filter_category === 'NEAR_BREAKOUT').length,
    VALID_SETUP: items.filter((i) => i.filter_category === 'VALID_SETUP').length,
    WAITING_CONFIRMATION: items.filter((i) => i.filter_category === 'WAITING_CONFIRMATION').length,
    BLOCKED: items.filter((i) => i.filter_category === 'BLOCKED').length,
    NO_SETUP: items.filter((i) => i.filter_category === 'NO_SETUP').length,
    ALREADY_HELD: items.filter((i) => i.filter_category === 'ALREADY_HELD' || i.is_already_held).length,
  };

  return (
    <div className="flex flex-col gap-4">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Star className="w-5 h-5 text-indigo-400" />
            Watchlists
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Named opportunity lists · Live prices · Breakout tracking · Fundamental analysis
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setIsImportModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition-all"
          >
            <Upload className="w-3.5 h-3.5 text-indigo-400" />
            Import
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

      {/* ── Watchlist tabs ── */}
      <div className="border-b border-slate-800 pb-3 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {watchlists.map((wl) => {
            const isActive = wl.id === activeListId;
            return (
              <div
                key={wl.id}
                onClick={() => setActiveListId(wl.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all border ${
                  isActive
                    ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/50'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white hover:bg-slate-800'
                }`}
              >
                <span className="truncate max-w-[140px]">{wl.name}</span>
                <span className="text-[10px] px-1 rounded bg-slate-800/80 text-slate-500 font-mono flex-shrink-0">
                  {wl.items_count}
                </span>
                {wl.is_stale && (
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" title="Stale — last imported > 7 days ago" />
                )}
                {!wl.is_default && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteList(wl.id); }}
                    className="text-slate-600 hover:text-rose-400 ml-0.5 flex-shrink-0"
                    title="Delete"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
        <button
          onClick={() => activeListId && fetchItems(activeListId)}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-xs text-slate-400 hover:text-white flex-shrink-0"
        >
          <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin text-indigo-400' : ''}`} />
          <span className="hidden sm:inline">{refreshing ? 'Refreshing...' : 'Refresh'}</span>
        </button>
      </div>

      {/* ── Preset quick-create strip (when no lists or empty) ── */}
      {watchlists.length <= 1 && items.length === 0 && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <p className="text-xs text-slate-400 mb-3 flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Quick-create opportunity lists — or add symbols manually below
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {Object.entries(PRESET_LISTS)
              .filter(([, p]) => p.market === currentMarket)
              .map(([key, preset]) => (
                <button
                  key={key}
                  onClick={() => handleCreatePreset(key)}
                  className="flex flex-col gap-1 p-3 bg-slate-950 hover:bg-slate-800/80 border border-slate-800 hover:border-indigo-500/50 rounded-xl text-left transition-all group"
                >
                  <span className="text-xs font-semibold text-slate-200 group-hover:text-indigo-300">{preset.name}</span>
                  <span className="text-[10px] text-slate-500 leading-snug">{preset.description}</span>
                  <span className="text-[10px] text-slate-600 font-mono">{preset.symbols.slice(0, 5).join(' · ')} +{preset.symbols.length - 5} more</span>
                </button>
              ))}
          </div>
        </div>
      )}

      {/* ── Add symbol form ── */}
      <form
        onSubmit={handleAddSymbol}
        className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center gap-2 flex-wrap text-xs shadow-sm"
      >
        <Plus className="w-4 h-4 text-indigo-400 flex-shrink-0" />
        <span className="font-semibold text-slate-400 flex-shrink-0">
          Add to <span className="text-slate-200">{activeWatchlist?.name || 'watchlist'}:</span>
        </span>
        <input
          type="text"
          placeholder={currentMarket === 'IN' ? 'Symbol (e.g. RELIANCE)' : 'Symbol (e.g. NVDA)'}
          value={newSymbol}
          onChange={(e) => { setNewSymbol(e.target.value.toUpperCase()); setAddError(null); }}
          className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-white font-mono uppercase w-44 focus:outline-none focus:border-indigo-500 text-xs"
        />
        <input
          type="text"
          placeholder="Reason / note (e.g. 3-week tight base)"
          value={newNotes}
          onChange={(e) => setNewNotes(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-300 flex-1 min-w-[160px] focus:outline-none focus:border-indigo-500 text-xs"
        />
        <button
          type="submit"
          disabled={addingSymbol || !newSymbol.trim()}
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold rounded-lg transition-all text-xs flex items-center gap-1.5 flex-shrink-0"
        >
          {addingSymbol ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
          {addingSymbol ? 'Adding...' : 'Add'}
        </button>
        {addError && (
          <span className="w-full text-rose-400 text-[10px] flex items-center gap-1">
            <AlertCircle className="w-3 h-3" /> {addError}
          </span>
        )}
      </form>

      {/* ── Search + Filter bar ── */}
      {items.length > 0 && (
        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs w-48">
            <Search className="w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search symbol or note..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent focus:outline-none text-slate-300 w-full"
            />
          </div>

          {/* Filter tabs */}
          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-xl text-xs font-semibold overflow-x-auto flex-1 min-w-0">
            {[
              { id: 'ALL', label: 'All' },
              { id: 'NEAR_BREAKOUT', label: '🔥 Near Breakout' },
              { id: 'VALID_SETUP', label: '✓ Valid Setup' },
              { id: 'WAITING_CONFIRMATION', label: 'Waiting' },
              { id: 'BLOCKED', label: 'Blocked' },
              { id: 'NO_SETUP', label: 'Monitoring' },
              { id: 'ALREADY_HELD', label: 'Held' },
            ].map((tab) => {
              const count = tabCounts[tab.id as keyof typeof tabCounts];
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveFilter(tab.id)}
                  className={`px-2.5 py-1 rounded-lg whitespace-nowrap transition-colors flex items-center gap-1 ${
                    activeFilter === tab.id
                      ? 'bg-indigo-600 text-white shadow'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
                  }`}
                >
                  <span>{tab.label}</span>
                  <span className="text-[9px] px-1 rounded-full bg-slate-800/80 text-slate-400 font-mono">{count}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Table or empty states ── */}
      {loading && items.length === 0 ? (
        <div className="h-48 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-center gap-3 text-slate-500">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
          <span className="text-sm">Loading watchlist...</span>
        </div>
      ) : filteredItems.length === 0 && items.length > 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500 text-xs">
          No stocks match the current filter.{' '}
          <button className="text-indigo-400 hover:underline" onClick={() => { setActiveFilter('ALL'); setSearchQuery(''); }}>
            Clear filters
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center flex flex-col items-center gap-3">
          <Sparkles className="w-8 h-8 text-indigo-400" />
          <h3 className="font-bold text-slate-200">This watchlist is empty</h3>
          <p className="text-slate-500 text-xs max-w-sm">
            Type a symbol above to add it, or click <strong>Import</strong> to paste from Zerodha / any broker CSV.
          </p>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[700px]">
              <thead className="bg-slate-950 text-slate-500 uppercase text-[10px] font-bold border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-3 py-2.5">Symbol</th>
                  <th className="px-3 py-2.5 text-right">Price</th>
                  <th className="px-3 py-2.5 text-right">Day %</th>
                  <th className="px-3 py-2.5 text-right">Trigger</th>
                  <th className="px-3 py-2.5 text-right">Dist</th>
                  <th className="px-3 py-2.5 text-right">Stop</th>
                  <th className="px-3 py-2.5 text-right">Feed</th>
                  <th className="px-3 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40 font-mono">
                {filteredItems.map((row) => (
                  <StockRow
                    key={row.id}
                    row={row}
                    market={currentMarket}
                    onOpenChart={setChartSymbol}
                    onRemove={handleRemoveItem}
                    onOpenFundamentals={setFundamentalSymbol}
                    expanded={expandedRows.has(row.symbol)}
                    onToggleExpand={toggleRow}
                    flash={priceFlashes[row.symbol]}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Fundamental Report Panel ── */}
      {fundamentalSymbol && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-indigo-400" />
              <span className="font-bold text-slate-200 text-sm">Fundamental Analysis</span>
              <span className="font-mono text-emerald-400 text-sm">{fundamentalSymbol}</span>
              <span className="text-[10px] text-slate-500">· Research only, not advice</span>
            </div>
            <button
              onClick={() => setFundamentalSymbol(null)}
              className="text-slate-500 hover:text-white p-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="p-4 max-h-[80vh] overflow-y-auto">
            <FundamentalReport symbol={fundamentalSymbol} market={currentMarket} />
          </div>
        </div>
      )}

      {/* ── New Watchlist Modal ── */}
      {isNewListModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col gap-4">
            <h3 className="font-bold text-white text-sm">Create New Watchlist</h3>
            <input
              type="text"
              placeholder="e.g. Swing Setups Q4, Power 20"
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-xs focus:outline-none focus:border-indigo-500"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleCreateList()}
            />
            <div className="flex items-center gap-2">
              <span className="text-slate-500 text-xs">Market:</span>
              {(['IN', 'US'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setNewListMarket(m)}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
                    newListMarket === m
                      ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/60'
                      : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                  }`}
                >
                  {m === 'IN' ? '🇮🇳 India' : '🇺🇸 US'}
                </button>
              ))}
            </div>
            <div className="flex items-center justify-end gap-2 text-xs">
              <button onClick={() => setIsNewListModalOpen(false)} className="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white">
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

            {/* Preset section */}
            <div className="border-t border-slate-800 pt-3">
              <p className="text-[10px] text-slate-500 mb-2 uppercase tracking-wider">Or start from a preset</p>
              <div className="flex flex-col gap-1.5">
                {Object.entries(PRESET_LISTS).map(([key, preset]) => (
                  <button
                    key={key}
                    onClick={() => { setIsNewListModalOpen(false); handleCreatePreset(key); }}
                    className="flex items-center gap-2 p-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-indigo-500/40 rounded-xl text-left transition-all group"
                  >
                    <Sparkles className="w-3 h-3 text-indigo-500 flex-shrink-0" />
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold text-slate-300 group-hover:text-indigo-300 truncate">{preset.name}</div>
                      <div className="text-[9px] text-slate-600 truncate">{preset.symbols.slice(0, 4).join(' · ')} +{preset.symbols.length - 4} more</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Import Modal ── */}
      {isImportModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col gap-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-white text-sm">Import Symbols into {activeWatchlist?.name}</h3>
                <p className="text-xs text-slate-500">Paste tickers — comma, newline, or space separated. Zerodha CSV also works.</p>
              </div>
              <button
                onClick={() => { setIsImportModalOpen(false); setImportReport(null); setImportText(''); }}
                className="text-slate-500 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <textarea
              rows={6}
              placeholder={`RELIANCE, TCS, INFY\nNSE:HDFCBANK\nBAJFINANCE`}
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs text-white font-mono focus:outline-none focus:border-indigo-500 resize-none"
            />

            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-600">NSE: prefix and -EQ suffix are auto-stripped</span>
              <button
                onClick={handleRunImport}
                disabled={importing || !importText.trim()}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold rounded-lg flex items-center gap-2"
              >
                <Upload className="w-3.5 h-3.5" />
                {importing ? 'Importing...' : 'Validate & Import'}
              </button>
            </div>

            {importReport && (
              <div className="border border-slate-800 rounded-xl p-4 bg-slate-950 flex flex-col gap-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white">Import Summary</span>
                  <span className="text-emerald-400 font-bold">✓ {importReport.added_count} Added</span>
                </div>
                <div className="max-h-48 overflow-y-auto divide-y divide-slate-800/60 font-mono text-[10px]">
                  {importReport.report?.map((r: any, idx: number) => (
                    <div key={idx} className="py-1.5 flex items-center justify-between gap-2">
                      <span className="text-slate-300 font-bold">{r.symbol || r.raw_input || r.raw}</span>
                      <span className={`px-1.5 py-0.5 rounded font-sans text-[9px] font-bold flex-shrink-0 ${
                        r.status === 'RESOLVED' ? 'bg-emerald-950 text-emerald-400' :
                        r.status === 'DUPLICATE' ? 'bg-slate-800 text-slate-400' : 'bg-rose-950 text-rose-400'
                      }`}>
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

      {/* ── Chart Modal ── */}
      <ChartModal
        isOpen={Boolean(chartSymbol)}
        onClose={() => setChartSymbol(null)}
        symbol={chartSymbol}
        market={currentMarket}
      />
    </div>
  );
};
