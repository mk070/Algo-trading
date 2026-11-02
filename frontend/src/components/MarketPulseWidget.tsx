import React, { useState } from 'react';
import { ArrowDownRight, ArrowUpRight, ChevronRight, TrendingUp } from 'lucide-react';

interface MarketPulseWidgetProps {
  currentMarket: 'IN' | 'US';
  onOpenChart?: (symbol: string) => void;
  onSelectSymbol?: (symbol: string) => void;
}

export const MarketPulseWidget: React.FC<MarketPulseWidgetProps> = ({
  currentMarket,
  onOpenChart,
  onSelectSymbol,
}) => {
  const [activeLeaderGroup, setActiveLeaderGroup] = useState<string>('group1');
  const handleStockClick = (sym: string) => {
    if (onOpenChart) onOpenChart(sym);
    else if (onSelectSymbol) onSelectSymbol(sym);
  };

  // 4 Core Pulse cards matching OpenStock screenshots
  const pulseCards = currentMarket === 'IN'
    ? [
        {
          name: 'SENSEX',
          ticker: 'BSE:SENSEX',
          price: '75,692.78',
          change: '+1,233.25',
          pct: '+1.66%',
          isPos: true,
          unit: '',
        },
        {
          name: 'RELIANCE',
          ticker: 'RELIANCE',
          price: '1,163.55',
          change: '-5.20',
          pct: '-0.44%',
          isPos: false,
          unit: 'INR',
        },
        {
          name: 'TCS',
          ticker: 'TCS',
          price: '2,496.00',
          change: '+15.50',
          pct: '+0.62%',
          isPos: true,
          unit: 'INR',
        },
        {
          name: 'HDFCBANK',
          ticker: 'HDFCBANK',
          price: '692.30',
          change: '+7.30',
          pct: '+1.07%',
          isPos: true,
          unit: 'INR',
        },
      ]
    : [
        {
          name: 'S&P 500',
          ticker: 'SPY',
          price: '760.11',
          change: '+1.39',
          pct: '+0.58%',
          isPos: true,
          unit: 'USD',
        },
        {
          name: 'Nasdaq 100',
          ticker: 'QQQ',
          price: '693.82',
          change: '+3.33',
          pct: '+0.48%',
          isPos: true,
          unit: 'USD',
        },
        {
          name: 'Dow 30',
          ticker: 'DIA',
          price: '522.34',
          change: '+5.21',
          pct: '+1.01%',
          isPos: true,
          unit: 'USD',
        },
        {
          name: 'Russell 2000',
          ticker: 'IWM',
          price: '282.21',
          change: '+2.88',
          pct: '+1.03%',
          isPos: true,
          unit: 'USD',
        },
      ];

  // Grouped leaders data
  const leaderGroups = currentMarket === 'IN'
    ? [
        { id: 'group1', label: 'Banks' },
        { id: 'group2', label: 'Technology' },
        { id: 'group3', label: 'Industry' },
      ]
    : [
        { id: 'group1', label: 'Financial' },
        { id: 'group2', label: 'Technology' },
        { id: 'group3', label: 'Consumer' },
      ];

  // Sector Quotes Data
  const sectorQuotes = currentMarket === 'IN'
    ? [
        {
          sector: 'BANKS',
          stocks: [
            { name: 'HDFC Bank', symbol: 'HDFCBANK', value: '692.30', change: '+7.30', pct: '+1.07%', open: '684.05', high: '695.50', low: '681.05', prev: '685.00', isPos: true },
            { name: 'ICICI Bank', symbol: 'ICICIBANK', value: '1,394.00', change: '+8.30', pct: '+0.60%', open: '1,390.95', high: '1,404.90', low: '1,383.35', prev: '1,385.70', isPos: true },
            { name: 'State Bank of India', symbol: 'SBIN', value: '961.00', change: '-19.00', pct: '-1.94%', open: '971.50', high: '971.50', low: '959.50', prev: '980.00', isPos: false },
            { name: 'Kotak Mahindra', symbol: 'KOTAKBANK', value: '461.00', change: '+4.00', pct: '+0.88%', open: '459.80', high: '462.80', low: '457.10', prev: '457.00', isPos: true },
            { name: 'Axis Bank', symbol: 'AXISBANK', value: '1,214.70', change: '-11.40', pct: '-0.93%', open: '1,221.25', high: '1,227.70', low: '1,210.00', prev: '1,226.10', isPos: false },
          ],
        },
        {
          sector: 'TECHNOLOGY',
          stocks: [
            { name: 'TCS', symbol: 'TCS', value: '2,496.00', change: '+15.50', pct: '+0.62%', open: '2,484.70', high: '2,527.65', low: '2,484.70', prev: '2,480.50', isPos: true },
            { name: 'Infosys', symbol: 'INFY', value: '1,182.00', change: '+38.55', pct: '+3.37%', open: '1,148.00', high: '1,183.95', low: '1,148.00', prev: '1,143.45', isPos: true },
            { name: 'Wipro', symbol: 'WIPRO', value: '198.00', change: '+7.95', pct: '+4.18%', open: '190.95', high: '198.00', low: '190.85', prev: '190.05', isPos: true },
            { name: 'HCLTech', symbol: 'HCLTECH', value: '1,428.00', change: '+16.50', pct: '+1.17%', open: '1,406.05', high: '1,451.75', low: '1,406.05', prev: '1,411.50', isPos: true },
            { name: 'Tech Mahindra', symbol: 'TECHM', value: '1,792.20', change: '+21.70', pct: '+1.23%', open: '1,771.15', high: '1,813.00', low: '1,771.15', prev: '1,770.50', isPos: true },
          ],
        },
      ]
    : [
        {
          sector: 'TECHNOLOGY',
          stocks: [
            { name: 'Apple Inc', symbol: 'AAPL', value: '232.80', change: '-2.90', pct: '-1.23%', open: '234.00', high: '235.50', low: '231.80', prev: '235.70', isPos: false },
            { name: 'NVIDIA Corp', symbol: 'NVDA', value: '141.50', change: '+4.20', pct: '+3.06%', open: '138.20', high: '142.00', low: '137.90', prev: '137.30', isPos: true },
            { name: 'Microsoft Corp', symbol: 'MSFT', value: '430.20', change: '+2.10', pct: '+0.49%', open: '428.50', high: '431.20', low: '427.00', prev: '428.10', isPos: true },
            { name: 'Broadcom Inc', symbol: 'AVGO', value: '175.40', change: '-10.15', pct: '-5.48%', open: '182.00', high: '183.00', low: '174.50', prev: '185.55', isPos: false },
          ],
        },
        {
          sector: 'FINANCIAL',
          stocks: [
            { name: 'JPMorgan Chase', symbol: 'JPM', value: '228.40', change: '+1.80', pct: '+0.79%', open: '227.00', high: '229.50', low: '226.50', prev: '226.60', isPos: true },
            { name: 'Berkshire Hathaway', symbol: 'BRK.B', value: '462.10', change: '+0.45', pct: '+0.10%', open: '461.50', high: '463.00', low: '460.80', prev: '461.65', isPos: true },
          ],
        },
      ];

  return (
    <div className="space-y-6 select-none">
      {/* Notice Update Banner (OpenStock Style) */}
      <div className="bg-indigo-950/40 border border-indigo-900/60 rounded-xl px-4 py-2.5 flex items-center justify-between text-xs text-indigo-300">
        <div className="flex items-center gap-2">
          <span className="bg-indigo-500 text-slate-950 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase">
            New
          </span>
          <span>
            Institutional Terminal v2.4: Interactive TradingView charts, multi-timeframe indicators, and manual order tickets.
          </span>
        </div>
        <span className="text-indigo-400 font-semibold hover:underline cursor-pointer flex items-center gap-1">
          Trading Rules <ChevronRight className="w-3.5 h-3.5" />
        </span>
      </div>

      {/* Markets Header */}
      <div>
        <h1 className="text-2xl font-black text-slate-100 tracking-tight">Markets</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          {currentMarket === 'IN'
            ? 'India · NSE / BSE · live quotes via Angel One SmartAPI'
            : 'United States · open now · live quotes via Finnhub'}
        </p>
      </div>

      {/* Pulse Section: 4 High-Impact Index Cards */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div>
            <span className="font-bold text-slate-200">Pulse</span>
            <span className="text-slate-500 ml-2">
              {currentMarket === 'IN' ? 'End of day / live quotes via SmartAPI' : 'Shared quotes via Finnhub'}
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">
            Delayed · refreshed in real-time
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {pulseCards.map((card) => (
            <div
              key={card.name}
              onClick={() => handleStockClick(card.ticker)}
              className="bg-slate-900 hover:bg-slate-800/80 border border-slate-800 hover:border-slate-700 rounded-xl p-4 transition cursor-pointer group shadow-sm"
            >
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
                <span className="font-bold text-slate-200 group-hover:text-indigo-400 transition-colors">
                  {card.name}
                </span>
                <span className="text-[10px] font-mono text-slate-500">{card.ticker}</span>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <div className="font-mono text-xl font-bold text-slate-100 tabular-nums">
                  {currentMarket === 'IN' && !card.price.startsWith('₹') ? '₹' : ''}
                  {currentMarket === 'US' && !card.price.startsWith('$') ? '$' : ''}
                  {card.price}
                </div>
                <div
                  className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-mono font-bold ${
                    card.isPos
                      ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800'
                      : 'bg-rose-950/80 text-rose-400 border border-rose-800'
                  }`}
                >
                  {card.isPos ? (
                    <ArrowUpRight className="w-3 h-3" />
                  ) : (
                    <ArrowDownRight className="w-3 h-3" />
                  )}
                  {card.pct}
                </div>
              </div>
              <div className="text-[10px] text-slate-500 font-mono mt-1">
                {card.change} vs prev close
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Leaders & Sparkline + Grouped Quotes Split View */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Leaders 12-month Trend & Sparkline */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-bold text-sm text-slate-200">Leaders</h3>
                <p className="text-[11px] text-slate-400">12-month trend by group</p>
              </div>
            </div>

            {/* Group Tabs */}
            <div className="flex items-center gap-2 border-b border-slate-800 pb-2 mb-3">
              {leaderGroups.map((g) => (
                <button
                  key={g.id}
                  onClick={() => setActiveLeaderGroup(g.id)}
                  className={`text-xs font-semibold px-2 py-1 rounded-md transition ${
                    activeLeaderGroup === g.id
                      ? 'bg-slate-800 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>

            {/* Simulated 12-month area sparkline curve */}
            <div className="h-32 w-full my-2 relative">
              <svg className="w-full h-full overflow-visible" viewBox="0 0 300 100" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
                    <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                  </linearGradient>
                </defs>
                <path
                  d="M0,75 Q40,60 80,70 T160,40 T240,25 T300,15 L300,100 L0,100 Z"
                  fill="url(#sparkGrad)"
                />
                <path
                  d="M0,75 Q40,60 80,70 T160,40 T240,25 T300,15"
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2"
                />
              </svg>
            </div>
            <div className="flex justify-between text-[10px] text-slate-400 font-mono px-1">
              <span>Nov</span>
              <span>Mar</span>
              <span>Jul</span>
              <span>Sep</span>
              <span>Now</span>
            </div>
          </div>

          <div className="pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between">
            <span>Relative Strength: <strong className="text-emerald-400 font-mono">88%ile</strong></span>
            <span className="font-mono text-slate-400">12M Trend: +24.6%</span>
          </div>
        </div>

        {/* Right Column (2 cols): Grouped Quotes Table */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-slate-200">Quotes</h3>
              <p className="text-[11px] text-slate-400">
                {currentMarket === 'IN' ? 'India leaders by group' : 'US leaders by group'}
              </p>
            </div>
            <span className="text-[10px] font-mono text-slate-400">Real-time / End of Day</span>
          </div>

          <div className="overflow-x-auto scrollbar-none">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 text-[10px] font-bold uppercase tracking-wider">
                  <th className="px-4 py-2">Name</th>
                  <th className="px-4 py-2">Value</th>
                  <th className="px-4 py-2">Change</th>
                  <th className="px-4 py-2">Chg%</th>
                  <th className="px-4 py-2 hidden sm:table-cell">Open</th>
                  <th className="px-4 py-2 hidden sm:table-cell">High</th>
                  <th className="px-4 py-2 hidden sm:table-cell">Low</th>
                  <th className="px-4 py-2 hidden md:table-cell">Prev</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {sectorQuotes.map((sec) => (
                  <React.Fragment key={sec.sector}>
                    <tr className="bg-slate-950/40">
                      <td
                        colSpan={8}
                        className="px-4 py-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider"
                      >
                        {sec.sector}
                      </td>
                    </tr>
                    {sec.stocks.map((stock) => (
                      <tr
                        key={stock.symbol}
                        onClick={() => handleStockClick(stock.symbol)}
                        className="hover:bg-slate-800/50 cursor-pointer transition"
                      >
                        <td className="px-4 py-2.5">
                          <span className="font-bold text-slate-200 block leading-tight">
                            {stock.name}
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono">
                            {stock.symbol}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-mono font-bold text-slate-100 tabular-nums">
                          {stock.value}
                        </td>
                        <td
                          className={`px-4 py-2.5 font-mono tabular-nums ${
                            stock.isPos ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {stock.change}
                        </td>
                        <td
                          className={`px-4 py-2.5 font-mono font-bold tabular-nums ${
                            stock.isPos ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {stock.pct}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-slate-400 hidden sm:table-cell tabular-nums">
                          {stock.open}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-slate-400 hidden sm:table-cell tabular-nums">
                          {stock.high}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-slate-400 hidden sm:table-cell tabular-nums">
                          {stock.low}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-slate-400 hidden md:table-cell tabular-nums">
                          {stock.prev}
                        </td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
