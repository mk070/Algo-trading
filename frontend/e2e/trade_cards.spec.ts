import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// Seeded mock trades satisfying all required conditions:
// 1. Winner trade
// 2. Stop-out trade
// 3. Gap-through-stop trade
// 4. Time-exit trade
// 5. Open trade
const MOCK_TRADES = [
  {
    id: 1,
    source: 'paper',
    study_id: 'study_live_1',
    strategy_id: 'S01',
    symbol: 'RELIANCE',
    side: 'SELL',
    qty: 10,
    signal_date: '2026-11-10', // Tuesday
    entry_date: '2026-11-11',  // Wednesday
    exec_date: '2026-11-17',   // Tuesday
    exit_date: '2026-11-17',
    fill_price: 2500.0,
    entry_price: 2500.0,
    exit_price: 2650.0,
    stop_price: 2420.0,
    planned_exit_date: '2026-11-17',
    holding_days_target: 4,
    net_pnl: 1450.0,
    gross_pnl: 1500.0,
    r_multiple: 1.81,
    exit_reason: 'TIME_EXIT',
    reason_text: 'EMA20 pullback with RSI14 upward turn above long-term trend filter.',
    trade_key: 'tkey_rel_1',
    data_through_date: '2026-11-23',
  },
  {
    id: 2,
    source: 'paper',
    study_id: 'study_live_1',
    strategy_id: 'S02',
    symbol: 'TCS',
    side: 'SELL',
    qty: 5,
    signal_date: '2026-11-11', // Wednesday
    entry_date: '2026-11-12',  // Thursday
    exec_date: '2026-11-16',   // Monday
    exit_date: '2026-11-16',
    fill_price: 3500.0,
    entry_price: 3500.0,
    exit_price: 3396.6,
    stop_price: 3400.0,
    planned_exit_date: '2026-11-18',
    holding_days_target: 4,
    net_pnl: -535.0,
    gross_pnl: -517.0,
    r_multiple: -1.04,
    exit_reason: 'STOP_HIT',
    reason_text: 'Closed above prior 20-bar Donchian high with volume confirmation.',
    trade_key: 'tkey_tcs_2',
    data_through_date: '2026-11-23',
  },
  {
    id: 3,
    source: 'paper',
    study_id: 'study_live_1',
    strategy_id: 'S03',
    symbol: 'INFY',
    side: 'SELL',
    qty: 15,
    signal_date: '2026-11-12', // Thursday
    entry_date: '2026-11-13',  // Friday
    exec_date: '2026-11-17',   // Tuesday (gap down open at 1400, below stop 1450)
    exit_date: '2026-11-17',
    fill_price: 1500.0,
    entry_price: 1500.0,
    exit_price: 1398.6,       // Fill at open (1400) * (1 - 0.001 slippage) = 1398.6
    stop_price: 1450.0,
    planned_exit_date: '2026-11-19',
    holding_days_target: 4,
    net_pnl: -1550.0,
    gross_pnl: -1521.0,
    r_multiple: -2.03,
    exit_reason: 'GAP_THROUGH_STOP',
    reason_text: 'Closed above 55-day high with volume confirmation above SMA50 and SMA200.',
    trade_key: 'tkey_infy_3',
    data_through_date: '2026-11-23',
  },
  {
    id: 4,
    source: 'paper',
    study_id: 'study_live_1',
    strategy_id: 'S04',
    symbol: 'HDFCBANK',
    side: 'SELL',
    qty: 20,
    signal_date: '2026-11-10', // Tuesday
    entry_date: '2026-11-11',  // Wednesday
    exec_date: '2026-11-17',   // Tuesday
    exit_date: '2026-11-17',
    fill_price: 1600.0,
    entry_price: 1600.0,
    exit_price: 1640.0,
    stop_price: 1550.0,
    planned_exit_date: '2026-11-17',
    holding_days_target: 4,
    net_pnl: 760.0,
    gross_pnl: 800.0,
    r_multiple: 0.76,
    exit_reason: 'TIME_EXIT',
    reason_text: 'RSI(5) dropped below 25 (oversold) while above 200-day SMA — mean reversion setup.',
    trade_key: 'tkey_hdfc_4',
    data_through_date: '2026-11-23',
  },
  {
    id: 5,
    source: 'paper',
    study_id: 'study_live_1',
    strategy_id: 'S05',
    symbol: 'ICICIBANK',
    side: 'BUY',
    qty: 25,
    signal_date: '2026-11-19', // Thursday
    entry_date: '2026-11-20',  // Friday
    fill_price: 1100.0,
    entry_price: 1100.0,
    stop_price: 1070.0,
    planned_exit_date: '2026-11-26', // Thursday next week
    holding_days_target: 4,
    net_pnl: null,
    gross_pnl: null,
    r_multiple: null,
    exit_reason: null,
    reason_text: '3 consecutive lower closes while above SMA50 and SMA200 — mean reversion dip.',
    trade_key: 'tkey_icici_5',
    data_through_date: '2026-11-23',
  },
];

