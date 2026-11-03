import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
  LineStyle,
  IChartApi,
  ISeriesApi,
  Time,
  SeriesMarker,
} from 'lightweight-charts';
import {
  BarChart3,
  TrendingUp,
  RefreshCw,
  AlertCircle,
  Eye,
  EyeOff,
  Trash2,
  Crosshair,
  Minus,
  Square,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  Zap,
  Activity,
  Maximize2,
  Layers,
  Target,
} from 'lucide-react';
import { apiClient, CandleBar, StrategyOverlay, BarsResponse } from '../api/client';
import { TradingViewRealtimeChart } from './TradingViewRealtimeChart';

export interface CandleChartProps {
  symbol: string;
  market?: 'IN' | 'US';
  initialTimeframe?: '1D' | '15m';
  bars?: CandleBar[];
  trigger?: number;
  stop?: number;
  target?: number;
  strategyOverlay?: StrategyOverlay | null;
  onClose?: () => void;
  fullHeight?: boolean;
}

interface ChartPreferences {
  showEma20: boolean;
  showEma50: boolean;
  showSma50: boolean;
  showSma150: boolean;
  showSma200: boolean;
  showVolume: boolean;
  showRsi: boolean;
  showAtr: boolean;
  showEntryTrigger: boolean;
  showStopLoss: boolean;
  showTarget1: boolean;
  showTarget2: boolean;
  showVcpBase: boolean;
}

const DEFAULT_PREFS: ChartPreferences = {
  showEma20: true,
  showEma50: true,
  showSma50: true,
  showSma150: false,
  showSma200: true,
  showVolume: true,
  showRsi: true,
  showAtr: false,
  showEntryTrigger: true,
  showStopLoss: true,
  showTarget1: true,
  showTarget2: true,
  showVcpBase: true,
};

const PREFS_KEY = 'algo_trading_chart_prefs_v2';

interface DrawingPoint {
  time: Time;
  price: number;
}

interface ChartDrawing {
  id: string;
  type: 'hline' | 'trendline' | 'rect';
  price?: number;
  p1?: DrawingPoint;
  p2?: DrawingPoint;
  color: string;
}

interface RenderedDrawing extends ChartDrawing {
  yCoord?: number | null;
  x1?: number | null;
  y1?: number | null;
  x2?: number | null;
  y2?: number | null;
}

