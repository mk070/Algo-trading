import React, { useEffect, useState } from 'react';
import { CheckCircle2, ExternalLink, Key, Lock, RefreshCw, Send, Settings, ShieldCheck, XCircle } from 'lucide-react';
import { apiClient } from '../api/client';

export const SettingsPage: React.FC = () => {
  const [settingsData, setSettingsData] = useState<any>(null);
  const [portfolioStatus, setPortfolioStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [testSent, setTestSent] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const [sData, pStatus] = await Promise.all([
        apiClient.getSettings(),
        apiClient.getPortfolioStatus(),
      ]);
      setSettingsData(sData);
      setPortfolioStatus(pStatus);
    } catch (e) {
      console.error('Error loading settings:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleConnectZerodha = async () => {
    try {
      const res = await apiClient.getKiteLoginUrl();
      if (res.login_url) {
        window.open(res.login_url, '_blank');
      }
    } catch (e) {
      alert('Error getting Kite login URL: ' + e);
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Settings className="w-5 h-5 text-indigo-400" />
          System Settings & Broker Integrations
        </h1>
        <p className="text-xs text-slate-400">
          Configure API credentials, risk sizing thresholds, and broker authentication sessions.
        </p>
      </div>

      {/* Zerodha Kite Connect Personal (Core Read-only) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Lock className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold text-white">
              Zerodha Kite Connect "Personal" (Strictly Read-Only)
            </h2>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
              portfolioStatus?.authenticated
                ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                : 'bg-amber-950 text-amber-300 border border-amber-800'
            }`}
          >
            {portfolioStatus?.authenticated ? 'Authenticated & Active' : 'Daily Reconnection Needed'}
          </span>
        </div>

        <p className="text-xs text-slate-300">
          Zerodha Kite Personal provides free read-only account data (holdings, positions, margins, trades). Per Rule 1, order placement endpoints are forbidden. The access token expires every day around 06:00 IST.
        </p>

        <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between flex-wrap gap-3 text-xs">
          <div>
            <span className="text-slate-500 block">Token Expiry:</span>
            <span className="font-mono text-slate-200">
              {portfolioStatus?.token_expiry || 'Not authenticated today'}
            </span>
          </div>
          <button
            onClick={handleConnectZerodha}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow transition-all"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Connect / Re-authenticate Zerodha
          </button>
        </div>
      </div>

      {/* Angel One SmartAPI (Core Market Data) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold text-white">
              Angel One SmartAPI (Core Indian Market Data)
            </h2>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
              settingsData?.providers_status?.angelone_configured
                ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                : 'bg-slate-800 text-slate-400'
            }`}
          >
            {settingsData?.providers_status?.angelone_configured ? 'Credentials Configured in .env' : 'Not Configured (Using Fallback)'}
          </span>
        </div>

        <p className="text-xs text-slate-300">
          Primary provider for Indian historical daily bars, 15-minute intraday candles, live quotes, and WebSocket stream. Uses TOTP authentication for daily login.
        </p>
      </div>

      {/* US Market Data (Alpaca candidate) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold text-white">
              US Market Data Provider (Alpaca)
            </h2>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
              settingsData?.providers_status?.alpaca_configured
                ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                : 'bg-slate-800 text-slate-400'
            }`}
          >
            {settingsData?.providers_status?.alpaca_configured ? 'Configured' : 'Not Configured'}
          </span>
        </div>
        <p className="text-xs text-slate-300">
          Until Alpaca credentials are configured in <code>.env</code>, US live breakout alerts remain disabled to prevent delayed data from generating false signals.
        </p>
      </div>

      {/* Persistent Disclaimer */}
      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-center text-xs text-slate-400">
        <strong>Mandatory Disclaimer (Rule 4):</strong> {settingsData?.disclaimer}
      </div>
    </div>
  );
};

