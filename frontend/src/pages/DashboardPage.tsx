import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, ArrowUpRight, BarChart3, CheckCircle, RefreshCw, Shield, Sparkles, TrendingUp } from 'lucide-react';
import { apiClient } from '../api/client';
import { CandleChart } from '../components/CandleChart';
import { SignalCard } from '../components/SignalCard';
import { TakeTradeModal } from '../components/TakeTradeModal';
import { Signal, TradePlan } from '../types';

interface DashboardPageProps {
  currentMarket: 'IN' | 'US';
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ currentMarket }) => {
  const [plan, setPlan] = useState<TradePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectedChartSymbol, setSelectedChartSymbol] = useState<string | null>(null);
  const [chartBars, setChartBars] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [tradeModalSignal, setTradeModalSignal] = useState<Signal | null>(null);

  const fetchPlan = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getTradePlan(currentMarket);
      setPlan(data);
    } catch (e) {
      console.error('Error fetching trade plan:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleRunScan = async () => {
    try {
      setScanning(true);
      const data = await apiClient.runScan(currentMarket);
      setPlan(data);
    } catch (e) {
      console.error('Error running scan:', e);
    } finally {
      setScanning(false);
    }
  };

  useEffect(() => {
    fetchPlan();
  }, [currentMarket]);

  const handleOpenChart = async (symbol: string) => {
    setSelectedChartSymbol(symbol);
    setChartLoading(true);
    try {
      const res = await apiClient.getBars(symbol, currentMarket, 120);
      setChartBars(res.bars || []);
    } catch (e) {
      console.error('Error fetching chart bars:', e);
      setChartBars([]);
    } finally {
      setChartLoading(false);
    }
  };

  const handleTakeTradeSubmit = async (data: any) => {
    try {
      await apiClient.createPosition(data);
      setTradeModalSignal(null);
      alert(`Position recorded successfully for ${data.symbol}! Remember to place your stop-loss order at your broker.`);
    } catch (e) {
      alert('Error creating position: ' + e);
    }
  };

  const selectedSignal = plan?.signals.find((s) => s.symbol === selectedChartSymbol);

  return (
    <div className="flex flex-col gap-6">
      {/* Top Banner: Market Regime & Overview */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs uppercase font-bold tracking-wider text-slate-400">
              {currentMarket === 'IN' ? 'NSE Nifty 50 Regime' : 'US S&P 500 Regime'}
            </span>
            <span
              className={`px-2 py-0.5 rounded text-xs font-bold ${
                plan?.regime.status === 'BULLISH'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : plan?.regime.status === 'CAUTION'
                  ? 'bg-amber-950 text-amber-400 border border-amber-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}
            >
              {plan?.regime.status || 'CHECKING...'}
            </span>
          </div>
          <p className="text-sm text-slate-300 font-medium">
            {plan?.regime.detail || 'Evaluating market trend conditions...'}
          </p>
          {plan?.regime && (
            <div className="flex items-center gap-4 text-xs font-mono text-slate-400 mt-2">
              <span>Close: <strong className="text-white">{plan.regime.last_close.toFixed(2)}</strong></span>
              <span>50 SMA: <strong className="text-blue-400">{plan.regime.sma50.toFixed(2)}</strong></span>
              <span>200 SMA: <strong className="text-purple-400">{plan.regime.sma200.toFixed(2)}</strong></span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRunScan}
            disabled={scanning}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs shadow-md transition-all"
          >
            <RefreshCw className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
            {scanning ? 'Running Universe Scan...' : 'Run Scan Now'}
          </button>
        </div>
      </div>

      {/* Warnings Banner if any */}
      {plan?.data_warnings && plan.data_warnings.length > 0 && (
        <div className="bg-amber-950/40 border border-amber-800/80 rounded-xl p-4 text-xs text-amber-300 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-1">
            <span className="font-bold">Data & Filter Warnings:</span>
            <ul className="list-disc pl-4 space-y-0.5">
              {plan.data_warnings.slice(0, 3).map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Interactive Chart Drawer / Modal if opened */}
      {selectedChartSymbol && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl relative">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-base text-white flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-indigo-400" />
              Technical Candlestick Chart: {selectedChartSymbol}
            </h3>
            <button
              onClick={() => setSelectedChartSymbol(null)}
              className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
            >
              Close Chart
            </button>
          </div>
          {chartLoading ? (
            <div className="h-72 flex items-center justify-center text-slate-400 text-sm">
              Loading technical indicators & candles...
            </div>
          ) : (
            <CandleChart
              symbol={selectedChartSymbol}
              bars={chartBars}
              trigger={selectedSignal?.trigger}
              stop={selectedSignal?.stop}
              target={selectedSignal?.target1}
            />
          )}
        </div>
      )}

      {/* Primary Section: Today's Ranked Trade Plan */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-400" />
              Today's Ranked Trade Plan ({plan?.signals.length || 0} Setups)
            </h2>
            <p className="text-xs text-slate-400">
              Screened from {plan?.universe_size || 0} constituents ({plan?.passed_filters || 0} passed Trend Template).
            </p>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            Session: {plan?.session_date || 'Today'}
          </span>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2].map((i) => (
              <div key={i} className="h-64 bg-slate-900/50 border border-slate-800 rounded-xl animate-pulse"></div>
            ))}
          </div>
        ) : !plan?.signals || plan.signals.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-10 text-center flex flex-col items-center justify-center gap-2">
            <Shield className="w-10 h-10 text-slate-600 mb-1" />
            <h3 className="text-base font-semibold text-slate-200">
              No Qualifying Setups Today
            </h3>
            <p className="text-xs text-slate-400 max-w-md">
              "Doing nothing is a valid trade." The market regime or trend template rules rejected extended or choppy stocks to protect your capital.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {plan.signals.map((sig) => (
              <SignalCard
                key={sig.id || sig.symbol}
                signal={sig}
                onOpenChart={handleOpenChart}
                onTakeTrade={(s) => setTradeModalSignal(s)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Experimental / Shadow Mode Setups (Setup P) */}
      {plan?.shadow_signals && plan.shadow_signals.length > 0 && (
        <div className="pt-4 border-t border-slate-800">
          <div className="mb-3">
            <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2">
              <Activity className="w-4 h-4 text-purple-400" />
              Experimental Setups (Shadow Mode: Pullback 20 EMA)
            </h3>
            <p className="text-xs text-slate-500">
              Running in shadow mode without live alerts to accumulate paper evidence before activation.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 opacity-75">
            {plan.shadow_signals.map((sig) => (
              <SignalCard
                key={sig.id || sig.symbol}
                signal={sig}
                onOpenChart={handleOpenChart}
              />
            ))}
          </div>
        </div>
      )}

      {/* Take Trade Modal */}
      {tradeModalSignal && (
        <TakeTradeModal
          signal={tradeModalSignal}
          onClose={() => setTradeModalSignal(null)}
          onSubmit={handleTakeTradeSubmit}
        />
      )}
    </div>
  );
};