export const CandleChart: React.FC<CandleChartProps> = ({
  symbol,
  market = 'IN',
  initialTimeframe = '1D',
  bars: initialBars,
  trigger: propTrigger,
  stop: propStop,
  target: propTarget,
  strategyOverlay: propStrategyOverlay,
  onClose,
  fullHeight = false,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  // Timeframe state
  const [timeframe, setTimeframe] = useState<'1D' | '15m'>(initialTimeframe);

  // Bars and Metadata state
  const [chartBars, setChartBars] = useState<CandleBar[]>(initialBars || []);
  const [strategyData, setStrategyData] = useState<StrategyOverlay | null>(propStrategyOverlay || null);
  const [feedStatus, setFeedStatus] = useState<'LIVE' | 'DELAYED' | 'STALE' | 'DISCONNECTED'>('DELAYED');
  const [providerName, setProviderName] = useState<string>(market === 'IN' ? 'Angel One' : 'Yahoo Finance');
  const [lastQuoteTime, setLastQuoteTime] = useState<string | null>(null);
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(!initialBars || initialBars.length === 0);
  const [error, setError] = useState<string | null>(null);

  // Hover Crosshair Ticker state
  const [hoveredBar, setHoveredBar] = useState<CandleBar | null>(null);

  // Persistent visual preferences
  const [prefs, setPrefs] = useState<ChartPreferences>(() => {
    try {
      const saved = localStorage.getItem(PREFS_KEY);
      if (saved) return { ...DEFAULT_PREFS, ...JSON.parse(saved) };
    } catch {}
    return DEFAULT_PREFS;
  });

  // Strategy Details drawer toggle
  const [showStrategyDrawer, setShowStrategyDrawer] = useState<boolean>(false);

  // Manual Drawing Tools State
  const [activeTool, setActiveTool] = useState<'cursor' | 'hline' | 'trendline' | 'rect'>('cursor');
  const [drawings, setDrawings] = useState<ChartDrawing[]>(() => {
    try {
      const saved = localStorage.getItem(`algo_trading_drawings_${symbol}`);
      if (saved) return JSON.parse(saved);
    } catch {}
    return [];
  });
  const [pendingPoint, setPendingPoint] = useState<DrawingPoint | null>(null);
  const [renderTick, setRenderTick] = useState<number>(0);

  const togglePref = (key: keyof ChartPreferences) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(PREFS_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });
  };

  // Save drawings per symbol
  useEffect(() => {
    try {
      localStorage.setItem(`algo_trading_drawings_${symbol}`, JSON.stringify(drawings));
    } catch {}
  }, [drawings, symbol]);

  // Fetch Bars function
  const fetchBarsData = useCallback(async (isPolling: boolean = false) => {
    if (!symbol) return;
    try {
      if (!isPolling) setLoading(true);
      setError(null);

      const tfParam = timeframe === '15m' ? '15m' : '1d';
      const data: BarsResponse = await apiClient.getBars(symbol, market, tfParam, 200);

      if (data && data.bars && data.bars.length > 0) {
        setChartBars(data.bars);
        setFeedStatus(data.feed_status);
        setProviderName(data.provider);
        setLastQuoteTime(data.last_quote_time || null);
        setCurrentPrice(data.current_price || (data.bars[data.bars.length - 1]?.close ?? null));
        if (data.strategy_overlay) {
          setStrategyData(data.strategy_overlay);
        }
      } else if (!isPolling) {
        setError(`No historical bar data available for ${symbol} (${timeframe})`);
      }
    } catch (err: any) {
      if (!isPolling) {
        setError(err.message || 'Failed to fetch historical candlestick bars');
      }
    } finally {
      if (!isPolling) setLoading(false);
    }
  }, [symbol, market, timeframe]);

  // Initial fetch and on timeframe switch
  useEffect(() => {
    fetchBarsData(false);
  }, [fetchBarsData]);

  // Live polling every 12 seconds for active current bar updates
  useEffect(() => {
    const timer = setInterval(() => {
      fetchBarsData(true);
    }, 12000);
    return () => clearInterval(timer);
  }, [fetchBarsData]);

  // Trigger, Stop, Target effective values
  const effectiveTrigger = strategyData?.trigger || propTrigger;
  const effectiveStop = strategyData?.stop || propStop;
  const effectiveTarget = strategyData?.target1 || propTarget;
  const effectiveTarget2 = (effectiveTrigger && effectiveStop && effectiveTrigger > effectiveStop)
    ? Number((effectiveTrigger + 3.0 * (effectiveTrigger - effectiveStop)).toFixed(2))
    : (strategyData?.target2 || null);
  const effectiveEntryHigh = strategyData?.entry_zone_high;
  const [useTradingViewStream, setUseTradingViewStream] = useState<boolean>(false);

  // Build Lightweight Chart instance
  useEffect(() => {
    if (!chartContainerRef.current || chartBars.length === 0) return;

    // Clean previous chart instance
    if (chartInstanceRef.current) {
      chartInstanceRef.current.remove();
      chartInstanceRef.current = null;
    }

    const container = chartContainerRef.current;
    const chartHeight = fullHeight ? container.clientHeight || 580 : 500;

    const chart = createChart(container, {
      width: container.clientWidth || 800,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#172033', style: LineStyle.SparseDotted },
        horzLines: { color: '#172033', style: LineStyle.SparseDotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: '#475569',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#1e293b',
        },
        horzLine: {
          color: '#475569',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#1e293b',
        },
      },
      rightPriceScale: {
        borderColor: '#1e293b',
        scaleMargins: {
          top: 0.1,
          bottom: prefs.showVolume ? 0.22 : 0.1,
        },
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: timeframe === '15m',
        secondsVisible: false,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
    });

    chartInstanceRef.current = chart;

    // Format & deduplicate candlestick data
    const sortedBars = [...chartBars].sort((a, b) => {
      const tA = typeof a.time === 'number' ? a.time : new Date(a.time).getTime();
      const tB = typeof b.time === 'number' ? b.time : new Date(b.time).getTime();
      return tA - tB;
    });

    const uniqueMap = new Map<string | number, CandleBar>();
    for (const b of sortedBars) {
      uniqueMap.set(b.time, b);
    }
    const cleanBars = Array.from(uniqueMap.values());

    // 1. Candlestick Series (Pane 0)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    });
    candleSeriesRef.current = candleSeries;

    const candleData = cleanBars.map((b) => ({
      time: b.time as Time,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    candleSeries.setData(candleData);

    // 2. Volume Series (Pane 0, Overlay scale)
    if (prefs.showVolume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: 'volume',
        priceFormat: { type: 'volume' },
      });
      volumeSeriesRef.current = volumeSeries;

      chart.priceScale('volume').applyOptions({
        scaleMargins: {
          top: 0.8,
          bottom: 0,
        },
      });

      const volumeData = cleanBars.map((b) => ({
        time: b.time as Time,
        value: b.volume,
        color: b.close >= b.open ? '#10b98144' : '#f43f5e44',
      }));
      volumeSeries.setData(volumeData);
    }

    // 3. Moving Average Series (Pane 0)
    const addMaSeries = (
      name: string,
      color: string,
      lineWidth: number,
      key: keyof CandleBar,
      enabled: boolean
    ) => {
      if (!enabled) return;
      const maSeries = chart.addSeries(LineSeries, {
        color,
        lineWidth: lineWidth as any,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      });
      const data = cleanBars
        .filter((b) => b[key] != null && !isNaN(Number(b[key])))
        .map((b) => ({
          time: b.time as Time,
          value: Number(b[key]),
        }));
      maSeries.setData(data);
    };

    addMaSeries('EMA 20', '#f59e0b', 1, 'ema20', prefs.showEma20);
    addMaSeries('EMA 50', '#fb923c', 1, 'ema50', prefs.showEma50);
    addMaSeries('SMA 50', '#3b82f6', 1, 'sma50', prefs.showSma50);
    addMaSeries('SMA 150', '#14b8a6', 1, 'sma150', prefs.showSma150);
    addMaSeries('SMA 200', '#a855f7', 2, 'sma200', prefs.showSma200);

    // 4. Separate Indicator Panels: RSI 14 (Pane 1)
    if (prefs.showRsi) {
      try {
        const rsiPane = chart.addPane();
        rsiPane.setStretchFactor(0.24);
        const rsiSeries = rsiPane.addSeries(LineSeries, {
          color: '#c084fc',
          lineWidth: 1,
          priceLineVisible: false,
        });

        const rsiData = cleanBars
          .filter((b) => b.rsi14 != null && !isNaN(Number(b.rsi14)))
          .map((b) => ({
            time: b.time as Time,
            value: Number(b.rsi14),
          }));
        rsiSeries.setData(rsiData);

        // Overbought (70) and Oversold (30) reference levels
        rsiSeries.createPriceLine({
          price: 70,
          color: '#f43f5e88',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: '70 OB',
        });
        rsiSeries.createPriceLine({
          price: 30,
          color: '#10b98188',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: '30 OS',
        });
      } catch (paneErr) {
        console.warn('Could not initialize separate RSI pane:', paneErr);
      }
    }

    // 5. Separate Indicator Panels: ATR 14 (Pane 2)
    if (prefs.showAtr) {
      try {
        const atrPane = chart.addPane();
        atrPane.setStretchFactor(0.2);
        const atrSeries = atrPane.addSeries(LineSeries, {
          color: '#06b6d4',
          lineWidth: 1,
          priceLineVisible: false,
        });

        const atrData = cleanBars
          .filter((b) => b.atr14 != null && !isNaN(Number(b.atr14)))
          .map((b) => ({
            time: b.time as Time,
            value: Number(b.atr14),
          }));
        atrSeries.setData(atrData);
      } catch (paneErr) {
        console.warn('Could not initialize separate ATR pane:', paneErr);
      }
    }

    // 6. Strategy Overlay Levels: Trigger, Stop, Target 1, Target 2, Entry Zone
    if (prefs.showEntryTrigger && effectiveTrigger && effectiveTrigger > 0) {
      candleSeries.createPriceLine({
        price: effectiveTrigger,
        color: '#10b981',
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `BUY TRIGGER: ${effectiveTrigger.toFixed(2)}`,
      });
    }

    if (prefs.showEntryTrigger && effectiveEntryHigh && effectiveEntryHigh > 0 && effectiveTrigger && effectiveEntryHigh > effectiveTrigger) {
      candleSeries.createPriceLine({
        price: effectiveEntryHigh,
        color: '#34d399',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: `ENTRY CEILING: ${effectiveEntryHigh.toFixed(2)}`,
      });
    }

    if (prefs.showStopLoss && effectiveStop && effectiveStop > 0) {
      candleSeries.createPriceLine({
        price: effectiveStop,
        color: '#f43f5e',
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `STOP LOSS: ${effectiveStop.toFixed(2)}`,
      });
    }

    if (prefs.showTarget1 && effectiveTarget && effectiveTarget > 0) {
      candleSeries.createPriceLine({
        price: effectiveTarget,
        color: '#06b6d4',
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `TARGET 1 (2R): ${effectiveTarget.toFixed(2)}`,
      });
    }

    if (prefs.showTarget2 && effectiveTarget2 && effectiveTarget2 > 0) {
      candleSeries.createPriceLine({
        price: effectiveTarget2,
        color: '#38bdf8',
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `TARGET 2 (3R): ${effectiveTarget2.toFixed(2)}`,
      });
    }

    // 7. Signal Markers on Candlestick Chart
    if (strategyData && cleanBars.length > 0) {
      const lastBar = cleanBars[cleanBars.length - 1];
      const state = strategyData.state || 'WATCHLIST';
      let markerColor = '#6366f1';
      let markerText = `SETUP: ${strategyData.setup}`;

      if (state.includes('CONFIRMED')) {
        markerColor = '#10b981';
        markerText = `CONFIRMED (${strategyData.setup})`;
      } else if (state.includes('PROVISIONAL') || state === 'APPROACHING') {
        markerColor = '#f59e0b';
        markerText = `NEAR BREAKOUT: ${effectiveTrigger?.toFixed(2)}`;
      } else if (state === 'BLOCKED' || state === 'INVALIDATED') {
        markerColor = '#f43f5e';
        markerText = `${state}`;
      }

      const markers: SeriesMarker<Time>[] = [
        {
          time: lastBar.time as Time,
          position: 'belowBar',
          color: markerColor,
          shape: 'arrowUp',
          text: markerText,
        },
      ];

      createSeriesMarkers(candleSeries, markers);
    }

    // 8. Crosshair hover inspection
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        setHoveredBar(cleanBars[cleanBars.length - 1] || null);
        return;
      }
      const bar = cleanBars.find((b) => b.time === param.time);
      if (bar) {
        setHoveredBar(bar);
      }
    });

    // Subscribe to visible time range changes to re-align drawings
    chart.timeScale().subscribeVisibleTimeRangeChange(() => {
      setRenderTick((t) => t + 1);
    });

    // Fit content on initial load
    chart.timeScale().fitContent();

    // Auto-resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0 || !chartInstanceRef.current) return;
      const { width, height } = entries[0].contentRect;
      chartInstanceRef.current.applyOptions({
        width: Math.max(300, width),
        height: fullHeight ? Math.max(400, height) : 500,
      });
      setRenderTick((t) => t + 1);
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (chartInstanceRef.current) {
        chartInstanceRef.current.remove();
        chartInstanceRef.current = null;
      }
    };
  }, [
    chartBars,
    prefs,
    timeframe,
    effectiveTrigger,
    effectiveStop,
    effectiveTarget,
    effectiveTarget2,
    effectiveEntryHigh,
    strategyData,
    fullHeight,
  ]);

  // Handle click on drawing overlay
  const handleOverlayClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (activeTool === 'cursor' || !chartInstanceRef.current || !candleSeriesRef.current) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const chart = chartInstanceRef.current;
    const series = candleSeriesRef.current;

    const clickedPrice = series.coordinateToPrice(y);
    const clickedTime = chart.timeScale().coordinateToTime(x);

    if (clickedPrice == null) return;

    if (activeTool === 'hline') {
      const newDrawing: ChartDrawing = {
        id: `hline_${Date.now()}`,
        type: 'hline',
        price: Number(clickedPrice.toFixed(2)),
        color: '#f59e0b',
      };
      setDrawings((prev) => [...prev, newDrawing]);
      setActiveTool('cursor');
      return;
    }

    if (clickedTime == null) return;

    if (!pendingPoint) {
      setPendingPoint({ time: clickedTime, price: Number(clickedPrice.toFixed(2)) });
    } else {
      const newDrawing: ChartDrawing = {
        id: `${activeTool}_${Date.now()}`,
        type: activeTool,
        p1: pendingPoint,
        p2: { time: clickedTime, price: Number(clickedPrice.toFixed(2)) },
        color: activeTool === 'rect' ? '#6366f1' : '#38bdf8',
      };
      setDrawings((prev) => [...prev, newDrawing]);
      setPendingPoint(null);
      setActiveTool('cursor');
    }
  };

  const removeDrawing = (id: string) => {
    setDrawings((prev) => prev.filter((d) => d.id !== id));
  };

  const clearAllDrawings = () => {
    setDrawings([]);
    setPendingPoint(null);
  };

  // Compute screen coordinates for SVG drawings
  const renderedDrawings: RenderedDrawing[] = useMemo(() => {
    if (!chartInstanceRef.current || !candleSeriesRef.current) return [];
    const chart = chartInstanceRef.current;
    const series = candleSeriesRef.current;

    return drawings.map((d): RenderedDrawing => {
      if (d.type === 'hline' && d.price != null) {
        const y = series.priceToCoordinate(d.price);
        return { ...d, yCoord: y };
      }
      if (d.p1 && d.p2) {
        const x1 = chart.timeScale().timeToCoordinate(d.p1.time);
        const y1 = series.priceToCoordinate(d.p1.price);
        const x2 = chart.timeScale().timeToCoordinate(d.p2.time);
        const y2 = series.priceToCoordinate(d.p2.price);
        return { ...d, x1, y1, x2, y2 };
      }
      return { ...d };
    });
  }, [drawings, renderTick]);

  // Compute VCP Base box coordinates
  const vcpBaseBox = useMemo(() => {
    if (!strategyData?.vcp_base || !chartInstanceRef.current || !candleSeriesRef.current) return null;
    const base = strategyData.vcp_base;
    const chart = chartInstanceRef.current;
    const series = candleSeriesRef.current;

    const x1 = chart.timeScale().timeToCoordinate(base.start_time as Time);
    const x2 = chart.timeScale().timeToCoordinate(base.end_time as Time);
    const yTop = series.priceToCoordinate(base.base_high);
    const yBottom = series.priceToCoordinate(base.base_low);

    if (x1 == null || x2 == null || yTop == null || yBottom == null) return null;

    return {
      x: Math.min(x1, x2),
      y: Math.min(yTop, yBottom),
      width: Math.max(10, Math.abs(x2 - x1)),
      height: Math.max(10, Math.abs(yBottom - yTop)),
      high: base.base_high,
      low: base.base_low,
      pivot: base.pivot,
      bars: base.base_bars,
    };
  }, [strategyData, renderTick]);

  const activeBar = hoveredBar || chartBars[chartBars.length - 1];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl flex flex-col shadow-2xl overflow-hidden font-sans">
      {/* 1. Header Toolbar: Symbol, Market, Timeframe, Live Feed Status, Quote Ticker */}
      <div className="px-5 py-3 border-b border-slate-800/90 bg-slate-900/90 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-extrabold text-white text-base tracking-tight">{symbol}</span>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
              {market === 'IN' ? 'NSE' : 'NASDAQ'}
            </span>
          </div>

          {/* Timeframe Selector */}
          <div className="flex items-center bg-slate-950/80 rounded-lg p-0.5 border border-slate-800">
            {(['1D', '15m'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 rounded-md text-xs font-semibold transition ${
                  timeframe === tf
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Official TradingView Real-Time Chart Switcher */}
          <button
            onClick={() => setUseTradingViewStream(!useTradingViewStream)}
            className={`px-2.5 py-1 rounded-md text-xs font-semibold flex items-center gap-1.5 border transition ${
              useTradingViewStream
                ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300'
                : 'bg-slate-950/80 border-slate-800 text-slate-400 hover:text-white'
            }`}
            title="Toggle Official TradingView Real-Time Live Feed (0-Latency)"
          >
            <Zap className={`w-3.5 h-3.5 ${useTradingViewStream ? 'text-emerald-400 fill-emerald-400' : 'text-amber-400'}`} />
            <span>{useTradingViewStream ? 'TradingView Live' : 'TradingView'}</span>
          </button>

          {/* Live / Feed Status Pill */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border bg-slate-950/60 border-slate-800">
            <span
              className={`w-2 h-2 rounded-full ${
                feedStatus === 'LIVE'
                  ? 'bg-emerald-400 animate-pulse'
                  : feedStatus === 'DELAYED'
                  ? 'bg-amber-400'
                  : feedStatus === 'STALE'
                  ? 'bg-rose-500'
                  : 'bg-slate-500'
              }`}
            />
            <span
              className={
                feedStatus === 'LIVE'
                  ? 'text-emerald-400'
                  : feedStatus === 'DELAYED'
                  ? 'text-amber-400'
                  : feedStatus === 'STALE'
                  ? 'text-rose-400'
                  : 'text-slate-400'
              }
            >
              {feedStatus}
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400 text-[10px]">{providerName}</span>
          </div>

          {lastQuoteTime && (
            <span className="text-[10px] text-slate-500 hidden sm:inline">
              Updated: {new Date(lastQuoteTime).toLocaleTimeString()}
            </span>
          )}
        </div>

        {/* OHLCV Crosshair Ticker Header */}
        {activeBar && (
          <div className="flex flex-wrap items-center gap-3 text-xs font-mono text-slate-300">
            <span>
              O: <span className="text-slate-100 font-semibold">{activeBar.open.toFixed(2)}</span>
            </span>
            <span>
              H: <span className="text-emerald-400 font-semibold">{activeBar.high.toFixed(2)}</span>
            </span>
            <span>
              L: <span className="text-rose-400 font-semibold">{activeBar.low.toFixed(2)}</span>
            </span>
            <span>
              C: <span className="text-indigo-300 font-bold">{activeBar.close.toFixed(2)}</span>
            </span>
            {activeBar.volume > 0 && (
              <span className="text-slate-400">
                Vol: <span className="text-slate-200 font-semibold">{(activeBar.volume / 1000).toFixed(0)}k</span>
              </span>
            )}
            {activeBar.rsi14 && (
              <span>
                RSI: <span className="text-purple-400 font-semibold">{activeBar.rsi14.toFixed(1)}</span>
              </span>
            )}
            {activeBar.atr14 && (
              <span>
                ATR: <span className="text-cyan-400 font-semibold">{activeBar.atr14.toFixed(2)}</span>
              </span>
            )}
          </div>
        )}
      </div>

      {/* 2. Controls & Preferences Bar: Moving Averages, Panels, Drawing Tools */}
      <div className="px-5 py-2.5 bg-slate-950/70 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Moving Averages & Indicator Toggles */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-slate-500 text-[11px] font-semibold flex items-center gap-1">
            <Layers className="w-3.5 h-3.5" /> Indicators:
          </span>

          <button
            onClick={() => togglePref('showEma20')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showEma20
                ? 'bg-amber-500/10 border-amber-500/40 text-amber-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            <span className="w-2 h-0.5 bg-amber-400 rounded"></span> EMA 20
          </button>

          <button
            onClick={() => togglePref('showEma50')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showEma50
                ? 'bg-orange-500/10 border-orange-500/40 text-orange-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            <span className="w-2 h-0.5 bg-orange-400 rounded"></span> EMA 50
          </button>

          <button
            onClick={() => togglePref('showSma50')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showSma50
                ? 'bg-blue-500/10 border-blue-500/40 text-blue-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            <span className="w-2 h-0.5 bg-blue-400 rounded"></span> SMA 50
          </button>

          <button
            onClick={() => togglePref('showSma150')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showSma150
                ? 'bg-teal-500/10 border-teal-500/40 text-teal-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            <span className="w-2 h-0.5 bg-teal-400 rounded"></span> SMA 150
          </button>

          <button
            onClick={() => togglePref('showSma200')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showSma200
                ? 'bg-purple-500/10 border-purple-500/40 text-purple-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            <span className="w-2 h-0.5 bg-purple-400 rounded"></span> SMA 200
          </button>

          <button
            onClick={() => togglePref('showVolume')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showVolume
                ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            <span className="w-1.5 h-1.5 bg-emerald-400 rounded-sm"></span> Vol
          </button>

          <button
            onClick={() => togglePref('showRsi')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showRsi
                ? 'bg-purple-500/10 border-purple-500/40 text-purple-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            RSI Panel
          </button>

          <button
            onClick={() => togglePref('showAtr')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
              prefs.showAtr
                ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
            }`}
          >
            ATR Panel
          </button>

          {/* Strategy Levels Hide/Show Toggles */}
          {(effectiveTrigger || effectiveStop || strategyData) && (
            <div className="flex flex-wrap items-center gap-1.5 pl-2 border-l border-slate-800">
              <span className="text-slate-500 text-[11px] font-semibold flex items-center gap-1">
                <Target className="w-3.5 h-3.5 text-indigo-400" /> Levels:
              </span>

              <button
                onClick={() => togglePref('showEntryTrigger')}
                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
                  prefs.showEntryTrigger
                    ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
                    : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
                }`}
                title="Toggle Entry / Buy Trigger Pivot Line"
              >
                <span className="w-2 h-0.5 bg-emerald-400 rounded"></span> Entry
              </button>

              <button
                onClick={() => togglePref('showStopLoss')}
                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
                  prefs.showStopLoss
                    ? 'bg-rose-500/10 border-rose-500/40 text-rose-300'
                    : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
                }`}
                title="Toggle Stop Loss Risk Line"
              >
                <span className="w-2 h-0.5 bg-rose-400 rounded"></span> Stop Loss
              </button>

              <button
                onClick={() => togglePref('showTarget1')}
                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
                  prefs.showTarget1
                    ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-300'
                    : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
                }`}
                title="Toggle Target 1 (2R)"
              >
                <span className="w-2 h-0.5 bg-cyan-400 rounded"></span> Target 1
              </button>

              <button
                onClick={() => togglePref('showTarget2')}
                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
                  prefs.showTarget2
                    ? 'bg-sky-500/10 border-sky-500/40 text-sky-300'
                    : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
                }`}
                title="Toggle Target 2 (3R)"
              >
                <span className="w-2 h-0.5 bg-sky-400 rounded"></span> Target 2
              </button>

              <button
                onClick={() => togglePref('showVcpBase')}
                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition flex items-center gap-1 ${
                  prefs.showVcpBase
                    ? 'bg-indigo-500/10 border-indigo-500/40 text-indigo-300'
                    : 'bg-slate-900 border-slate-800 text-slate-500 line-through'
                }`}
                title="Toggle VCP Consolidation Base Box"
              >
                <span className="w-1.5 h-1.5 bg-indigo-400 rounded-sm"></span> VCP Base
              </button>
            </div>
          )}
        </div>

        {/* Drawing Tools Toolbar */}
        <div className="flex items-center gap-2">
          <span className="text-slate-500 text-[11px] font-semibold">Draw:</span>

          <button
            onClick={() => {
              setActiveTool('cursor');
              setPendingPoint(null);
            }}
            title="Pan / Crosshair"
            className={`p-1.5 rounded border transition ${
              activeTool === 'cursor'
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            <Crosshair className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => {
              setActiveTool('hline');
              setPendingPoint(null);
            }}
            title="Horizontal Price Line (Click on chart)"
            className={`p-1.5 rounded border transition ${
              activeTool === 'hline'
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            <Minus className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => {
              setActiveTool('trendline');
              setPendingPoint(null);
            }}
            title="Trendline (Click 2 points)"
            className={`p-1.5 rounded border transition ${
              activeTool === 'trendline'
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => {
              setActiveTool('rect');
              setPendingPoint(null);
            }}
            title="Rectangle / Base Area (Click 2 corners)"
            className={`p-1.5 rounded border transition ${
              activeTool === 'rect'
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            <Square className="w-3.5 h-3.5" />
          </button>

          {drawings.length > 0 && (
            <button
              onClick={clearAllDrawings}
              title="Clear all manual drawings"
              className="p-1.5 rounded border bg-slate-900 border-slate-800 text-rose-400 hover:bg-rose-950/40 hover:border-rose-800 transition"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}

          <button
            onClick={() => chartInstanceRef.current?.timeScale().fitContent()}
            title="Reset Zoom / Fit Content"
            className="p-1.5 rounded border bg-slate-900 border-slate-800 text-slate-400 hover:text-white transition"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 3. Strategy Header Banner: VCP / Pullback Setup, Trigger, SL, Target & Trend Template */}
      {strategyData && (
        <div className="px-5 py-2.5 bg-slate-950/90 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="px-2 py-0.5 rounded font-bold bg-indigo-950 text-indigo-300 border border-indigo-800">
                {strategyData.setup} SETUP
              </span>
              <span
                className={`px-2 py-0.5 rounded font-semibold text-[10px] ${
                  strategyData.state.includes('CONFIRMED')
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                    : strategyData.state === 'APPROACHING'
                    ? 'bg-amber-950 text-amber-300 border border-amber-800'
                    : 'bg-slate-800 text-slate-300 border border-slate-700'
                }`}
              >
                {strategyData.state}
              </span>
            </div>

            {effectiveTrigger && (
              <span className="font-mono text-emerald-400 font-semibold">
                Buy Trigger: ₹{effectiveTrigger.toFixed(2)}
              </span>
            )}
            {effectiveEntryHigh && (
              <span className="font-mono text-teal-400 text-slate-400">
                Zone Ceiling: ₹{effectiveEntryHigh.toFixed(2)}
              </span>
            )}
            {effectiveStop && (
              <span className="font-mono text-rose-400 font-semibold">
                Stop Loss: ₹{effectiveStop.toFixed(2)}
              </span>
            )}
            {effectiveTarget && (
              <span className="font-mono text-cyan-400 font-semibold">
                2R Target: ₹{effectiveTarget.toFixed(2)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Trend Template Pass/Fail badge */}
            {strategyData.trend_template && strategyData.trend_template.length > 0 && (
              <button
                onClick={() => setShowStrategyDrawer(!showStrategyDrawer)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-700 hover:border-indigo-500 text-slate-300 transition text-[11px]"
              >
                <Activity className="w-3.5 h-3.5 text-indigo-400" />
                <span>
                  Trend Template:{' '}
                  <span className="font-bold text-white">
                    {strategyData.trend_template.filter((r) => r.passed).length} /{' '}
                    {strategyData.trend_template.length}
                  </span>
                </span>
                {showStrategyDrawer ? (
                  <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                )}
              </button>
            )}
          </div>
        </div>
      )}

      {/* 4. Strategy Details Dropdown: Minervini Trend Template & Strategy Rationale */}
      {showStrategyDrawer && strategyData && (
        <div className="px-5 py-4 bg-slate-950 border-b border-slate-800 text-xs flex flex-col gap-3 animate-fadeIn">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Trend Template Checklist */}
            {strategyData.trend_template && strategyData.trend_template.length > 0 && (
              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800">
                <h4 className="font-bold text-white text-xs mb-2 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  Minervini Stage 2 Trend Template Criteria
                </h4>
                <div className="space-y-1.5">
                  {strategyData.trend_template.map((rule, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-[11px] py-1 border-b border-slate-800/60 last:border-0"
                    >
                      <div className="flex items-center gap-2">
                        {rule.passed ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                        )}
                        <span className={rule.passed ? 'text-slate-300' : 'text-slate-400'}>
                          {rule.rule}
                        </span>
                      </div>
                      <div className="font-mono text-slate-400 text-[10px]">
                        {rule.actual} <span className="text-slate-600">({rule.expected})</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Setup Rationale & VCP Details */}
            <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 flex flex-col justify-between">
              <div>
                <h4 className="font-bold text-white text-xs mb-2 flex items-center gap-1.5">
                  <Zap className="w-4 h-4 text-amber-400" />
                  Pattern & Setup Rationale
                </h4>
                <ul className="space-y-1.5 text-slate-300 text-[11px]">
                  {strategyData.reasons.map((reason, idx) => (
                    <li key={idx} className="flex items-start gap-1.5">
                      <span className="text-indigo-400 font-bold">•</span>
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {strategyData.vcp_base && (
                <div className="mt-3 pt-3 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between font-mono">
                  <span>Base Sessions: {strategyData.vcp_base.base_bars}</span>
                  <span>Pivot: ₹{strategyData.vcp_base.base_high.toFixed(2)}</span>
                  <span>Base Low: ₹{strategyData.vcp_base.base_low.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 5. Chart Body: Lightweight Charts Canvas + Interactive SVG Drawing Overlay OR TradingView Realtime */}
      <div className="relative w-full flex-1 min-h-[480px] bg-slate-950">
        {useTradingViewStream ? (
          <TradingViewRealtimeChart
            symbol={symbol}
            market={market}
            height={fullHeight ? '100%' : 500}
          />
        ) : (
          <>
            {loading && (
              <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-slate-950/70 backdrop-blur-sm text-slate-400 text-sm gap-2">
                <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
                <span>Loading {timeframe} candlestick bars...</span>
              </div>
            )}

            {error && (
              <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-slate-950/90 text-rose-400 text-sm gap-3 p-6 text-center">
                <AlertCircle className="w-8 h-8 text-rose-400" />
                <span className="max-w-md">{error}</span>
                <div className="flex flex-wrap items-center justify-center gap-3 mt-2">
                  <button
                    onClick={() => fetchBarsData(false)}
                    className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold transition"
                  >
                    Retry Load
                  </button>
                  <button
                    onClick={() => setUseTradingViewStream(true)}
                    className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-lg transition"
                  >
                    <Zap className="w-3.5 h-3.5 fill-white" />
                    Switch to TradingView Live Feed (0-Latency)
                  </button>
                </div>
              </div>
            )}

            {/* Lightweight Charts mounting DOM container */}
            <div ref={chartContainerRef} className="w-full h-full min-h-[480px]" />

        {/* SVG Drawing Overlay */}
        <svg
          onClick={handleOverlayClick}
          className={`absolute inset-0 w-full h-full ${
            activeTool === 'cursor' ? 'pointer-events-none' : 'pointer-events-auto cursor-crosshair'
          }`}
        >
          {/* VCP Base Consolidation Area Highlight Box */}
          {prefs.showVcpBase && vcpBaseBox && (
            <g className="pointer-events-none">
              <rect
                x={vcpBaseBox.x}
                y={vcpBaseBox.y}
                width={vcpBaseBox.width}
                height={vcpBaseBox.height}
                fill="#6366f1"
                fillOpacity="0.08"
                stroke="#6366f1"
                strokeWidth="1.2"
                strokeDasharray="3 3"
                rx="3"
              />
              <text
                x={vcpBaseBox.x + 8}
                y={vcpBaseBox.y + 16}
                fill="#818cf8"
                fontSize="10"
                fontFamily="sans-serif"
                fontWeight="bold"
              >
                VCP BASE ({vcpBaseBox.bars} Bars)
              </text>
            </g>
          )}

          {/* Render User Manual Drawings */}
          {renderedDrawings.map((d) => {
            if (d.type === 'hline' && d.yCoord != null) {
              return (
                <g key={d.id} className="group cursor-pointer pointer-events-auto">
                  <line
                    x1="0"
                    y1={d.yCoord}
                    x2="100%"
                    y2={d.yCoord}
                    stroke={d.color}
                    strokeWidth="1.5"
                    strokeDasharray="4 4"
                  />
                  <text
                    x="8"
                    y={d.yCoord - 4}
                    fill={d.color}
                    fontSize="10"
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    HL: {d.price?.toFixed(2)}
                  </text>
                </g>
              );
            }

            if (d.type === 'trendline' && d.x1 != null && d.y1 != null && d.x2 != null && d.y2 != null) {
              return (
                <g key={d.id} className="cursor-pointer pointer-events-auto">
                  <line
                    x1={d.x1}
                    y1={d.y1}
                    x2={d.x2}
                    y2={d.y2}
                    stroke={d.color}
                    strokeWidth="2"
                  />
                  <circle cx={d.x1} cy={d.y1} r="3" fill={d.color} />
                  <circle cx={d.x2} cy={d.y2} r="3" fill={d.color} />
                </g>
              );
            }

            if (d.type === 'rect' && d.x1 != null && d.y1 != null && d.x2 != null && d.y2 != null) {
              const x = Math.min(d.x1, d.x2);
              const y = Math.min(d.y1, d.y2);
              const w = Math.abs(d.x2 - d.x1);
              const h = Math.abs(d.y2 - d.y1);
              return (
                <g key={d.id} className="cursor-pointer pointer-events-auto">
                  <rect
                    x={x}
                    y={y}
                    width={w}
                    height={h}
                    fill={d.color}
                    fillOpacity="0.12"
                    stroke={d.color}
                    strokeWidth="1.5"
                    strokeDasharray="3 3"
                    rx="2"
                  />
                </g>
              );
            }

            return null;
          })}
        </svg>
      </>
    )}
  </div>
    </div>
  );
};
