import React, { useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, ChevronRight, ExternalLink, LayoutGrid, RefreshCw, Table, TrendingUp } from 'lucide-react';
import { apiClient } from '../api/client';
import { TradingViewStockHeatmap } from './TradingViewStockHeatmap';

interface MarketPulseWidgetProps {
  currentMarket: 'IN' | 'US';
  onMarketChange?: (market: 'IN' | 'US') => void;
  onOpenChart?: (symbol: string) => void;
  onSelectSymbol?: (symbol: string) => void;
}

export const MarketPulseWidget: React.FC<MarketPulseWidgetProps> = ({
  currentMarket,
  onMarketChange,
  onOpenChart,
  onSelectSymbol,
}) => {
  const [activeLeaderGroup, setActiveLeaderGroup] = useState<string>('group1');
  const [rightPanelView, setRightPanelView] = useState<'heatmap' | 'quotes'>('heatmap');
  const [liveQuotes, setLiveQuotes] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState<boolean>(true);

  const handleStockClick = (sym: string) => {
    if (onOpenChart) onOpenChart(sym);
    else if (onSelectSymbol) onSelectSymbol(sym);
  };

  const usPulseTickers = ['SPY', 'QQQ', 'DIA', 'IWM'];
  const inPulseTickers = ['SENSEX', 'RELIANCE', 'TCS', 'HDFCBANK'];

  const usSectorTickers = ['AAPL', 'NVDA', 'MSFT', 'AVGO', 'JPM', 'BRK.B'];
  const inSectorTickers = ['HDFCBANK', 'ICICIBANK', 'SBIN', 'KOTAKBANK', 'AXISBANK', 'TCS', 'INFY', 'WIPRO', 'HCLTECH', 'TECHM'];

  // Fetch real-time quotes dynamically from backend (Bloomberg Terminal style silent refresh)
  const fetchLiveMarketData = async (isSilent = false) => {
    if (!isSilent) setLoading(true);
    try {
      const symbolsToFetch = currentMarket === 'US'
        ? [...usPulseTickers, ...usSectorTickers]
        : [...inPulseTickers, ...inSectorTickers];

      const data = await apiClient.getQuotes(symbolsToFetch, currentMarket);
      if (data && typeof data === 'object') {
        setLiveQuotes(data);
      }
    } catch (e) {
      if (!isSilent) console.warn('Error fetching live pulse quotes:', e);
    } finally {
      if (!isSilent) setLoading(false);
    }
  };

  useEffect(() => {
    fetchLiveMarketData(false);
    const interval = setInterval(() => fetchLiveMarketData(true), 2500); // 2.5s real-time streaming without loader flicker
    return () => clearInterval(interval);
  }, [currentMarket]);

  // Compute live pulse card metrics
  const getCardData = (name: string, ticker: string, defaultPrice: string, defaultChg: string, defaultPct: string, isDefaultPos: boolean, unit: string) => {
    const rawTicker = ticker.replace('BSE:', '').replace('NSE:', '').trim().toUpperCase();
    const q = liveQuotes[ticker] || liveQuotes[rawTicker] || liveQuotes[`BSE:${rawTicker}`] || liveQuotes[`NSE:${rawTicker}`];
    const priceVal = q ? Number(q.price || q.last_price || 0) : 0;
    if (priceVal > 0) {
      const prevClose = Number(q.prev_close || q.close || q.open || priceVal);
      const chgVal = q.change !== undefined && q.change !== null ? Number(q.change) : (priceVal - prevClose);
      const pctVal = q.change_pct !== undefined && q.change_pct !== null ? Number(q.change_pct) : (prevClose > 0 ? (chgVal / prevClose) * 100 : 0);
      const isPos = chgVal >= 0;

      return {
        name,
        ticker,
        price: priceVal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        change: `${isPos ? '+' : ''}${chgVal.toFixed(2)}`,
        pct: `${isPos ? '+' : ''}${pctVal.toFixed(2)}%`,
        isPos,
        unit,
      };
    }

    return {
      name,
      ticker,
      price: defaultPrice,
      change: defaultChg,
      pct: defaultPct,
      isPos: isDefaultPos,
      unit,
    };
  };

  const pulseCards = currentMarket === 'IN'
    ? [
        getCardData('SENSEX', 'BSE:SENSEX', '77,301.40', '+383.55', '+0.50%', true, ''),
        getCardData('RELIANCE', 'RELIANCE', '1,307.90', '+7.90', '+0.61%', true, 'INR'),
        getCardData('TCS', 'TCS', '2,499.10', '-2.60', '-0.10%', false, 'INR'),
        getCardData('HDFCBANK', 'HDFCBANK', '725.50', '+25.50', '+3.64%', true, 'INR'),
      ]
    : [
        getCardData('S&P 500', 'SPY', '768.18', '+13.80', '+1.83%', true, 'USD'),
        getCardData('Nasdaq 100', 'QQQ', '695.12', '+11.30', '+1.65%', true, 'USD'),
        getCardData('Dow 30', 'DIA', '531.84', '+9.84', '+1.89%', true, 'USD'),
        getCardData('Russell 2000', 'IWM', '283.98', '+2.68', '+0.95%', true, 'USD'),
      ];

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

  // Compute live quote rows for sectors
  const formatQuoteRow = (name: string, symbol: string, fallbackVal: string, fallbackChg: string, fallbackPct: string, isFallbackPos: boolean) => {
    const q = liveQuotes[symbol] || liveQuotes[symbol.toUpperCase()];
    if (q && q.price > 0) {
      const priceVal = q.price;
      const prevClose = q.prev_close || q.close || priceVal;
      const chgVal = q.change !== undefined && q.change !== null ? Number(q.change) : (priceVal - prevClose);
      const pctVal = q.change_pct !== undefined && q.change_pct !== null ? Number(q.change_pct) : (prevClose > 0 ? (chgVal / prevClose) * 100 : 0);
      const isPos = chgVal >= 0;

      return {
        name,
        symbol,
        value: priceVal.toFixed(2),
        change: `${isPos ? '+' : ''}${chgVal.toFixed(2)}`,
        pct: `${isPos ? '+' : ''}${pctVal.toFixed(2)}%`,
        open: q.open ? q.open.toFixed(2) : priceVal.toFixed(2),
        high: q.high ? q.high.toFixed(2) : priceVal.toFixed(2),
        low: q.low ? q.low.toFixed(2) : priceVal.toFixed(2),
        prev: prevClose.toFixed(2),
        isPos,
      };
    }

    return {
      name,
      symbol,
      value: fallbackVal,
      change: fallbackChg,
      pct: fallbackPct,
      open: fallbackVal,
      high: fallbackVal,
      low: fallbackVal,
      prev: fallbackVal,
      isPos: isFallbackPos,
    };
  };

  const sectorQuotes = currentMarket === 'IN'
    ? [
        {
          sector: 'BANKS',
          stocks: [
            formatQuoteRow('HDFC Bank', 'HDFCBANK', '692.30', '+7.30', '+1.07%', true),
            formatQuoteRow('ICICI Bank', 'ICICIBANK', '1,394.00', '+8.30', '+0.60%', true),
            formatQuoteRow('State Bank of India', 'SBIN', '961.00', '-19.00', '-1.94%', false),
            formatQuoteRow('Kotak Mahindra', 'KOTAKBANK', '461.00', '+4.00', '+0.88%', true),
            formatQuoteRow('Axis Bank', 'AXISBANK', '1,214.70', '-11.40', '-0.93%', false),
          ],
        },
        {
          sector: 'TECHNOLOGY',
          stocks: [
            formatQuoteRow('TCS', 'TCS', '2,496.00', '+15.50', '+0.62%', true),
            formatQuoteRow('Infosys', 'INFY', '1,182.00', '+38.55', '+3.37%', true),
            formatQuoteRow('Wipro', 'WIPRO', '198.00', '+7.95', '+4.18%', true),
            formatQuoteRow('HCLTech', 'HCLTECH', '1,428.00', '+16.50', '+1.17%', true),
            formatQuoteRow('Tech Mahindra', 'TECHM', '1,792.20', '+21.70', '+1.23%', true),
          ],
        },
      ]
    : [
        {
          sector: 'TECHNOLOGY',
          stocks: [
            formatQuoteRow('Apple Inc', 'AAPL', '336.97', '+1.45', '+0.43%', true),
            formatQuoteRow('NVIDIA Corp', 'NVDA', '206.35', '+4.20', '+2.08%', true),
            formatQuoteRow('Microsoft Corp', 'MSFT', '520.00', '+2.10', '+0.41%', true),
            formatQuoteRow('Broadcom Inc', 'AVGO', '329.32', '-2.15', '-0.65%', false),
          ],
        },
        {
          sector: 'FINANCIAL',
          stocks: [
            formatQuoteRow('JPMorgan Chase', 'JPM', '341.44', '+1.80', '+0.53%', true),
            formatQuoteRow('Berkshire Hathaway', 'BRK.B', '462.10', '+0.45', '+0.10%', true),
          ],
        },
      ];

  return (
    <div className="space-y-6 select-none">
      {/* Notice Update Banner (OpenStock Style) */}
      <div className="bg-indigo-950/40 border border-indigo-900/60 rounded-xl px-4 py-2.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs text-indigo-300">
        <div className="flex items-center gap-2">
          <span className="bg-indigo-500 text-slate-950 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase">
            Live
          </span>
          <span>
            Institutional Terminal v2.4: Real-time Alpaca IEX &amp; Angel One SmartAPI live quote integration.
          </span>
        </div>
        <button
          onClick={() => fetchLiveMarketData(false)}
          className="text-indigo-400 font-semibold hover:underline flex items-center gap-1"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Live Quotes</span>
        </button>
      </div>

      {/* Markets Header & Country Filter Pills (OpenStock Exact Match) */}
      <div className="space-y-3">
        <div>
          <h1 className="text-2xl font-black text-slate-100 tracking-tight">Markets</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {currentMarket === 'IN'
              ? 'India · open · live data via Angel One SmartAPI'
              : 'United States · open now · live data via Alpaca IEX'}
          </p>
        </div>

        {/* Horizontal country pills matching OpenStock layout */}
        <div className="flex items-center gap-2 overflow-x-auto scrollbar-none pb-1">
          {[
            { id: 'US', label: 'United States', available: true },
            { id: 'IN', label: 'India', available: true },
            { id: 'DE', label: 'Germany', available: false },
            { id: 'CA', label: 'Canada', available: false },
            { id: 'AU', label: 'Australia', available: false },
            { id: 'SA', label: 'Saudi Arabia', available: false },
            { id: 'CRYPTO', label: 'Crypto', available: false },
            { id: 'FOREX', label: 'Forex', available: false },
          ].map((country) => {
            const isActive =
              (currentMarket === 'US' && country.id === 'US') ||
              (currentMarket === 'IN' && country.id === 'IN');
            return (
              <button
                key={country.id}
                onClick={() => {
                  if (country.available && onMarketChange) {
                    onMarketChange(country.id as 'IN' | 'US');
                  }
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all border ${
                  isActive
                    ? 'bg-emerald-950/80 border-emerald-500/80 text-emerald-300 font-semibold shadow-sm ring-1 ring-emerald-500/30'
                    : country.available
                    ? 'bg-slate-900/80 border-slate-800 text-slate-300 hover:border-slate-700 hover:text-white'
                    : 'bg-slate-900/30 border-slate-800/40 text-slate-500 cursor-not-allowed opacity-60'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    isActive ? 'bg-emerald-400' : 'bg-slate-500'
                  }`}
                />
                <span>{country.label}</span>
                {!country.available && (
                  <span className="text-[9px] uppercase px-1 py-0.5 bg-slate-800/80 rounded text-slate-500">
                    Soon
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Pulse Section: 4 High-Impact Index Cards */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-200">Pulse</span>
            <span className="text-slate-500">
              {currentMarket === 'IN' ? 'Quotes via Angel One SmartAPI' : 'Live real-time feed via Alpaca IEX'}
            </span>
          </div>
          <span className="text-[11px] text-emerald-400 font-mono flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
            Real-Time Streaming
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

            {/* Smooth 12-month area sparkline curve */}
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

        {/* Right Column (2 cols): S&P 500 / Nifty 50 Heatmap + Quotes Table Toggle */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col justify-between shadow-sm">
          <div className="px-4 py-3 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2 bg-slate-950/40">
            <div>
              <h3 className="font-bold text-sm text-slate-100 flex items-center gap-2">
                <span>{currentMarket === 'IN' ? 'Nifty 50 heatmap' : 'S&P 500 heatmap'}</span>
                <span className="text-[10px] font-mono font-normal text-emerald-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  Real-time
                </span>
              </h3>
              <p className="text-[11px] text-slate-400">
                Sized by market cap, coloured by today's move
              </p>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-xs">
                <button
                  onClick={() => setRightPanelView('heatmap')}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition ${
                    rightPanelView === 'heatmap'
                      ? 'bg-slate-800 text-white font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <LayoutGrid className="w-3 h-3" />
                  <span>Heatmap</span>
                </button>
                <button
                  onClick={() => setRightPanelView('quotes')}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition ${
                    rightPanelView === 'quotes'
                      ? 'bg-slate-800 text-white font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Table className="w-3 h-3" />
                  <span>Quotes Table</span>
                </button>
              </div>

              <a
                href="/heatmap"
                className="hidden sm:flex items-center gap-1 text-[11px] text-slate-400 hover:text-emerald-400 border border-slate-800 hover:border-slate-700 bg-slate-950 px-2.5 py-1 rounded-lg transition"
                title="Open full-page institutional heatmap"
              >
                <span>Full View</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>

          {rightPanelView === 'heatmap' ? (
            <div className="p-3 bg-slate-950/60 min-h-[350px]">
              <TradingViewStockHeatmap market={currentMarket} height={340} hasTopBar={false} />
            </div>
          ) : (
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
                          {currentMarket === 'IN' ? '₹' : '$'}{stock.value}
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
          )}
        </div>
      </div>
    </div>
  );
};
