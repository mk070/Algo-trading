import React, { useEffect, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Navbar } from './components/Navbar';
import { BacktestsPage } from './pages/BacktestsPage';
import { DashboardPage } from './pages/DashboardPage';
import { JournalPage } from './pages/JournalPage';
import { NewsPage } from './pages/NewsPage';
import { PositionsPage } from './pages/PositionsPage';
import { SettingsPage } from './pages/SettingsPage';
import { SystemHealthPage } from './pages/SystemHealthPage';
import { WatchlistPage } from './pages/WatchlistPage';
import { apiClient } from './api/client';
import { RegimeResult } from './types';

export const App: React.FC = () => {
  const [currentMarket, setCurrentMarket] = useState<'IN' | 'US'>('IN');
  const [regime, setRegime] = useState<RegimeResult | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveAlertToast, setLiveAlertToast] = useState<any | null>(null);

  const fetchRegime = async () => {
    try {
      const data = await apiClient.getRegime(currentMarket);
      setRegime(data);
    } catch (e) {
      console.error('Error fetching regime:', e);
    }
  };

  useEffect(() => {
    fetchRegime();
  }, [currentMarket]);

  // Connect to SSE stream
  useEffect(() => {
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource('/api/stream');
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

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
        <Navbar
          currentMarket={currentMarket}
          onMarketChange={setCurrentMarket}
          regime={regime}
          isStreaming={isStreaming}
          onRefresh={fetchRegime}
        />

        {/* Live SSE Alert Toast Banner */}
        {liveAlertToast && (
          <div className="fixed bottom-6 right-6 z-50 max-w-sm bg-slate-900 border-2 border-indigo-500 rounded-xl p-4 shadow-2xl animate-bounce">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
                🚨 Live Alert: {liveAlertToast.type}
              </span>
              <button
                onClick={() => setLiveAlertToast(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>
            <h4 className="text-sm font-bold text-white mb-1">{liveAlertToast.title}</h4>
            <p className="text-xs text-slate-300 line-clamp-2">{liveAlertToast.body}</p>
          </div>
        )}

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl w-full mx-auto p-4 lg:p-8">
          <Routes>
            <Route path="/" element={<DashboardPage currentMarket={currentMarket} />} />
            <Route path="/watchlist" element={<WatchlistPage currentMarket={currentMarket} />} />
            <Route path="/positions" element={<PositionsPage currentMarket={currentMarket} />} />
            <Route path="/journal" element={<JournalPage />} />
            <Route path="/backtests" element={<BacktestsPage currentMarket={currentMarket} />} />
            <Route path="/news" element={<NewsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/system" element={<SystemHealthPage />} />
          </Routes>
        </main>

        {/* Persistent Rule 4 Disclaimer Footer */}
        <footer className="border-t border-slate-900 bg-slate-950 px-4 py-4 text-center text-[11px] text-slate-500">
          <div className="max-w-7xl mx-auto">
            <strong>Mandatory Legal & Risk Disclaimer:</strong> Signals are rules-based decision support, not financial advice. All orders are manually placed by the owner at their broker. Past and backtested performance does not guarantee future results.
          </div>
        </footer>
      </div>
    </BrowserRouter>
  );
};