// 10 valid weekday bars spanning 2026-11-09 through 2026-11-20
const MOCK_CHART_BARS = [
  { time: '2026-11-09', open: 2480, high: 2510, low: 2470, close: 2490, volume: 100000 },
  { time: '2026-11-10', open: 2490, high: 2520, low: 2485, close: 2505, volume: 120000 },
  { time: '2026-11-11', open: 2500, high: 2540, low: 2495, close: 2530, volume: 140000 },
  { time: '2026-11-12', open: 2530, high: 2560, low: 2520, close: 2555, volume: 110000 },
  { time: '2026-11-13', open: 2555, high: 2580, low: 2540, close: 2575, volume: 130000 },
  { time: '2026-11-16', open: 2575, high: 2620, low: 2570, close: 2610, volume: 150000 },
  { time: '2026-11-17', open: 2610, high: 2660, low: 2605, close: 2650, volume: 180000 },
  { time: '2026-11-18', open: 2650, high: 2670, low: 2630, close: 2640, volume: 90000 },
  { time: '2026-11-19', open: 2640, high: 2660, low: 2620, close: 2635, volume: 95000 },
  { time: '2026-11-20', open: 2635, high: 2650, low: 2610, close: 2625, volume: 85000 },
];

const MOCK_CHART_BARS_INFY = [
  { time: '2026-11-09', open: 1480, high: 1510, low: 1470, close: 1490, volume: 100000 },
  { time: '2026-11-10', open: 1490, high: 1520, low: 1485, close: 1505, volume: 120000 },
  { time: '2026-11-11', open: 1500, high: 1540, low: 1495, close: 1530, volume: 140000 },
  { time: '2026-11-12', open: 1510, high: 1530, low: 1490, close: 1515, volume: 110000 },
  { time: '2026-11-13', open: 1500, high: 1525, low: 1490, close: 1510, volume: 130000 },
  { time: '2026-11-16', open: 1490, high: 1500, low: 1460, close: 1465, volume: 150000 },
  // 2026-11-17: Gaps down at open 1400 (below stop 1450)
  { time: '2026-11-17', open: 1400, high: 1410, low: 1380, close: 1390, volume: 220000 },
  { time: '2026-11-18', open: 1390, high: 1410, low: 1380, close: 1400, volume: 120000 },
  { time: '2026-11-19', open: 1400, high: 1420, low: 1395, close: 1415, volume: 100000 },
  { time: '2026-11-20', open: 1415, high: 1430, low: 1405, close: 1420, volume: 95000 },
];

