import React, { useState } from 'react';
import { Activity, AlertCircle, CheckCircle2, Compass, Info, Play, Shuffle, Sliders, XCircle } from 'lucide-react';
import { apiClient } from '../api/client';
import { BacktestMetrics, MonteCarloData, ScenarioLabResult } from '../types';

interface BacktestsPageProps {
  currentMarket: 'IN' | 'US';
}

export const BacktestsPage: React.FC<BacktestsPageProps> = ({ currentMarket }) => {
  const [activeTab, setActiveTab] = useState<'BACKTEST' | 'SCENARIO_LAB'>('BACKTEST');

  // Backtest state
  const [running, setRunning] = useState(false);
  const [metrics, setMetrics] = useState<BacktestMetrics | null>(null);
  const [monteCarlo, setMonteCarlo] = useState<MonteCarloData | null>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [dataCoverage, setDataCoverage] = useState<any>(null);
  const [setupFilter, setSetupFilter] = useState<'ALL' | 'VCP' | 'PULLBACK'>('ALL');
  const [capital, setCapital] = useState(17500);

  // Scenario Lab state
  const [labSymbol, setLabSymbol] = useState(currentMarket === 'IN' ? 'RELIANCE' : 'AAPL');
  const [labTrigger, setLabTrigger] = useState(currentMarket === 'IN' ? 2500 : 180);
  const [labStop, setLabStop] = useState(currentMarket === 'IN' ? 2380 : 172);
  const [labSimulations, setLabSimulations] = useState(10000);
  const [labSeed, setLabSeed] = useState(42);
  const [labRunning, setLabRunning] = useState(false);
  const [labResult, setLabResult] = useState<ScenarioLabResult | null>(null);

  const handleRunBacktest = async () => {
    try {
      setRunning(true);
      const res = await apiClient.runBacktest({
        market: currentMarket,
        capital,
        setup_filter: setupFilter,
      });
      setMetrics(res.metrics);
      setMonteCarlo(res.monte_carlo);
      setTrades(res.trades || []);
      setDataCoverage(res.data_coverage || null);
    } catch (e) {
      alert('Backtest execution error: ' + e);
    } finally {
      setRunning(false);
    }
  };

  const handleRunScenarioLab = async () => {
    try {
      setLabRunning(true);
      const res = await apiClient.runScenarioLab({
        symbol: labSymbol.trim().toUpperCase(),
        market: currentMarket,
        trigger: Number(labTrigger),
        stop: Number(labStop),
        n_simulations: Number(labSimulations),
        seed: Number(labSeed),
      });
      setLabResult(res);
    } catch (e) {
      alert('Scenario Lab simulation error: ' + e);
    } finally {
      setLabRunning(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Top Segmented Mode Selector */}
      <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
        <button
          onClick={() => setActiveTab('BACKTEST')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'BACKTEST' ? 'bg-indigo-600 text-white shadow-md' : 'text-slate-400 hover:text-white bg-slate-900'
          }`}
        >
          <Activity className="w-4 h-4" />
          Strategy Backtest & Acceptance Gates
        </button>
        <button
          onClick={() => setActiveTab('SCENARIO_LAB')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'SCENARIO_LAB' ? 'bg-indigo-600 text-white shadow-md' : 'text-slate-400 hover:text-white bg-slate-900'
          }`}
        >
          <Compass className="w-4 h-4" />
          Swing Replay & Scenario Lab (Spec 12.6)
        </button>
      </div>

      {activeTab === 'BACKTEST' ? (
        <>
          {/* Backtest Header & Controls */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-indigo-400" />
                Strategy Backtesting & Acceptance Gates
              </h1>
              <p className="text-xs text-slate-400">
                Event-driven daily simulation strictly enforcing conservative fill rules (Section 12.2) and full trading costs.
              </p>
              <p className="mt-1 text-[11px] text-amber-300">Max drawdown uses daily mark-to-market equity, includes open positions and liquidates remaining positions at the test end.</p>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-2 text-xs">
                <label className="text-slate-400">Setup:</label>
                <select
                  value={setupFilter}
                  onChange={(e) => setSetupFilter(e.target.value as any)}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
                >
                  <option value="ALL">All (VCP + Pullback)</option>
                  <option value="VCP">Setup V (Tight-Base VCP)</option>
                  <option value="PULLBACK">Setup P (Pullback 20 EMA)</option>
                </select>
              </div>

              <div className="flex items-center gap-2 text-xs">
                <label className="text-slate-400">Capital:</label>
                <input
                  type="number"
                  value={capital}
                  onChange={(e) => setCapital(Number(e.target.value))}
                  className="w-24 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
                />
              </div>

              <button
                onClick={handleRunBacktest}
                disabled={running}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs shadow-md transition-all"
              >
                <Play className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
                {running ? 'Simulating Strategy...' : 'Run Backtest'}
              </button>
            </div>
          </div>

          {/* Mandatory Survivorship Bias Notice */}
          <div className="p-3 bg-amber-950/40 border border-amber-800/80 rounded-lg text-xs text-amber-300 flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Honesty Notice (Section 12.3):</strong> Free data uses today's index constituents. Results carry survivorship bias. Treat performance as hypothetical decision support, never a guarantee of future profits.
            </span>
          </div>

          {/* Results View */}
          {metrics && (
            <div className="flex flex-col gap-6">
              {dataCoverage && (
                <div className={`rounded-lg border p-3 text-xs ${dataCoverage.warning ? 'border-amber-800 bg-amber-950/40 text-amber-300' : 'border-slate-700 bg-slate-900 text-slate-300'}`}>
                  Data coverage: requested {dataCoverage.requested_start}–{dataCoverage.requested_end}; available {dataCoverage.actual_start || 'none'}–{dataCoverage.actual_end || 'none'} ({dataCoverage.sessions} sessions, {dataCoverage.symbols_with_bars} symbols). {dataCoverage.warning || ''}
                </div>
              )}
              {/* Key Metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Simulated Trades</span>
                  <span className="text-xl font-bold font-mono text-white">{metrics.total_trades}</span>
                  <span className="text-[10px] text-slate-500 block mt-1">{metrics.winning_trades}W / {metrics.losing_trades}L</span>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Win Rate</span>
                  <span className="text-xl font-bold font-mono text-emerald-400">{metrics.win_rate}%</span>
                  <span className="text-[10px] text-slate-500 block mt-1">Winning trades %</span>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Net Profit Factor</span>
                  <span className="text-xl font-bold font-mono text-indigo-300">{metrics.profit_factor}</span>
                  <span className="text-[10px] text-slate-500 block mt-1">Net wins / net losses, after costs</span>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Expectancy / Trade</span>
                  <span className={`text-xl font-bold font-mono ${metrics.expectancy_r >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {metrics.expectancy_r >= 0 ? '+' : ''}{metrics.expectancy_r}R
                  </span>
                  <span className="text-[10px] text-slate-500 block mt-1">Net after all fees</span>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Max Drawdown</span>
                  <span className="text-xl font-bold font-mono text-rose-400">-{metrics.max_drawdown_pct}%</span>
            <span className="text-[10px] text-slate-500 block mt-1">Daily marked-to-market peak-to-trough</span>
                </div>
              </div>

              {/* Section 12.4 Acceptance Gates Checklist */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
                <h2 className="text-base font-bold text-white mb-2 flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  Out-of-Sample Acceptance Gates (Section 12.4)
                </h2>
                <p className="text-xs text-slate-400 mb-4">
                  All acceptance criteria must pass before considering live trading with real capital.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {metrics.acceptance_gates.map((gate, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-3 rounded-lg bg-slate-950 border border-slate-800/80 text-xs"
                    >
                      <div className="flex items-center gap-2.5">
                        {gate.passed ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400" />
                        )}
                        <div>
                          <span className="font-semibold text-slate-200 block">{gate.name}</span>
                          <span className="text-[11px] text-slate-500">Target: {gate.target}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className={`font-mono font-bold ${gate.passed ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {gate.actual}
                        </span>
                        <span className="text-[10px] text-slate-500 block">
                          {gate.passed ? 'PASSED' : 'FAILED'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Monte Carlo Simulation Breakdown */}
              {monteCarlo && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
                  <h2 className="text-base font-bold text-white mb-1 flex items-center gap-2">
                    <Shuffle className="w-5 h-5 text-purple-400" />
                    Monte Carlo Simulation ({monteCarlo.iterations} Shuffled Sequences)
                  </h2>
                  <p className="text-xs text-slate-400 mb-4">
                    Assesses sequencing risk and distribution of maximum drawdown.
                  </p>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs">
                      <span className="text-slate-500 block">Median Ending Equity</span>
                      <span className="text-sm font-bold text-white font-mono">₹{monteCarlo.median_ending_equity?.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs">
                      <span className="text-slate-500 block">5th - 95th Percentile Range</span>
                      <span className="text-sm font-bold text-indigo-300 font-mono">
                        ₹{monteCarlo.pct_5th_ending_equity?.toLocaleString('en-IN')} - ₹{monteCarlo.pct_95th_ending_equity?.toLocaleString('en-IN')}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs">
                      <span className="text-slate-500 block">Worst-Case Drawdown</span>
                      <span className="text-sm font-bold text-rose-400 font-mono">-{monteCarlo.worst_case_max_drawdown_pct}%</span>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs">
                      <span className="text-slate-500 block">Risk of Ruin (&gt; 30% DD)</span>
                      <span className="text-sm font-bold text-amber-400 font-mono">{monteCarlo.risk_of_ruin_pct}%</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Trade Preview */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
                <div className="p-4 border-b border-slate-800">
                  <h3 className="text-sm font-bold text-white">Simulated Trades Preview ({trades.length} Generated)</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 uppercase font-bold border-b border-slate-800 tracking-wider">
                      <tr>
                        <th className="px-4 py-3">Symbol</th>
                        <th className="px-4 py-3">Setup</th>
                        <th className="px-4 py-3">Entry</th>
                        <th className="px-4 py-3">Exit</th>
                        <th className="px-4 py-3">Hold Days</th>
                        <th className="px-4 py-3">Exit Reason</th>
                        <th className="px-4 py-3">Net P&L</th>
                        <th className="px-4 py-3">R-Multiple</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {trades.slice(0, 20).map((t, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/40">
                          <td className="px-4 py-2.5 font-bold text-white font-sans">{t.symbol}</td>
                          <td className="px-4 py-2.5 font-sans text-indigo-300">{t.setup}</td>
                          <td className="px-4 py-2.5 text-slate-300">{t.entry_price?.toFixed(2)}</td>
                          <td className="px-4 py-2.5 text-slate-300">{t.exit_price?.toFixed(2)}</td>
                          <td className="px-4 py-2.5 text-slate-400 font-sans">{t.holding_days}d</td>
                          <td className="px-4 py-2.5 font-sans text-slate-300">{t.exit_reason}</td>
                          <td className={`px-4 py-2.5 font-bold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {t.pnl >= 0 ? '+' : ''}{t.pnl?.toFixed(2)}
                          </td>
                          <td className={`px-4 py-2.5 font-bold ${t.r_multiple >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {t.r_multiple >= 0 ? '+' : ''}{t.r_multiple?.toFixed(2)}R
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        /* Scenario Lab View (Spec 12.6) */
        <div className="flex flex-col gap-6">
          {/* Lab Setup Panel */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-white flex items-center gap-2">
                <Compass className="w-5 h-5 text-indigo-400" />
                Swing Replay & Scenario Lab (Spec 12.6)
              </h1>
              <p className="text-xs text-slate-400">
                Point-in-time analogue matching + block bootstrap forward simulation. Informational research tool only.
              </p>
            </div>

            <div className="flex items-center gap-3 flex-wrap text-xs">
              <div>
                <label className="text-slate-400 block mb-1">Symbol:</label>
                <input
                  type="text"
                  value={labSymbol}
                  onChange={(e) => setLabSymbol(e.target.value.toUpperCase())}
                  className="w-24 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-bold"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Trigger Price:</label>
                <input
                  type="number"
                  value={labTrigger}
                  onChange={(e) => setLabTrigger(Number(e.target.value))}
                  className="w-24 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Stop Loss:</label>
                <input
                  type="number"
                  value={labStop}
                  onChange={(e) => setLabStop(Number(e.target.value))}
                  className="w-24 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Simulations (M):</label>
                <select
                  value={labSimulations}
                  onChange={(e) => setLabSimulations(Number(e.target.value))}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
                >
                  <option value={1000}>1,000 runs (Fast)</option>
                  <option value={5000}>5,000 runs</option>
                  <option value={10000}>10,000 runs (Spec 12.6 Standard)</option>
                </select>
              </div>
              <div className="self-end pt-5">
                <button
                  onClick={handleRunScenarioLab}
                  disabled={labRunning}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold shadow-md transition-all"
                >
                  <Play className={`w-3.5 h-3.5 ${labRunning ? 'animate-spin' : ''}`} />
                  {labRunning ? 'Simulating...' : 'Run Scenario Lab'}
                </button>
              </div>
            </div>
          </div>

          {labResult && (
            <div className="flex flex-col gap-6">
              {/* Distinct N Observations vs M Simulations Counter Banner */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs text-slate-400 uppercase font-semibold block">Observed Analogues (Point-in-Time)</span>
                    <span className="text-2xl font-bold font-mono text-cyan-400">N = {labResult.observed.sample_size_n}</span>
                    <span className="text-[11px] text-slate-400 block mt-0.5">
                      {labResult.observed.date_range ? `Range: ${labResult.observed.date_range[0]} to ${labResult.observed.date_range[1]}` : 'Zero future leakage enforced'}
                    </span>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${labResult.observed.status === 'OK' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-amber-950 text-amber-300 border-amber-800'}`}>
                    {labResult.observed.status}
                  </span>
                </div>

                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs text-slate-400 uppercase font-semibold block">Bootstrap Monte Carlo</span>
                    <span className="text-2xl font-bold font-mono text-purple-400">M = {labResult.simulated.simulation_runs_m.toLocaleString()}</span>
                    <span className="text-[11px] text-slate-400 block mt-0.5">Block bootstrap (Seed {labResult.simulated.seed_used})</span>
                  </div>
                  <span className="px-2.5 py-1 rounded-full text-xs font-bold border bg-purple-950 text-purple-300 border-purple-800">
                    M &ne; N (Distinct)
                  </span>
                </div>
              </div>

              {/* Observed Analogues Section */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
                <h2 className="text-base font-bold text-white mb-2 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-cyan-400" />
                  Observed Historical Analogues (N={labResult.observed.sample_size_n})
                </h2>
                {labResult.observed.status === 'INSUFFICIENT SAMPLE' ? (
                  <div className="p-3 bg-amber-950/40 border border-amber-800/80 rounded-lg text-xs text-amber-300">
                    <strong>INSUFFICIENT SAMPLE:</strong> {labResult.observed.note || 'Fewer than 10 historical point-in-time analogues found. Outcome percentages are strictly suppressed to avoid misleading inferences.'}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {['5d', '10d', '20d'].map((hKey) => {
                      const h = labResult.observed.horizons[hKey];
                      if (!h) return null;
                      return (
                        <div key={hKey} className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs flex flex-col gap-2">
                          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                            <span className="font-bold text-white text-sm">{h.horizon_sessions} Sessions Horizon</span>
                            <span className="font-mono text-slate-400">Median: {h.median_r !== null && h.median_r !== undefined ? (h.median_r >= 0 ? '+' : '') + h.median_r + 'R' : 'N/A'}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">First-Passage 1R:</span>
                            <span className="font-bold text-emerald-400 font-mono">
                              {h.first_passage_1r_pct}% {h.first_passage_1r_ci ? `[${h.first_passage_1r_ci[0]}%-${h.first_passage_1r_ci[1]}%]` : ''}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">First-Passage 2R:</span>
                            <span className="font-bold text-cyan-400 font-mono">{h.first_passage_2r_pct}%</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Stop Hit First:</span>
                            <span className="font-bold text-rose-400 font-mono">
                              {h.stop_first_pct}% {h.stop_first_ci ? `[${h.stop_first_ci[0]}%-${h.stop_first_ci[1]}%]` : ''}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-slate-400">Neither (Holding):</span>
                            <span className="font-mono text-slate-300">{h.neither_pct}%</span>
                          </div>
                          <div className="flex items-center justify-between pt-1 border-t border-slate-800/60 text-[11px] text-slate-500">
                            <span>MAE: {h.median_mae_r}R</span>
                            <span>MFE: +{h.median_mfe_r}R</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Simulated Bootstrap Section */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
                <h2 className="text-base font-bold text-white mb-2 flex items-center gap-2">
                  <Shuffle className="w-5 h-5 text-purple-400" />
                  Simulated Forward Block Bootstrap (M={labResult.simulated.simulation_runs_m.toLocaleString()} runs)
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {['5d', '10d', '20d'].map((hKey) => {
                    const h = labResult.simulated.horizons[hKey];
                    if (!h) return null;
                    return (
                      <div key={hKey} className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs flex flex-col gap-2">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                          <span className="font-bold text-white text-sm">{h.horizon_sessions} Sessions Horizon</span>
                          <span className="font-mono text-slate-400">Median: {h.median_r !== null && h.median_r !== undefined ? (h.median_r >= 0 ? '+' : '') + h.median_r + 'R' : 'N/A'}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">First-Passage 1R:</span>
                          <span className="font-bold text-emerald-400 font-mono">{h.first_passage_1r_pct}%</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">First-Passage 2R:</span>
                          <span className="font-bold text-cyan-400 font-mono">{h.first_passage_2r_pct}%</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">Stop Hit First:</span>
                          <span className="font-bold text-rose-400 font-mono">{h.stop_first_pct}%</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">Neither (Holding):</span>
                          <span className="font-mono text-slate-300">{h.neither_pct}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Sensitivity Analysis Table */}
              {labResult.sensitivity_table && labResult.sensitivity_table.length > 0 && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
                  <div className="p-4 border-b border-slate-800 flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-indigo-400" />
                    <h3 className="text-sm font-bold text-white">Sensitivity Analysis (Stop & Volatility Variations, 10d Horizon)</h3>
                  </div>
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 uppercase font-bold border-b border-slate-800">
                      <tr>
                        <th className="px-4 py-3">Scenario</th>
                        <th className="px-4 py-3">Effective Stop</th>
                        <th className="px-4 py-3">Stop Hit First %</th>
                        <th className="px-4 py-3">Target 1R %</th>
                        <th className="px-4 py-3">Median Realized R</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {labResult.sensitivity_table.map((row, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/40">
                          <td className="px-4 py-2.5 font-bold text-slate-200 font-sans">{row.scenario}</td>
                          <td className="px-4 py-2.5 text-slate-300">{row.stop_price}</td>
                          <td className="px-4 py-2.5 text-rose-400 font-bold">{row.stop_first_pct}%</td>
                          <td className="px-4 py-2.5 text-emerald-400 font-bold">{row.target_1r_pct}%</td>
                          <td className="px-4 py-2.5 text-slate-200">{row.median_r >= 0 ? '+' : ''}{row.median_r}R</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Strict Limitations Box (Spec 12.6 Invariant d) */}
              <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-400 flex items-start gap-3">
                <Info className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-white block mb-1">Methodology & Limitations Notice (Spec 12.6):</strong>
                  {labResult.limitations_disclaimer}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
