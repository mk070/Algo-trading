import React from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, BarChart2, BookOpen, Clock, Compass, FileText, Newspaper, RefreshCw, Settings, ShieldCheck } from 'lucide-react';
import { RegimeResult } from '../types';

interface NavbarProps {
  currentMarket: 'IN' | 'US';
  onMarketChange: (m: 'IN' | 'US') => void;
  regime?: RegimeResult | null;
  isStreaming: boolean;
  onRefresh?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentMarket,
  onMarketChange,
  regime,
  isStreaming,
  onRefresh,
}) => {
  const getRegimeColor = (status?: string) => {
    switch (status) {
      case 'BULLISH':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'CAUTION':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/30';
      case 'WEAK':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  const navItems = [
    { to: '/', label: 'Dashboard', icon: Compass },
    { to: '/watchlist', label: 'Watchlist & Live', icon: Clock },
    { to: '/positions', label: 'Positions & Portfolio', icon: BarChart2 },
    { to: '/journal', label: 'Journal & Stats', icon: BookOpen },
    { to: '/backtests', label: 'Backtests', icon: Activity },
    { to: '/news', label: 'News & Disclosures', icon: Newspaper },
    { to: '/settings', label: 'Settings', icon: Settings },
    { to: '/system', label: 'System Health', icon: ShieldCheck },
  ];

  return (
    <header className="sticky top-0 z-50 bg-slate-950/95 backdrop-blur border-b border-slate-800 px-4 lg:px-8 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
        {/* Brand & Market Switcher */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-black text-white text-base shadow-indigo-500/20 shadow-md">
              S
            </div>
            <div>
              <span className="font-extrabold text-base tracking-tight text-white block leading-none">
                SWING INTEL
              </span>
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block">
                Decision Support
              </span>
            </div>
          </div>

          {/* Market selector (IN / US) */}
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs font-semibold">
            <button
              onClick={() => onMarketChange('IN')}
              className={`px-3 py-1 rounded-md transition-all ${currentMarket === 'IN' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
            >
              NSE India (₹)
            </button>
            <button
              onClick={() => onMarketChange('US')}
              className={`px-3 py-1 rounded-md transition-all ${currentMarket === 'US' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
            >
              US Markets ($)
            </button>
          </div>

          {/* Regime Badge */}
          {regime && (
            <div className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${getRegimeColor(regime.status)}`}>
              <span className="w-2 h-2 rounded-full bg-current"></span>
              {currentMarket} Regime: {regime.status}
            </div>
          )}
        </div>

        {/* Right side: Live SSE Pulse + Refresh + Disclaimer badge */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-400 font-medium">
            <span
              className={`w-2 h-2 rounded-full ${isStreaming ? 'bg-emerald-400 animate-ping' : 'bg-slate-600'}`}
              title={isStreaming ? 'Connected to Live Server-Sent Events' : 'Connecting to Stream...'}
            ></span>
            <span className="hidden sm:inline">{isStreaming ? 'Live Feed' : 'Connecting'}</span>
          </div>

          {onRefresh && (
            <button
              onClick={onRefresh}
              className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-colors"
              title="Refresh Market Data"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}

          <div className="hidden xl:block text-[11px] text-slate-500 italic max-w-xs truncate">
            Signals are rules-based, not financial advice.
          </div>
        </div>
      </div>

      {/* Navigation Sub-bar */}
      <nav className="max-w-7xl mx-auto flex items-center gap-1 overflow-x-auto pt-2 text-xs font-medium scrollbar-none">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-lg whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-indigo-400 font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                }`
              }
            >
              <Icon className="w-3.5 h-3.5" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>
    </header>
  );
};

