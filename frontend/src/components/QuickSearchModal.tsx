import React, { useEffect, useRef, useState } from 'react';
import { LineChart, Newspaper, Search, Star } from 'lucide-react';
import { apiClient } from '../api/client';

interface SearchResult {
  symbol: string;
  name: string;
  sector: string;
  market: string;
  price?: number | null;
  freshness?: string;
  realtime?: boolean;
  source?: string | null;
}

interface QuickSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentMarket: 'IN' | 'US';
  onSelectSymbol: (symbol: string) => void;
  onOpenChart?: (symbol: string) => void;
  onAddToWatchlist?: (symbol: string) => void;
  onViewNews?: (symbol: string) => void;
}

export const QuickSearchModal: React.FC<QuickSearchModalProps> = ({
  isOpen,
  onClose,
  currentMarket,
  onSelectSymbol,
  onOpenChart,
  onAddToWatchlist,
  onViewNews,
}) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const matches = await apiClient.searchSymbols(query.trim(), currentMarket);
        setResults(matches);
        setSelectedIndex(0);
      } catch (err) {
        console.error('Search failed:', err);
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query, currentMarket]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < results.length - 1 ? prev + 1 : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : results.length - 1));
    } else if (e.key === 'Enter' && results[selectedIndex]) {
      e.preventDefault();
      onSelectSymbol(results[selectedIndex].symbol);
      onClose();
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-8 sm:pt-20 px-3 sm:px-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-slate-800 bg-slate-900/90">
          <Search className="w-4 h-4 text-slate-400 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Search ${currentMarket === 'IN' ? 'NSE / Nifty' : 'US / S&P'} symbols or company names...`}
            className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
          />
          <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            {currentMarket}
          </span>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-xs px-1.5 py-0.5 rounded border border-slate-700 font-mono"
          >
            ESC
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto divide-y divide-slate-800/60 p-1">
          {loading && (
            <div className="p-4 text-center text-xs text-slate-400">
              Searching {currentMarket} universe...
            </div>
          )}

          {!loading && query.trim() && results.length === 0 && (
            <div className="p-6 text-center text-xs text-slate-500">
              No matching instruments found in {currentMarket} universe for "{query}".
            </div>
          )}

          {!loading && !query.trim() && (
            <div className="p-6 text-center text-xs text-slate-500">
              Type a ticker or company name to jump directly to its chart and analytics.
            </div>
          )}

          {results.map((res, idx) => {
            const isSelected = idx === selectedIndex;
            return (
              <div
                key={res.symbol}
                onMouseEnter={() => setSelectedIndex(idx)}
                onClick={() => {
                  onSelectSymbol(res.symbol);
                  onClose();
                }}
                className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg cursor-pointer transition ${
                  isSelected ? 'bg-indigo-600/20 text-white' : 'text-slate-300 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-slate-100 font-mono">{res.symbol}</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                      {res.sector}
                    </span>
                  </div>
                  <span className="text-xs text-slate-400 line-clamp-1">{res.name}</span>
                </div>

                <div className="flex items-center gap-3 text-right">
                  {res.price != null && (
                    <div className="font-mono text-sm font-bold text-slate-100">
                      {currentMarket === 'IN' ? '₹' : '$'}
                      {res.price.toFixed(2)}
                    </div>
                  )}
                  {res.freshness && res.freshness !== 'UNAVAILABLE' && (
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                        res.freshness === 'FRESH'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                      }`}
                    >
                      {res.freshness}
                    </span>
                  )}

                  {/* OpenTerminal-style Quick Action Buttons */}
                  <div className="flex items-center gap-1 opacity-80 hover:opacity-100" onClick={(e) => e.stopPropagation()}>
                    {onOpenChart && (
                      <button
                        onClick={() => {
                          onOpenChart(res.symbol);
                          onClose();
                        }}
                        className="p-1.5 rounded bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white transition"
                        title="View Candlestick Chart"
                      >
                        <LineChart className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {onAddToWatchlist && (
                      <button
                        onClick={() => {
                          onAddToWatchlist(res.symbol);
                        }}
                        className="p-1.5 rounded bg-slate-800 hover:bg-amber-600 text-slate-300 hover:text-white transition"
                        title="Add to Watchlist"
                      >
                        <Star className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {onViewNews && (
                      <button
                        onClick={() => {
                          onViewNews(res.symbol);
                          onClose();
                        }}
                        className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"
                        title="Inspect News & Events"
                      >
                        <Newspaper className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer shortcuts hint */}
        <div className="flex items-center justify-between px-4 py-2 bg-slate-950/60 border-t border-slate-800/80 text-[11px] text-slate-500 font-mono">
          <span>Navigate with ↑ / ↓</span>
          <span>Press Enter to Select</span>
        </div>
      </div>
    </div>
  );
};