test.describe('Strategy Lab — Reusable Trade Cards & Click-to-Chart E2E', () => {
  const screenshotsDir = path.resolve('screenshots');

  test.beforeAll(() => {
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test.beforeEach(async ({ page }) => {
    // Intercept standard quote and bars APIs to prevent unhandled background calls
    await page.route('**/api/quotes*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
    });
    await page.route('**/api/bars*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ bars: MOCK_CHART_BARS, symbol: 'RELIANCE', market: 'IN' }),
      });
    });
    await page.route('**/api/lab/trades/backtest*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total: 0, items: [] }),
      });
    });
  });

  test('1. Render seeded study with Winner, Stop-out, Gap-through-stop, Time exit, and Open trade with verified chart rendering', async ({ page }) => {
    // Intercept paper trades endpoint
    await page.route('**/api/lab/trades/paper*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total: MOCK_TRADES.length,
          page: 1,
          page_size: 50,
          items: MOCK_TRADES,
        }),
      });
    });

    // Intercept chart endpoint
    await page.route('**/api/lab/trade/**/chart*', async (route) => {
      const url = route.request().url();
      let trade = MOCK_TRADES[0];
      let bars = MOCK_CHART_BARS;

      if (url.includes('/1/chart')) {
        trade = MOCK_TRADES[0];
      } else if (url.includes('/2/chart')) {
        trade = MOCK_TRADES[1];
      } else if (url.includes('/3/chart')) {
        trade = MOCK_TRADES[2];
        bars = MOCK_CHART_BARS_INFY;
      } else if (url.includes('/4/chart')) {
        trade = MOCK_TRADES[3];
      } else if (url.includes('/5/chart')) {
        trade = MOCK_TRADES[4];
      }

      const markers = [
        { date: trade.signal_date, price: trade.entry_price, type: 'SIGNAL', label: 'Signal', color: '#a78bfa' },
        { date: trade.entry_date, price: trade.entry_price, type: 'BUY', label: `Buy @ ₹${trade.entry_price}`, color: '#34d399' },
      ];
      if (trade.planned_exit_date) {
        markers.push({ date: trade.planned_exit_date, price: trade.entry_price, type: 'PLANNED_EXIT', label: 'Planned exit', color: '#fbbf24' });
      }
      if (trade.exit_date) {
        markers.push({ date: trade.exit_date, price: trade.exit_price || 0, type: 'SELL', label: trade.exit_reason || 'Exit', color: '#60a5fa' });
      }

      const segments = [];
      if (trade.stop_price && trade.entry_date) {
        segments.push({
          startDate: trade.entry_date,
          endDate: trade.exit_date || trade.planned_exit_date || '2026-11-20',
          price: trade.stop_price,
          type: 'STOP',
          color: '#ef4444',
          style: 'dashed',
        });
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: trade.symbol,
          bars,
          markers,
          segments,
          trade_info: trade,
        }),
      });
    });

    // Navigate to Strategy Lab
    await page.goto('/strategy-lab');

    // Click "Trade Cards" tab
    const cardsTab = page.getByRole('button', { name: /Trade Cards/i });
    await cardsTab.click();

    // Verify all 5 cards are displayed in main content
    const main = page.getByRole('main');
    await expect(main.getByText('RELIANCE')).toBeVisible();
    await expect(main.getByText('TCS')).toBeVisible();
    await expect(main.getByText('INFY')).toBeVisible();
    await expect(main.getByText('HDFCBANK')).toBeVisible();
    await expect(main.getByText('ICICIBANK')).toBeVisible();

    // Verify status badges
    await expect(page.getByText('WIN').first()).toBeVisible();
    await expect(page.getByText('LOSS').first()).toBeVisible();
    await expect(page.getByText('OPEN').first()).toBeVisible();

    // Verify card footers show "Data through:"
    await expect(page.getByText('Data through:').first()).toBeVisible();

    // Screenshot 1: Trade Cards List
    await page.screenshot({ path: path.join(screenshotsDir, '01_trade_cards_list.png'), fullPage: true });

    // ── Open Winner Card ──
    await main.getByText('RELIANCE').click();
    await expect(page.getByText('TRADE VIEW')).toBeVisible();

    // Explicit wait for chart-ready signal (series & markers rendered)
    const chartReady = page.locator('[data-testid="chart-ready"]');
    await expect(chartReady).toBeVisible({ timeout: 10000 });

    // Fail if loading spinner is still visible
    await expect(page.getByText('Loading 1D candlestick bars...')).not.toBeVisible();
    await expect(page.getByText('Loading trade chart…')).not.toBeVisible();

    // Fail if canvas is not attached or has 0 dimensions
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(200);
    expect(box!.height).toBeGreaterThan(200);

    // Read chart debug state from live series
    const debugState: any = await page.evaluate(() => (window as any).__chartDebug);
    expect(debugState).toBeDefined();
    expect(debugState.bars.length).toBeGreaterThan(0);
    expect(debugState.markers.length).toBe(4);

    // Assert BUY and SELL markers match fills
    const buyM = debugState.markers.find((m: any) => m.type === 'BUY');
    expect(buyM.price).toBe(2500.0);
    expect(buyM.date).toBe('2026-11-11');

    const sellM = debugState.markers.find((m: any) => m.type === 'SELL');
    expect(sellM.price).toBe(2650.0);
    expect(sellM.date).toBe('2026-11-17');

    // Screenshot 2: Winner Modal Chart (TAKEN STRICTLY AFTER chart-ready)
    await page.screenshot({ path: path.join(screenshotsDir, '02_trade_card_modal_winner.png') });
    await page.getByTitle('Close (Esc)').click();
    await expect(page.getByText('TRADE VIEW')).not.toBeVisible();

    // ── Open Gap-through-stop Card (INFY) ──
    await main.getByText('INFY').click();
    await expect(page.getByText('TRADE VIEW')).toBeVisible();

    // Explicit wait for chart-ready signal
    await expect(page.locator('[data-testid="chart-ready"]')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Loading 1D candlestick bars...')).not.toBeVisible();
    await expect(page.getByText('Loading trade chart…')).not.toBeVisible();

    // Assert gap-through-stop shows open price as fill from live debug state
    const infyDebug: any = await page.evaluate(() => (window as any).__chartDebug);
    expect(infyDebug).toBeDefined();
    const infySell = infyDebug.markers.find((m: any) => m.type === 'SELL');
    expect(infySell).toBeDefined();
    expect(infySell.price).toBe(1398.6); // Filled at open 1400 * (1 - 0.001)

    // Screenshot 3: Gap-through-stop Modal Chart (TAKEN STRICTLY AFTER chart-ready)
    await page.screenshot({ path: path.join(screenshotsDir, '03_trade_card_modal_gap_stop.png') });
    await page.getByTitle('Close (Esc)').click();
    await expect(page.getByText('TRADE VIEW')).not.toBeVisible();
  });

  test('2. Verify assertion rules from real chart series: marker counts, prices match fill, bounded segments, no weekend dates', async ({ page }) => {
    await page.route('**/api/lab/trade/paper/1/chart*', async (route) => {
      const body = {
        symbol: 'RELIANCE',
        bars: MOCK_CHART_BARS,
        markers: [
          { date: '2026-11-10', price: 2500, type: 'SIGNAL', label: 'Signal', color: '#a78bfa' },
          { date: '2026-11-11', price: 2500, type: 'BUY', label: 'Buy @ ₹2500.00', color: '#34d399' },
          { date: '2026-11-17', price: 2500, type: 'PLANNED_EXIT', label: 'Planned exit', color: '#fbbf24' },
          { date: '2026-11-17', price: 2650, type: 'SELL', label: 'TIME_EXIT', color: '#60a5fa' },
        ],
        segments: [
          { startDate: '2026-11-11', endDate: '2026-11-17', price: 2420, type: 'STOP', color: '#ef4444', style: 'dashed' },
        ],
        trade_info: MOCK_TRADES[0],
      };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.route('**/api/lab/trades/paper*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total: 1, items: [MOCK_TRADES[0]] }) });
    });

    await page.goto('/strategy-lab');
    await page.getByRole('button', { name: /Trade Cards/i }).click();
    await page.getByRole('main').getByText('RELIANCE').click();

    await expect(page.getByText('TRADE VIEW')).toBeVisible();
    await expect(page.locator('[data-testid="chart-ready"]')).toBeVisible({ timeout: 10000 });

    // Read chart series state directly from window.__chartDebug
    const chartState: any = await page.evaluate(() => (window as any).__chartDebug);
    expect(chartState).toBeDefined();

    // 1. Assert marker counts
    expect(chartState.markers.length).toBe(4);

    // 2. Assert BUY marker date and price equal trade entry_fill
    const buyMarker = chartState.markers.find((m: any) => m.type === 'BUY');
    expect(buyMarker.price).toBe(MOCK_TRADES[0].fill_price);
    expect(buyMarker.date).toBe(MOCK_TRADES[0].entry_date);

    // 3. Assert SELL marker equals exit_fill
    const sellMarker = chartState.markers.find((m: any) => m.type === 'SELL');
    expect(sellMarker.price).toBe(MOCK_TRADES[0].exit_price);
    expect(sellMarker.date).toBe(MOCK_TRADES[0].exit_date);

    // 4. Assert stop segment starts on entry bar and ends on exit bar (bounded, not full width)
    const stopSegment = chartState.segments.find((s: any) => s.type === 'STOP');
    expect(stopSegment).toBeDefined();
    expect(stopSegment.startDate).toBe('2026-11-11');
    expect(stopSegment.endDate).toBe('2026-11-17');
    expect(stopSegment.price).toBe(2420);

    // 5. Assert markers sit on bars that exist in chartBars
    for (const marker of chartState.markers) {
      const sitsOnExistingBar = chartState.bars.some((b: any) => String(b.time) === marker.date);
      expect(sitsOnExistingBar).toBe(true);
    }

    // 6. Assert NO weekend dates on markers (Mon-Fri only)
    for (const marker of chartState.markers) {
      const d = new Date(marker.date);
      const dayOfWeek = d.getUTCDay();
      expect(dayOfWeek).toBeGreaterThanOrEqual(1); // Mon=1
      expect(dayOfWeek).toBeLessThanOrEqual(5);    // Fri=5
    }
  });

  test('3. Verify Stale Data Banner and Partial Stale Notice on Paper Tab', async ({ page }) => {
    // Intercept study list and details with stale data and partial stale symbols
    await page.route('**/api/lab/study', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'study_stale_1', name: 'Forward Study — Momentum', status: 'ACTIVE', start_date: '2026-10-01', capital: 500000, kill_switch_triggered: false },
          ]),
        });
      } else {
        await route.continue();
      }
    });

    await page.route('**/api/lab/study/study_stale_1*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'study_stale_1',
          name: 'Forward Study — Momentum',
          status: 'ACTIVE',
          start_date: '2026-10-01',
          capital: 500000,
          kill_switch_triggered: false,
          data_through_date: '2026-11-18',
          last_evaluated_at: '2026-11-18T10:30:00Z',
          staleness: {
            last_data_date: '2026-11-18',
            missed_sessions: 4,
            is_stale: true,
            status: 'PARTIAL_STALE',
            stale_symbols: ['TCS'],
          },
          strategies: [{ strategy_id: 'S01', holding_days: 4 }],
          daily: [],
          holdings: [
            { symbol: 'TCS', strategy_id: 'S01', qty: 10, entry_date: '2026-11-15', entry_price: 3500.0, stop_price: 3400.0, avg_cost: 3500.0, unrealized_pnl: 0.0, is_stale_data: true },
          ],
          recent_trades: [],
          promotion_checklists: {},
          disclaimer: 'Warning: Survivorship bias',
        }),
      });
    });

    await page.goto('/strategy-lab');
    await page.getByRole('button', { name: /Paper & Manual Promotion/i }).click();

    // Verify Stale Data Notice banner is visible
    const banner = page.getByText(/Stale Market Data Notice:/i);
    await expect(banner).toBeVisible();
    await expect(page.getByText('2026-11-18').first()).toBeVisible();
    await expect(page.getByText('4 missed trading sessions')).toBeVisible();

    // Verify Partial Stale Symbol Notice is visible
    const partialNotice = page.locator('[data-testid="partial-stale-banner"]');
    await expect(partialNotice).toBeVisible();
    await expect(partialNotice.getByText('TCS')).toBeVisible();

    // Screenshot 4: Stale Data Banner
    await page.screenshot({ path: path.join(screenshotsDir, '04_stale_data_banner.png') });
  });

  test('4. Verify Empty State when no trades exist', async ({ page }) => {
    await page.route('**/api/lab/trades/paper*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total: 0, page: 1, page_size: 50, items: [] }),
      });
    });

    await page.goto('/strategy-lab');
    await page.getByRole('button', { name: /Trade Cards/i }).click();

    await expect(page.getByText('No paper trades yet')).toBeVisible();
    await expect(page.getByText('Start a study and trigger an evaluation to see trade cards here.')).toBeVisible();

    // Screenshot 5: Empty State
    await page.screenshot({ path: path.join(screenshotsDir, '05_empty_state.png') });
  });

  test('5. Verify Error State on network failure', async ({ page }) => {
    await page.route('**/api/lab/trades/paper*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Database connection failed: simulated server error' }),
      });
    });

    await page.goto('/strategy-lab');
    await page.getByRole('button', { name: /Trade Cards/i }).click();

    await expect(page.getByText(/Database connection failed/i)).toBeVisible();

    // Screenshot 6: Error State
    await page.screenshot({ path: path.join(screenshotsDir, '06_error_state.png') });
  });

  test('6. Verify backtest trade click-to-chart with verified chart-ready and debug state', async ({ page }) => {
    const mockBtTrade = {
      id: 101,
      source: 'backtest',
      strategy_id: 'S01',
      symbol: 'SBIN',
      entry_date: '2026-11-11',
      exit_date: '2026-11-17',
      signal_date: '2026-11-10',
      entry_price: 600.0,
      exit_price: 630.0,
      stop_price: 580.0,
      planned_exit_date: '2026-11-17',
      net_pnl: 1500.0,
      r_multiple: 1.5,
      exit_reason: 'TIME_EXIT',
      holding_days_target: 4,
      qty: 50,
      reason_text: 'EMA20 pullback backtest trade',
    };

    await page.route('**/api/lab/trades/backtest*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total: 1, items: [mockBtTrade] }),
      });
    });

    await page.route('**/api/lab/trades/paper*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total: 0, items: [] }),
      });
    });

    await page.route('**/api/lab/trade/backtest/101/chart*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: 'SBIN',
          bars: MOCK_CHART_BARS,
          markers: [
            { date: '2026-11-10', price: 600, type: 'SIGNAL', label: 'Signal', color: '#a78bfa' },
            { date: '2026-11-11', price: 600, type: 'BUY', label: 'Buy @ ₹600.00', color: '#34d399' },
            { date: '2026-11-17', price: 630, type: 'SELL', label: 'TIME_EXIT', color: '#60a5fa' },
          ],
          segments: [
            { startDate: '2026-11-11', endDate: '2026-11-17', price: 580, type: 'STOP', color: '#ef4444', style: 'dashed' },
          ],
          trade_info: mockBtTrade,
        }),
      });
    });

    await page.goto('/strategy-lab');
    await page.getByRole('button', { name: /Trade Cards/i }).click();

    // Select "Backtest only" source filter
    await page.locator('select').first().selectOption('backtest');

    // Wait for SBIN to appear in main
    const sbin = page.getByRole('main').getByText('SBIN');
    await expect(sbin).toBeVisible({ timeout: 5000 });
    await sbin.click();

    await expect(page.getByText('TRADE VIEW')).toBeVisible();
    await expect(page.locator('[data-testid="chart-ready"]')).toBeVisible({ timeout: 10000 });

    const debugState: any = await page.evaluate(() => (window as any).__chartDebug);
    expect(debugState).toBeDefined();
    expect(debugState.bars.length).toBe(10);
    expect(debugState.markers.length).toBe(3);

    const buy = debugState.markers.find((m: any) => m.type === 'BUY');
    expect(buy.price).toBe(600.0);
    expect(buy.date).toBe('2026-11-11');

    await page.getByTitle('Close (Esc)').click();
    await expect(page.getByText('TRADE VIEW')).not.toBeVisible();
  });
});
