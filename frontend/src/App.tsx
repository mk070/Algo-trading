import React, { useEffect, useState } from 'react';
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Bell, ShieldAlert, Sparkles, X } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { Topbar, WorkspaceTab } from './components/Topbar';
import { QuickSearchModal } from './components/QuickSearchModal';
import { CustomAlertsModal } from './components/CustomAlertsModal';
import { ChartModal } from './components/ChartModal';
import { ALL_NAV_ITEMS } from './components/navItems';
import { BacktestsPage } from './pages/BacktestsPage';
import { DashboardPage } from './pages/DashboardPage';
import { JournalPage } from './pages/JournalPage';
import { NewsPage } from './pages/NewsPage';
import { PositionsPage } from './pages/PositionsPage';
import { SettingsPage } from './pages/SettingsPage';
import { SystemHealthPage } from './pages/SystemHealthPage';
import { WatchlistPage } from './pages/WatchlistPage';
import { HeatmapPage } from './pages/HeatmapPage';
import { API_BASE, apiClient } from './api/client';
import { RegimeResult } from './types';

export const AppContent: React.FC = () => {
  const [currentMarket, setCurrentMarket] = useState<'IN' | 'US'>('IN');
  const [regime, setRegime] = useState<RegimeResult | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveAlertToast, setLiveAlertToast] = useState<any | null>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isCustomAlertsOpen, setIsCustomAlertsOpen] = useState(false);
  const [globalChartSymbol, setGlobalChartSymbol] = useState<string | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // OpenStock Workspace Tabs
  const [activeTabs, setActiveTabs] = useState<WorkspaceTab[]>([
    { id: 'overview', label: 'Overview', to: '/' },
    { id: 'watchlist', label: 'Watchlist', to: '/watchlist' },
    { id: 'heatmap', label: 'Market Heatmap', to: '/heatmap' },
  ]);
  const [activeTabId, setActiveTabId] = useState<string>('overview');

  const navigate = useNavigate();
  const location = useLocation();

  // Sync route changes with workspace tabs
  useEffect(() => {
    const path = location.pathname;
    if (path === '/') {
      setActiveTabId('overview');
    } else if (path === '/watchlist') {
      setActiveTabId('watchlist');
    } else {
      const match = ALL_NAV_ITEMS.find((n) => n.to === path);
      if (match) {
        const tabId = match.to.replace('/', '');
        setActiveTabs((prev) => {
          if (!prev.some((t) => t.id === tabId)) {
            return [...prev, { id: tabId, label: match.label, to: match.to, closable: true }];
          }
          return prev;
        });
        setActiveTabId(tabId);
      }
    }
  }, [location.pathname]);

  const handleSelectTab = (tabId: string) => {
    setActiveTabId(tabId);
    const tab = activeTabs.find((t) => t.id === tabId);
    if (tab?.to) {
      navigate(tab.to);
    } else if (tab?.symbol) {
      setGlobalChartSymbol(tab.symbol);
    }
  };

  const handleCloseTab = (tabId: string) => {
    setActiveTabs((prev) => {
      const next = prev.filter((t) => t.id !== tabId);
      if (activeTabId === tabId) {
        const last = next[next.length - 1];
        if (last) {
          setActiveTabId(last.id);
          if (last.to) navigate(last.to);
          else if (last.symbol) setGlobalChartSymbol(last.symbol);
        }
      }
      return next;
    });
    if (globalChartSymbol && tabId === `chart-${globalChartSymbol}`) {
      setGlobalChartSymbol(null);
    }
  };

  const handleOpenChartTab = (symbol: string) => {
    const tabId = `chart-${symbol}`;
    if (!activeTabs.some((t) => t.id === tabId)) {
      setActiveTabs((prev) => [...prev, { id: tabId, label: symbol, symbol, closable: true }]);
    }
    setActiveTabId(tabId);
    setGlobalChartSymbol(symbol);
  };

  const handleAddToWatchlist = async (symbol: string) => {
    try {
      const lists = await apiClient.getWatchlists(currentMarket);
      const targetList = lists?.[0];
      if (targetList) {
        await apiClient.addWatchlistItem(targetList.id, { symbol, notes: 'Added via Quick Search' });
        alert(`Added ${symbol} to watchlist "${targetList.name}"!`);
      }
    } catch (e) {
      alert(`Error adding ${symbol} to watchlist: ` + e);
    }
  };

  const fetchRegime = async () => {
    try {
      setIsRefreshing(true);
      const data = await apiClient.getRegime(currentMarket);
      setRegime(data);
    } catch (e) {
      console.error('Error fetching regime:', e);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRegime();
    // 5s periodic background refresh for topbar market index points & regime
    const interval = setInterval(() => {
      fetchRegime();
    }, 5000);
    return () => clearInterval(interval);
  }, [currentMarket]);

  // Global keyboard shortcut for Quick Search (Ctrl/Cmd + K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Connect to SSE stream
  useEffect(() => {
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource(`${API_BASE}/stream`);
      eventSource.onopen = () => setIsStreaming(true);
      eventSource.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data);
          if (payload.type && payload.type !== 'CONNECTED') {
            setLiveAlertToast(payload);
            setTimeout(() => setLiveAlertToast(null), 8000);
          }
        } catch (err) {
          // heartbeat
        }
      };
      eventSource.onerror = () => setIsStreaming(false);
    } catch (e) {
      setIsStreaming(false);
    }

    return () => {
      if (eventSource) eventSource.close();
    };
  }, []);

  const handleSelectSymbol = (symbol: string) => {
    navigate(`/watchlist?symbol=${encodeURIComponent(symbol)}`);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col lg:flex-row font-sans overflow-x-hidden">
      {/* Left Sidebar (OpenStock Institutional Layout) */}
      <Sidebar
        currentMarket={currentMarket}
        onOpenSearch={() => setIsSearchOpen(true)}
        onSelectStock={handleOpenChartTab}
        isMobileOpen={isMobileMenuOpen}
        onCloseMobile={() => setIsMobileMenuOpen(false)}
        feedStatus={isStreaming ? 'LIVE' : 'DELAYED'}
      />

      {/* Main Terminal Shell */}
      <div className="flex-1 flex flex-col min-w-0 w-full overflow-x-hidden">
        {/* Sticky Topbar with Workspace Tabs & Market Controls */}
        <Topbar
          currentMarket={currentMarket}
          onMarketChange={setCurrentMarket}
          regime={regime}
          isStreaming={isStreaming}
          onRefresh={fetchRegime}
          isRefreshing={isRefreshing}
          onOpenSearch={() => setIsSearchOpen(true)}
          onOpenCustomAlerts={() => setIsCustomAlertsOpen(true)}
          onToggleMobileMenu={() => setIsMobileMenuOpen(true)}
          activeTabs={activeTabs}
          activeTabId={activeTabId}
          onSelectTab={handleSelectTab}
          onCloseTab={handleCloseTab}
        />

        {/* Quick Search Modal (Ctrl/Cmd+K) */}
        <QuickSearchModal
          isOpen={isSearchOpen}
          onClose={() => setIsSearchOpen(false)}
          currentMarket={currentMarket}
          onSelectSymbol={handleSelectSymbol}
          onOpenChart={handleOpenChartTab}
          onAddToWatchlist={handleAddToWatchlist}
          onViewNews={(sym) => navigate(`/news?symbol=${encodeURIComponent(sym)}`)}
        />

        {/* Interactive Candlestick Chart Modal */}
        <ChartModal
          isOpen={Boolean(globalChartSymbol)}
          onClose={() => setGlobalChartSymbol(null)}
          symbol={globalChartSymbol}
          market={currentMarket}
        />

        {/* Custom Price Alerts Modal */}
        <CustomAlertsModal
          isOpen={isCustomAlertsOpen}
          onClose={() => setIsCustomAlertsOpen(false)}
          currentMarket={currentMarket}
        />

        {/* Live SSE Alert Toast Banner (Anti-Slop SVG, Zero Emojis) */}
        {liveAlertToast && (
          <div className="fixed bottom-6 right-6 z-50 max-w-sm bg-slate-900 border border-indigo-500/80 rounded-xl p-4 shadow-2xl animate-bounce">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
                <Bell className="w-3.5 h-3.5 text-indigo-400" />
                Live Alert: {liveAlertToast.type}
              </span>
              <button
                onClick={() => setLiveAlertToast(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <h4 className="text-sm font-bold text-white mb-1">{liveAlertToast.title}</h4>
            <p className="text-xs text-slate-300 line-clamp-2">{liveAlertToast.body}</p>
          </div>
        )}

        {/* Primary Page Content Canvas */}
        <main className="flex-1 max-w-[1600px] w-full mx-auto p-3 sm:p-4 lg:p-6 min-w-0">
          <Routes>
            <Route path="/" element={<DashboardPage currentMarket={currentMarket} onMarketChange={setCurrentMarket} />} />
            <Route path="/watchlist" element={<WatchlistPage currentMarket={currentMarket} />} />
            <Route path="/heatmap" element={<HeatmapPage currentMarket={currentMarket} onMarketChange={setCurrentMarket} />} />
            <Route path="/positions" element={<PositionsPage currentMarket={currentMarket} />} />
            <Route path="/journal" element={<JournalPage />} />
            <Route path="/backtests" element={<BacktestsPage currentMarket={currentMarket} />} />
            <Route path="/news" element={<NewsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/system" element={<SystemHealthPage />} />
          </Routes>
        </main>

        {/* Persistent Institutional Risk Disclaimer Footer */}
        <footer className="border-t border-slate-900 bg-slate-950 px-4 py-3.5 text-center text-[11px] text-slate-500">
          <div className="max-w-[1600px] mx-auto">
            <strong>Mandatory Legal & Risk Disclaimer:</strong> Signals are rules-based decision support, not financial advice. All orders are manually placed by the owner at their broker. Past and backtested performance does not guarantee future results.
          </div>
        </footer>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
};
