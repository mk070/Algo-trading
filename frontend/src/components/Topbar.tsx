import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  CheckCircle2,
  ChevronRight,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Star,
  X,
} from 'lucide-react';
import { RegimeResult } from '../types';

export interface WorkspaceTab {
  id: string;
  label: string;
  to?: string;
  symbol?: string;
  closable?: boolean;
}

interface TopbarProps {
  currentMarket: 'IN' | 'US';
  onMarketChange: (m: 'IN' | 'US') => void;
  regime?: RegimeResult | null;
  isStreaming: boolean;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  onOpenSearch?: () => void;
  onOpenCustomAlerts?: () => void;
  onToggleMobileMenu?: () => void;
  activeTabs: WorkspaceTab[];
  activeTabId: string;
  onSelectTab: (tabId: string) => void;
  onCloseTab: (tabId: string) => void;
}

export const Topbar: React.FC<TopbarProps> = ({
  currentMarket,
  onMarketChange,
  regime,
  isStreaming,
  onRefresh,
  isRefreshing = false,
  onOpenSearch,
  onOpenCustomAlerts,
  onToggleMobileMenu,
  activeTabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
}) => {
  const navigate = useNavigate();
  const location = useLocation();

  const getRegimeColor = (status?: string) => {
    switch (status) {
      case 'BULLISH':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-800';
      case 'CAUTION':
        return 'bg-amber-950/80 text-amber-300 border-amber-800';
      case 'WEAK':
        return 'bg-rose-950/80 text-rose-400 border-rose-800';
      default:
        return 'bg-slate-900 text-slate-400 border-slate-800';
    }
  };

  return (
    <header className="sticky top-0 z-40 h-14 bg-slate-950/95 backdrop-blur border-b border-slate-800 px-3 lg:px-6 flex items-center justify-between gap-4 select-none">
      {/* Left: Mobile hamburger + Workspace Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto scrollbar-none flex-1 py-1">
        {onToggleMobileMenu && (
          <button
            onClick={onToggleMobileMenu}
            className="lg:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900 mr-1 shrink-0 min-w-[38px] min-h-[38px] flex items-center justify-center"
            aria-label="Toggle Navigation Drawer"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}

        {/* Browser-style Workspace Tabs */}
        <div className="flex items-center gap-1 shrink-0">
          {activeTabs.map((tab) => {
            const isActive = activeTabId === tab.id;
            return (
              <div
                key={tab.id}
                onClick={() => onSelectTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all border shrink-0 ${
                  isActive
                    ? 'bg-slate-900 text-white border-slate-700 shadow-sm'
                    : 'bg-slate-950 text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                {tab.id === 'watchlist' && (
                  <Star className="w-3 h-3 text-amber-400 fill-amber-400 shrink-0" />
                )}
                <span>{tab.label}</span>
                {tab.closable && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onCloseTab(tab.id);
                    }}
                    className="p-0.5 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 ml-1 transition"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            );
          })}

          {/* Plus button to open search / new tab */}
          {onOpenSearch && (
            <button
              onClick={onOpenSearch}
              className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-slate-900 transition shrink-0"
              title="Open Stock or View (Ctrl+K)"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Right: Market Pills, Regime Chip, Global Actions */}
      <div className="flex items-center gap-3 shrink-0">
        {/* OpenStock Market Selector Pills */}
        <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs font-semibold">
          <button
            onClick={() => onMarketChange('US')}
            className={`flex items-center gap-1.5 px-2 sm:px-2.5 py-1 rounded-md transition-all ${
              currentMarket === 'US'
                ? 'bg-indigo-950 text-indigo-300 border border-indigo-700/80 font-bold shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                currentMarket === 'US' ? 'bg-indigo-400' : 'bg-slate-500'
              }`}
            ></span>
            <span className="hidden sm:inline">United States</span>
            <span className="sm:hidden font-mono text-[11px]">US</span>
          </button>
          <button
            onClick={() => onMarketChange('IN')}
            className={`flex items-center gap-1.5 px-2 sm:px-2.5 py-1 rounded-md transition-all ${
              currentMarket === 'IN'
                ? 'bg-indigo-950 text-indigo-300 border border-indigo-700/80 font-bold shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                currentMarket === 'IN' ? 'bg-indigo-400' : 'bg-slate-500'
              }`}
            ></span>
            <span className="hidden sm:inline">India</span>
            <span className="sm:hidden font-mono text-[11px]">IN</span>
          </button>
        </div>

        {/* Regime Chip */}
        {regime && (
          <div
            className={`hidden md:flex items-center gap-2 px-2.5 py-1 rounded-lg text-xs font-semibold border ${getRegimeColor(
              regime.status
            )}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
            <span>
              {currentMarket} {regime.status}
            </span>
            <span className="hidden xl:inline text-[11px] font-mono text-slate-400 border-l border-slate-700/60 pl-2">
              {regime.index_symbol
                ? `${regime.index_symbol.replace('^', '')}: ${Number(regime.last_close || 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
                : (currentMarket === 'IN' ? 'NIFTY: 24,180' : 'S&P: 5,860')}
            </span>
          </div>
        )}

        {/* Custom Price Alerts Trigger */}
        {onOpenCustomAlerts && (
          <button
            onClick={onOpenCustomAlerts}
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-amber-300 transition"
            title="Custom Price Alerts"
          >
            <Bell className="w-4 h-4 text-amber-400" />
          </button>
        )}

        {/* Manual Refresh */}
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition disabled:opacity-50"
            title="Refresh Quotes & Regime"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        )}
      </div>
    </header>
  );
};

