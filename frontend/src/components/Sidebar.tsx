import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  ExternalLink,
  HelpCircle,
  LucideIcon,
  Search,
  Shield,
  Star,
  User,
  X,
  Zap,
} from 'lucide-react';
import { NAV_GROUPS } from './navItems';

interface SidebarProps {
  currentMarket: 'IN' | 'US';
  onOpenSearch: () => void;
  onSelectStock?: (symbol: string) => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
  feedStatus?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentMarket,
  onOpenSearch,
  onSelectStock,
  isMobileOpen = false,
  onCloseMobile,
  feedStatus = 'LIVE',
}) => {
  const location = useLocation();

  // Curated pinned stocks per market
  const pinnedStocks = currentMarket === 'IN'
    ? [
        { symbol: 'TMPV', name: 'Tata Motors PV', price: '₹644.00', chg: '+0.00%', isPos: true },
        { symbol: 'RELIANCE', name: 'Reliance Ind.', price: '₹1,163.55', chg: '-0.44%', isPos: false },
        { symbol: 'TCS', name: 'Tata Consultancy', price: '₹2,496.00', chg: '+0.62%', isPos: true },
        { symbol: 'HDFCBANK', name: 'HDFC Bank Ltd', price: '₹692.30', chg: '+1.07%', isPos: true },
      ]
    : [
        { symbol: 'SPY', name: 'S&P 500 ETF', price: '$760.11', chg: '+0.58%', isPos: true },
        { symbol: 'QQQ', name: 'Invesco QQQ', price: '$693.82', chg: '+0.48%', isPos: true },
        { symbol: 'NVDA', name: 'NVIDIA Corp', price: '$141.50', chg: '+2.14%', isPos: true },
        { symbol: 'AAPL', name: 'Apple Inc', price: '$232.80', chg: '-0.32%', isPos: false },
      ];

  const handleStockClick = (symbol: string) => {
    if (onCloseMobile) onCloseMobile();
    if (onSelectStock) onSelectStock(symbol);
  };

  const handleSearchClick = () => {
    if (onCloseMobile) onCloseMobile();
    onOpenSearch();
  };

  const sidebarContent = (
    <aside className="w-full sm:w-64 h-full bg-slate-950 border-r border-slate-800 flex flex-col justify-between select-none">
      {/* Top Section */}
      <div className="flex-1 overflow-y-auto scrollbar-none p-3.5 space-y-4">
        {/* Brand Header */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center font-black text-slate-950 text-base shadow-sm shrink-0">
              S
            </div>
            <div>
              <span className="font-extrabold text-sm tracking-tight text-white block leading-tight">
                SWING INTEL
              </span>
              <span className="text-[10px] text-slate-400 font-medium block">
                OpenStock Terminal
              </span>
            </div>
          </div>
          {onCloseMobile && (
            <button
              onClick={onCloseMobile}
              className="lg:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 min-h-[40px] min-w-[40px] flex items-center justify-center"
              aria-label="Close navigation menu"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Top Search CTA Button (OpenStock Style) */}
        <button
          onClick={handleSearchClick}
          className="w-full bg-indigo-500 hover:bg-indigo-400 text-slate-950 font-bold py-2.5 px-3 rounded-lg text-xs flex items-center justify-between shadow transition-all duration-150 group min-h-[40px]"
          title="Search symbols (Ctrl+K or Cmd+K)"
        >
          <span className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-slate-950" />
            Search stocks
          </span>
          <kbd className="text-[10px] font-mono bg-indigo-600/30 px-1.5 py-0.5 rounded text-slate-950 font-bold">
            ⌘K
          </kbd>
        </button>

        {/* Navigation Groups */}
        <nav className="space-y-3 pt-1">
          {NAV_GROUPS.map((group) => (
            <div key={group.group} className="space-y-0.5">
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                {group.group}
              </div>
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.to;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={onCloseMobile}
                    className={`flex items-center justify-between px-2.5 py-2 rounded-lg text-xs font-medium transition-colors min-h-[38px] ${
                      isActive
                        ? 'bg-slate-800 text-white font-semibold border-l-2 border-indigo-500'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : 'text-slate-400'}`} />
                      <span>{item.label}</span>
                    </div>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Pinned Watching Section */}
        <div className="pt-2 border-t border-slate-800/80">
          <div className="flex items-center justify-between px-2 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1">
              <Star className="w-3 h-3 text-amber-400 fill-amber-400" /> Watching
            </span>
            <span className="text-[10px] font-mono text-slate-500">{pinnedStocks.length}</span>
          </div>
          <div className="space-y-1">
            {pinnedStocks.map((s) => (
              <button
                key={s.symbol}
                onClick={() => handleStockClick(s.symbol)}
                className="w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-xs hover:bg-slate-900 transition-colors text-left group min-h-[38px]"
              >
                <div>
                  <span className="font-bold text-slate-200 group-hover:text-white block leading-none">
                    {s.symbol}
                  </span>
                  <span className="text-[10px] text-slate-500 truncate block max-w-[110px]">
                    {s.name}
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-mono text-[11px] font-semibold text-slate-200 block leading-none">
                    {s.price}
                  </span>
                  <span
                    className={`font-mono text-[10px] ${
                      s.isPos ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {s.chg}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Broker Identity & Compliance Tile */}
      <div className="p-3 border-t border-slate-800 space-y-2.5 bg-slate-950">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-slate-800 border border-slate-700 flex items-center justify-center font-bold text-xs text-indigo-400 font-mono shrink-0">
              Z
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold text-slate-200 leading-tight truncate">
                madhan (SBV367)
              </div>
              <div className="text-[10px] text-emerald-400 flex items-center gap-1 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0"></span>
                Zerodha Connected
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between px-1 text-[10px] text-slate-400 font-mono">
          <span className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                feedStatus === 'LIVE' ? 'bg-emerald-400 animate-ping' : 'bg-amber-400'
              }`}
            ></span>
            Angel One: {feedStatus}
          </span>
          <span className="text-slate-500">v2.4</span>
        </div>

        <div className="px-1 text-[9px] text-slate-500 leading-tight">
          Strictly manual broker execution.
        </div>
      </div>
    </aside>
  );

  return (
    <>
      {/* Desktop static sidebar */}
      <div className="hidden lg:block h-screen sticky top-0 shrink-0 w-64">
        {sidebarContent}
      </div>

      {/* Mobile drawer overlay */}
      {isMobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm transition-opacity"
            onClick={onCloseMobile}
          />
          <div className="relative z-10 w-72 max-w-[85vw] h-full shadow-2xl">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};
