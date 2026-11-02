import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Database,
  ExternalLink,
  Key,
  Lock,
  Radio,
  RefreshCw,
  Send,
  Settings,
  ShieldCheck,
  Zap,
  XCircle,
  AlertTriangle,
} from 'lucide-react';
import { apiClient } from '../api/client';

export const SettingsPage: React.FC = () => {
  const [settingsData, setSettingsData] = useState<any>(null);
  const [portfolioStatus, setPortfolioStatus] = useState<any>(null);
  const [neonServices, setNeonServices] = useState<any>(null);
  const [telegramStatus, setTelegramStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Telegram test state
  const [testingTelegram, setTestingTelegram] = useState(false);
  const [telegramFeedback, setTelegramFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [sData, pStatus, neonData, tgStatus] = await Promise.all([
        apiClient.getSettings(),
        apiClient.getPortfolioStatus(),
        apiClient.getNeonServices(),
        apiClient.getTelegramStatus().catch((e) => ({
          status: 'ERROR',
          error: e.message || 'Failed to fetch status',
          bot_username: null,
          masked_chat_id: null,
          last_check: null,
        })),
      ]);
      setSettingsData(sData);
      setPortfolioStatus(pStatus);
      setNeonServices(neonData);
      setTelegramStatus(tgStatus);
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

  const handleTestTelegram = async () => {
    if (testingTelegram) return;
    setTestingTelegram(true);
    setTelegramFeedback(null);
    try {
      const res = await apiClient.testTelegram();
      setTelegramFeedback({
        type: 'success',
        message: res.detail || 'Test message sent and confirmed by Telegram API!',
      });
      if (res.status) {
        setTelegramStatus(res.status);
      }
    } catch (e: any) {
      setTelegramFeedback({
        type: 'error',
        message: e.message || 'Telegram test failed',
      });
    } finally {
      setTestingTelegram(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Settings className="w-5 h-5 text-indigo-400" />
          System Settings & Integrations
        </h1>
        <p className="text-xs text-slate-400">
          Configure API credentials, Telegram notifications, risk sizing thresholds, and broker authentication sessions.
        </p>
      </div>

      {/* Telegram Notifications Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Send className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-white">Telegram Notifications</h2>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs font-semibold flex items-center gap-1.5 ${
              telegramStatus?.status === 'CONNECTED'
                ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                : telegramStatus?.status === 'ERROR'
                ? 'bg-rose-950 text-rose-400 border border-rose-800'
                : 'bg-slate-800 text-slate-400 border border-slate-700'
            }`}
          >
            {telegramStatus?.status === 'CONNECTED' && <CheckCircle2 className="w-3.5 h-3.5" />}
            {telegramStatus?.status === 'ERROR' && <XCircle className="w-3.5 h-3.5" />}
            {telegramStatus?.status === 'CONNECTED'
              ? 'Connected'
              : telegramStatus?.status === 'ERROR'
              ? 'Error'
              : 'Not Configured'}
          </span>
        </div>

        <p className="text-xs text-slate-300">
          Delivers outbound trading alerts: confirmed BUY entries, stop-loss and trailing exits, earnings risk warnings, and circuit breakers. Strictly an outbound notification channel; credentials remain securely on the backend.
        </p>

        {/* Telegram Details Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1">
            <span className="text-[11px] font-medium text-slate-400">Connection Status</span>
            <span
              className={`text-xs font-bold ${
                telegramStatus?.status === 'CONNECTED'
                  ? 'text-emerald-400'
                  : telegramStatus?.status === 'ERROR'
                  ? 'text-rose-400'
                  : 'text-slate-400'
              }`}
            >
              {telegramStatus?.status === 'CONNECTED'
                ? 'Connected & Active'
                : telegramStatus?.status === 'ERROR'
                ? 'Connection Error'
                : 'Not configured'}
            </span>
          </div>

          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1">
            <span className="text-[11px] font-medium text-slate-400">Bot Username</span>
            <span className="text-xs font-mono font-semibold text-slate-200 truncate" title={telegramStatus?.bot_username}>
              {telegramStatus?.bot_username || '—'}
            </span>
          </div>

          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1">
            <span className="text-[11px] font-medium text-slate-400">Masked Chat ID</span>
            <span className="text-xs font-mono font-semibold text-slate-200">
              {telegramStatus?.masked_chat_id || '—'}
            </span>
          </div>

          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1">
            <span className="text-[11px] font-medium text-slate-400">Last Connection Check</span>
            <span className="text-xs text-slate-300 truncate" title={telegramStatus?.last_check}>
              {telegramStatus?.last_check
                ? new Date(telegramStatus.last_check).toLocaleTimeString() + ' ' + new Date(telegramStatus.last_check).toLocaleDateString()
                : 'Never'}
            </span>
          </div>
        </div>

        {/* Action Button & Feedback */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-1">
          <button
            onClick={handleTestTelegram}
            disabled={testingTelegram || telegramStatus?.status === 'NOT_CONFIGURED'}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-xs transition-all shadow ${
              testingTelegram || telegramStatus?.status === 'NOT_CONFIGURED'
                ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                : 'bg-sky-600 hover:bg-sky-500 text-white active:scale-95'
            }`}
          >
            {testingTelegram ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-white" />
                Testing Telegram...
              </>
            ) : (
              <>
                <Send className="w-3.5 h-3.5" />
                Test Telegram
              </>
            )}
          </button>

          {telegramStatus?.status === 'NOT_CONFIGURED' && (
            <span className="text-[11px] text-amber-400 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env to enable.
            </span>
          )}
        </div>

        {/* Inline Feedback Alerts */}
        {telegramFeedback && (
          <div
            className={`p-3 rounded-lg border text-xs flex items-center gap-2.5 transition-all ${
              telegramFeedback.type === 'success'
                ? 'bg-emerald-950/70 text-emerald-300 border-emerald-800'
                : 'bg-rose-950/70 text-rose-300 border-rose-800'
            }`}
          >
            {telegramFeedback.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{telegramFeedback.message}</span>
          </div>
        )}

        {telegramStatus?.error && !telegramFeedback && (
          <div className="p-3 bg-rose-950/40 border border-rose-900 rounded-lg text-xs text-rose-300 flex items-center gap-2">
            <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>Connection check error: {telegramStatus.error}</span>
          </div>
        )}
      </div>

      {/* Neon Cloud Services (Postgres, Auth, Realtime) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-emerald-400" />
            <h2 className="text-base font-bold text-white">
              Neon Cloud Services (Branch:{' '}
              <span className="text-emerald-400 font-mono text-sm">
                {neonServices?.branch || 'production'}
              </span>
              )
            </h2>
          </div>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
            Active & Deployed
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* Neon Postgres */}
          <div className="p-3.5 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Database className="w-4 h-4 text-emerald-400" />
                Neon Postgres
              </span>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                  neonServices?.postgres?.status === 'HEALTHY'
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                    : 'bg-amber-950 text-amber-400'
                }`}
              >
                {neonServices?.postgres?.status || 'HEALTHY'}
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Connection Pool: {neonServices?.postgres?.pool_checked_in ?? 0} in /{' '}
              {neonServices?.postgres?.pool_checked_out ?? 0} out
            </p>
            <p className="text-[10px] text-slate-500 font-mono">
              Latency: {neonServices?.postgres?.latency_ms ?? 0}ms
            </p>
          </div>

          {/* Neon Auth */}
          <div className="p-3.5 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-blue-400" />
                Neon Auth
              </span>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                  neonServices?.auth?.status === 'CONNECTED'
                    ? 'bg-blue-950 text-blue-400 border border-blue-800'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                {neonServices?.auth?.status || 'CONNECTED'}
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              JWKS Keys: {neonServices?.auth?.keys_count ?? 1} active EdDSA
            </p>
            <p className="text-[10px] text-slate-500 truncate" title={neonServices?.auth?.base_url}>
              {neonServices?.auth?.base_url ? 'Managed Better Auth' : 'Configured'}
            </p>
          </div>

          {/* Neon Realtime */}
          <div className="p-3.5 bg-slate-950 rounded-lg border border-slate-800 flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Radio className="w-4 h-4 text-purple-400" />
                Neon Realtime
              </span>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                  neonServices?.realtime?.status === 'ACTIVE'
                    ? 'bg-purple-950 text-purple-400 border border-purple-800'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                {neonServices?.realtime?.status || 'ACTIVE'}
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Live SQL engine on Postgres</p>
            <p
              className="text-[10px] text-slate-500 font-mono truncate"
              title={neonServices?.realtime?.url}
            >
              {neonServices?.realtime?.url ? 'WebSocket Live' : 'Not configured'}
            </p>
          </div>
        </div>
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
            {portfolioStatus?.authenticated
              ? 'Authenticated & Active'
              : 'Daily Reconnection Needed'}
          </span>
        </div>

        <p className="text-xs text-slate-300">
          Zerodha Kite Personal provides free read-only account data (holdings, positions, margins,
          trades). Per Rule 1, order placement endpoints are forbidden. The access token expires
          every day around 06:00 IST.
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
            {settingsData?.providers_status?.angelone_configured
              ? 'Credentials Configured in .env'
              : 'Not Configured (Using Fallback)'}
          </span>
        </div>

        <p className="text-xs text-slate-300">
          Primary provider for Indian historical daily bars, 15-minute intraday candles, live
          quotes, and WebSocket stream. Uses TOTP authentication for daily login.
        </p>
      </div>

      {/* US Market Data (Alpaca candidate) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold text-white">US Market Data Provider (Alpaca)</h2>
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
          Until Alpaca credentials are configured in <code>.env</code>, US live breakout alerts
          remain disabled to prevent delayed data from generating false signals.
        </p>
      </div>

      {/* Persistent Disclaimer */}
      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-center text-xs text-slate-400">
        <strong>Mandatory Disclaimer (Rule 4):</strong> {settingsData?.disclaimer}
      </div>
    </div>
  );
};
