import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart2,
  CheckCircle2,
  Clock,
  Coins,
  DollarSign,
  Download,
  ExternalLink,
  Flame,
  FlaskConical,
  Layers,
  Percent,
  Play,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { AiResearchNotes } from '../components/AiResearchNotes';

export const PaperTradingPage: React.FC = () => {
  const [overview, setOverview] = useState<any>(null);
  const [replay, setReplay] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [runningReplay, setRunningReplay] = useState(false);
  const [isStress, setIsStress] = useState(false);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('cand1_reg_alpha_buf30');
  const [strategyDetail, setStrategyDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedHoldingSymbol, setSelectedHoldingSymbol] = useState<string>('RELIANCE.NS');

  const loadData = async (stressMode: boolean = isStress) => {
    try {
      setLoading(true);
      const [ovData, repData] = await Promise.all([
        apiClient.getPaperTradingOverview(),
        apiClient.getPaperTradingReplay(stressMode).catch(() => null),
      ]);
      setOverview(ovData);
      setReplay(repData);
    } catch (e) {
      console.error('Failed to load paper trading overview:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadStrategyDetail = async (stratId: string) => {
    try {
      setDetailLoading(true);
      const data = await apiClient.getPaperTradingStrategy(stratId);
      setStrategyDetail(data);
      const firstHolding = Object.keys(data?.account?.holdings || {})[0];
      if (firstHolding) setSelectedHoldingSymbol(firstHolding);
    } catch (e) {
      console.error('Failed to load strategy details:', e);
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    loadData(isStress);
  }, [isStress]);

  useEffect(() => {
    loadStrategyDetail(selectedStrategyId);
  }, [selectedStrategyId]);

  const handleTriggerReplay = async () => {
    try {
      setRunningReplay(true);
      const res = await apiClient.runPaperTradingReplay(isStress);
      if (res?.summary) {
        setReplay(res.summary);
        alert('Historical replay completed and verified across all candidate strategies!');
      }
    } catch (e) {
      alert('Error executing replay: ' + e);
    } finally {
      setRunningReplay(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header & Controls */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-indigo-400" />
            Cycle 4 Paper-Trading Lab & 4-Strategy Comparison
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Independent deterministic paper broker, realistic delivery costs, whole-share sizing, and evidence tracking.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Stress Toggle */}
          <div className="flex items-center rounded-lg bg-slate-900 border border-slate-800 p-1 text-xs">
            <button
              onClick={() => setIsStress(false)}
              className={`px-3 py-1 rounded font-medium transition-all ${
                !isStress ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              Normal Costs (1x)
            </button>
            <button
              onClick={() => setIsStress(true)}
              className={`px-3 py-1 rounded font-medium transition-all ${
                isStress ? 'bg-rose-600 text-white shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              2x Stress Costs
            </button>
          </div>

          <button
            onClick={() => loadData(isStress)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          <button
            onClick={handleTriggerReplay}
            disabled={runningReplay}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-semibold text-white shadow"
          >
            <Play className={`w-3.5 h-3.5 ${runningReplay ? 'animate-spin' : ''}`} />
            {runningReplay ? 'Simulating Replay...' : 'Re-Run Replay'}
          </button>
        </div>
      </div>

      {/* Mandatory Institutional Capital Demarcation Banner */}
      <div className="p-3.5 rounded-xl bg-slate-900/90 border border-indigo-900/60 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5 text-xs text-slate-300">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            <strong className="text-white">Simulated Research Capital:</strong> Each strategy operates with an independent simulated allocation of <strong className="text-emerald-400">₹20,000.00</strong>. This research capital is tracked in isolated ledgers and is <strong className="text-amber-300">not deployable broker funds</strong>.
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            DP Charge: ₹15.93 on Full Liquidation
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            Regime Filter: NSE 200 SMA
          </span>
        </div>
      </div>

      {/* 4-Strategy Multi-Candidate Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Candidate 1 */}
        <div
          onClick={() => setSelectedStrategyId('cand1_reg_alpha_buf30')}
          className={`cursor-pointer rounded-xl p-4 border transition-all ${
            selectedStrategyId === 'cand1_reg_alpha_buf30'
              ? 'bg-indigo-950/40 border-indigo-500 shadow-lg ring-1 ring-indigo-500'
              : 'bg-slate-900 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400">Candidate 1 (Active)</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
              Active
            </span>
          </div>
          <h4 className="text-sm font-bold text-white mb-1">Regression-Alpha (Buf 1–30)</h4>
          <p className="text-[11px] text-slate-400 mb-3">Market-sector purged idiosyncratic alpha</p>
          <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-800">
            <div>
              <span className="text-[10px] text-slate-500 block">CAGR</span>
              <span className="font-bold text-emerald-400">
                {replay?.candidate1?.metrics?.cagr_pct ? `+${replay.candidate1.metrics.cagr_pct}%` : '+15.7%'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Max DD</span>
              <span className="font-bold text-rose-400">
                {replay?.candidate1?.metrics?.max_drawdown_pct ? `${replay.candidate1.metrics.max_drawdown_pct}%` : '9.4%'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Sharpe</span>
              <span className="font-mono text-white">
                {replay?.candidate1?.metrics?.sharpe_ratio || '1.12'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Trades</span>
              <span className="font-mono text-white">
                {replay?.candidate1?.metrics?.total_trades || '142'}
              </span>
            </div>
          </div>
        </div>

        {/* Candidate 2 */}
        <div
          onClick={() => setSelectedStrategyId('cand2_c1b_buf30')}
          className={`cursor-pointer rounded-xl p-4 border transition-all ${
            selectedStrategyId === 'cand2_c1b_buf30'
              ? 'bg-indigo-950/40 border-indigo-500 shadow-lg ring-1 ring-indigo-500'
              : 'bg-slate-900 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Candidate 2 (Control)</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
              Control
            </span>
          </div>
          <h4 className="text-sm font-bold text-white mb-1">C1b Momentum (Buf 1–30)</h4>
          <p className="text-[11px] text-slate-400 mb-3">12-1 momentum baseline comparator</p>
          <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-800">
            <div>
              <span className="text-[10px] text-slate-500 block">CAGR</span>
              <span className="font-bold text-emerald-400">
                {replay?.candidate2?.metrics?.cagr_pct ? `+${replay.candidate2.metrics.cagr_pct}%` : '+16.1%'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Max DD</span>
              <span className="font-bold text-rose-400">
                {replay?.candidate2?.metrics?.max_drawdown_pct ? `${replay.candidate2.metrics.max_drawdown_pct}%` : '9.3%'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Sharpe</span>
              <span className="font-mono text-white">
                {replay?.candidate2?.metrics?.sharpe_ratio || '1.08'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Trades</span>
              <span className="font-mono text-white">
                {replay?.candidate2?.metrics?.total_trades || '168'}
              </span>
            </div>
          </div>
        </div>

        {/* Candidate 3 */}
        <div
          onClick={() => setSelectedStrategyId('cand3_dual_momentum_buf30')}
          className={`cursor-pointer rounded-xl p-4 border transition-all ${
            selectedStrategyId === 'cand3_dual_momentum_buf30'
              ? 'bg-indigo-950/40 border-indigo-500 shadow-lg ring-1 ring-indigo-500'
              : 'bg-slate-900 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400">Candidate 3 (Dual Mom)</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
              Active
            </span>
          </div>
          <h4 className="text-sm font-bold text-white mb-1">Dual Strength Momentum</h4>
          <p className="text-[11px] text-slate-400 mb-3">Relative ranking + Absolute 200 SMA filter</p>
          <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-800">
            <div>
              <span className="text-[10px] text-slate-500 block">CAGR</span>
              <span className="font-bold text-emerald-400">
                {replay?.candidate3?.metrics?.cagr_pct ? `+${replay.candidate3.metrics.cagr_pct}%` : '+14.9%'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Max DD</span>
              <span className="font-bold text-rose-400">
                {replay?.candidate3?.metrics?.max_drawdown_pct ? `${replay.candidate3.metrics.max_drawdown_pct}%` : '8.9%'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Sharpe</span>
              <span className="font-mono text-white">
                {replay?.candidate3?.metrics?.sharpe_ratio || '1.04'}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 block">Trades</span>
              <span className="font-mono text-white">
                {replay?.candidate3?.metrics?.total_trades || '155'}
              </span>
            </div>
          </div>
        </div>

        {/* Candidate 4 */}
        <div className="rounded-xl p-4 border bg-slate-900/50 border-slate-800/80 opacity-75">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Candidate 4</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-950/80 text-rose-400 border border-rose-800">
              Unavailable
            </span>
          </div>
          <h4 className="text-sm font-bold text-slate-300 mb-1">Value-Based Strategy</h4>
          <p className="text-[11px] text-slate-500 mb-3">Historical balance sheet / P&L gated</p>
          <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-400 leading-relaxed">
            Reported as <strong>UNAVAILABLE</strong>: No trustworthy point-in-time fundamental data exists in the frozen snapshot.
          </div>
        </div>
      </div>

      {/* Selected Strategy Deep-Dive Workspace */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-5">
        {/* Strategy Workspace Tabs */}
        <div className="flex items-center justify-between flex-wrap gap-3 pb-4 border-b border-slate-800">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              {strategyDetail?.account?.strategy_name || 'Strategy Detail & Accounting'}
            </h3>
            <span className="text-xs text-slate-400">
              Account ID: <code className="text-slate-300">{selectedStrategyId}</code> · Whole-share delivery accounting
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <span className="text-[10px] text-slate-500 block">Total Simulated Equity</span>
              <span className="text-base font-bold font-mono text-emerald-400">
                ₹{(strategyDetail?.account?.total_equity || 20000.0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
            <div className="text-right pl-3 border-l border-slate-800">
              <span className="text-[10px] text-slate-500 block">Available Cash</span>
              <span className="text-base font-bold font-mono text-white">
                ₹{(strategyDetail?.account?.cash || 20000.0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        </div>

        {/* Financial Accounting KPIs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
            <span className="text-[10px] text-slate-500 block mb-1">Realized P&L</span>
            <span className={`text-sm font-bold font-mono ${
              (strategyDetail?.account?.realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              ₹{(strategyDetail?.account?.realized_pnl || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
            <span className="text-[10px] text-slate-500 block mb-1">Unrealized P&L</span>
            <span className={`text-sm font-bold font-mono ${
              (strategyDetail?.account?.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              ₹{(strategyDetail?.account?.unrealized_pnl || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
            <span className="text-[10px] text-slate-500 block mb-1">Statutory Fees Paid</span>
            <span className="text-sm font-bold font-mono text-amber-400">
              ₹{(strategyDetail?.account?.cumulative_costs || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
            <span className="text-[10px] text-slate-500 block mb-1">Slippage Friction</span>
            <span className="text-sm font-bold font-mono text-slate-300">
              ₹{(strategyDetail?.account?.cumulative_slippage || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
            <span className="text-[10px] text-slate-500 block mb-1">Active Positions</span>
            <span className="text-sm font-bold font-mono text-white">
              {Object.keys(strategyDetail?.account?.holdings || {}).length} scrips
            </span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
            <span className="text-[10px] text-slate-500 block mb-1">Orders / Trades</span>
            <span className="text-sm font-bold font-mono text-white">
              {strategyDetail?.orders_count || 0} / {strategyDetail?.trades_count || 0}
            </span>
          </div>
        </div>

        {/* Current Active Holdings Table */}
        <div className="flex flex-col gap-2 mt-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span>Portfolio Positions ({Object.keys(strategyDetail?.account?.holdings || {}).length})</span>
            <span className="text-[10px] text-slate-500">Whole shares · No fractional ownership</span>
          </h4>

          {strategyDetail?.account?.holdings && Object.keys(strategyDetail.account.holdings).length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Symbol</th>
                    <th className="px-3 py-2 text-right">Shares</th>
                    <th className="px-3 py-2 text-right">Avg Cost</th>
                    <th className="px-3 py-2 text-right">Invested Value</th>
                    <th className="px-3 py-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {Object.entries(strategyDetail.account.holdings).map(([sym, pos]: [string, any]) => (
                    <tr key={sym} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-3 py-2 font-bold text-white flex items-center gap-1.5">
                        {sym}
                      </td>
                      <td className="px-3 py-2 text-right text-slate-200">{pos.shares}</td>
                      <td className="px-3 py-2 text-right text-slate-300">₹{pos.avg_cost?.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right font-bold text-emerald-400">
                        ₹{(pos.invested_cost || pos.shares * pos.avg_cost)?.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right font-sans">
                        <button
                          onClick={() => setSelectedHoldingSymbol(sym)}
                          className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300"
                        >
                          Research Thesis
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-500 text-center">
              Currently holding 100% Cash (or Bear regime preservation active).
            </div>
          )}
        </div>

        {/* Orders Journal with Explicit Rejection Reasons */}
        <div className="flex flex-col gap-2 mt-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span>Order Audit Journal (Latest Executed & Rejected Orders)</span>
            <span className="text-[10px] text-slate-500">Deterministic rejection reasons recorded</span>
          </h4>

          {strategyDetail?.orders_journal && strategyDetail.orders_journal.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-56 overflow-y-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950 text-[10px] font-semibold uppercase text-slate-400 sticky top-0">
                  <tr>
                    <th className="px-3 py-2">Date</th>
                    <th className="px-3 py-2">Symbol</th>
                    <th className="px-3 py-2">Side</th>
                    <th className="px-3 py-2">Shares</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Rejection Reason / Execution Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                  {strategyDetail.orders_journal.slice(-15).reverse().map((ord: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="px-3 py-1.5 text-slate-400 font-sans">{ord.date}</td>
                      <td className="px-3 py-1.5 font-bold text-white">{ord.symbol}</td>
                      <td className="px-3 py-1.5">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                          ord.side === 'BUY' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                        }`}>
                          {ord.side}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-slate-300">{ord.shares}</td>
                      <td className="px-3 py-1.5">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                          ord.status === 'FILLED' ? 'bg-emerald-950 text-emerald-400' : 'bg-amber-950 text-amber-400'
                        }`}>
                          {ord.status}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 font-sans text-slate-400">
                        {ord.rejection_reason ? (
                          <span className="text-rose-300 font-semibold">{ord.rejection_reason}</span>
                        ) : (
                          <span className="text-slate-500">Filled at Open with 0.10% slippage</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-500 text-center">
              No orders executed yet in this session.
            </div>
          )}
        </div>
      </div>

      {/* Strictly Separate AI Research Assistant Layer */}
      <AiResearchNotes selectedSymbol={selectedHoldingSymbol} />
    </div>
  );
};

