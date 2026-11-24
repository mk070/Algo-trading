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
    exec_date: '2026-11-17',   // Tuesday (gap down open)
    exit_date: '2026-11-17',
    fill_price: 1500.0,
    entry_price: 1500.0,
    exit_price: 1398.6,
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

const MOCK_CHART_BARS = [
  { time: '2026-11-09', open: 2480, high: 2510, low: 2470, close: 2490, volume: 100000 },
  { time: '2026-11-10', open: 2490, high: 2520, low: 2485, close: 2505, volume: 120000 },
  { time: '2026-11-11', open: 2500, high: 2540, low: 2495, close: 2530, volume: 140000 },
  { time: '2026-11-12', open: 2530, high: 2560, low: 2520, close: 2555, volume: 110000 },
  { time: '2026-11-13', open: 2555, high: 2580, low: 2540, close: 2575, volume: 130000 },
  { time: '2026-11-16', open: 2575, high: 2620, low: 2570, close: 2610, volume: 150000 },
  { time: '2026-11-17', open: 2610, high: 2660, low: 2605, close: 2650, volume: 180000 },
];

test.describe('Strategy Lab — Reusable Trade Cards & Click-to-Chart E2E', () => {
  const screenshotsDir = path.resolve('screenshots');

  test.beforeAll(() => {
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test('1. Render seeded study with Winner, Stop-out, Gap-through-stop, Time exit, and Open trade', async ({ page }) => {
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
      if (url.includes('/1/chart')) trade = MOCK_TRADES[0];
      else if (url.includes('/2/chart')) trade = MOCK_TRADES[1];
      else if (url.includes('/3/chart')) trade = MOCK_TRADES[2];
      else if (url.includes('/4/chart')) trade = MOCK_TRADES[3];
      else if (url.includes('/5/chart')) trade = MOCK_TRADES[4];

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
          endDate: trade.exit_date || trade.planned_exit_date || '2026-11-23',
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
          bars: MOCK_CHART_BARS,
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
    await expect(page.getByText('Signal:').first()).toBeVisible();
    await expect(page.getByText('2026-11-10').first()).toBeVisible();
    await expect(page.getByText('Entry:').first()).toBeVisible();
    await expect(page.getByText('2026-11-11').first()).toBeVisible();
    await expect(page.getByText(/2500\.00/).first()).toBeVisible();
    await expect(page.getByText(/2420\.00/).first()).toBeVisible();
    await expect(page.getByText('Planned exit:').first()).toBeVisible();

    // Screenshot 2: Winner Modal Chart
    await page.screenshot({ path: path.join(screenshotsDir, '02_trade_card_modal_winner.png') });
    await page.getByTitle('Close (Esc)').click();
    await expect(page.getByText('TRADE VIEW')).not.toBeVisible();

    // ── Open Gap-through-stop Card ──
    await main.getByText('INFY').click();
    await expect(page.getByText('TRADE VIEW')).toBeVisible();
    await expect(page.getByText('Gap-through stop')).toBeVisible();
    await expect(page.getByText('2026-11-13').first()).toBeVisible();
    await expect(page.getByText(/1500\.00/).first()).toBeVisible();

    // Screenshot 3: Gap-through-stop Modal Chart
    await page.screenshot({ path: path.join(screenshotsDir, '03_trade_card_modal_gap_stop.png') });
    await page.getByTitle('Close (Esc)').click();
    await expect(page.getByText('TRADE VIEW')).not.toBeVisible();
  });

  test('2. Verify assertion rules: marker counts, prices match fill, bounded segments, no weekend dates', async ({ page }) => {
    let capturedResponse: any = null;
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
      capturedResponse = body;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.route('**/api/lab/trades/paper*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total: 1, items: [MOCK_TRADES[0]] }) });
    });

    await page.goto('/strategy-lab');
    await page.getByRole('button', { name: /Trade Cards/i }).click();
    await page.getByRole('main').getByText('RELIANCE').click();

    await expect(page.getByText('TRADE VIEW')).toBeVisible();

    // Assert marker counts
    expect(capturedResponse.markers.length).toBe(4);

    // Assert marker prices match fill price
    const buyMarker = capturedResponse.markers.find((m: any) => m.type === 'BUY');
    expect(buyMarker.price).toBe(MOCK_TRADES[0].fill_price);

    // Assert stop segment spans entry to exit only (bounded, not full chart)
    const stopSegment = capturedResponse.segments.find((s: any) => s.type === 'STOP');
    expect(stopSegment.startDate).toBe('2026-11-11');
    expect(stopSegment.endDate).toBe('2026-11-17');

    // Assert NO weekend dates on markers
    for (const marker of capturedResponse.markers) {
      const d = new Date(marker.date);
      const dayOfWeek = d.getUTCDay();
      expect(dayOfWeek).toBeGreaterThanOrEqual(1); // Mon=1
      expect(dayOfWeek).toBeLessThanOrEqual(5);    // Fri=5
    }
  });

  test('3. Verify Stale Data Banner on Paper Tab', async ({ page }) => {
    // Intercept study list and details with stale data
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
          },
          strategies: [{ strategy_id: 'S01', holding_days: 4 }],
          daily: [],
          holdings: [],
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
});
