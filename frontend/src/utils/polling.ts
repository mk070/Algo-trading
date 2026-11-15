/**
 * Polling and Tab Visibility Utilities for Low-Egress Client Operation
 */

export function isTabVisible(): boolean {
  if (typeof document === 'undefined') return true;
  return document.visibilityState === 'visible';
}

/**
 * Approximate client-side market hours check.
 * IN: 09:15 - 15:30 IST (UTC+5:30) Mon-Fri
 * US: 09:30 - 16:00 EST/EDT (America/New_York) Mon-Fri
 * Prevents continuous polling when markets are closed (nights, weekends).
 */
export function isMarketOpenClient(market: 'IN' | 'US'): boolean {
  const now = new Date();

  if (market === 'IN') {
    const utcMillis = now.getTime() + now.getTimezoneOffset() * 60000;
    const istDate = new Date(utcMillis + 5.5 * 3600000);
    const day = istDate.getDay();
    if (day === 0 || day === 6) return false; // Weekend
    const mins = istDate.getHours() * 60 + istDate.getMinutes();
    return mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30;
  } else if (market === 'US') {
    try {
      const nyStr = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
      const nyDate = new Date(nyStr);
      const day = nyDate.getDay();
      if (day === 0 || day === 6) return false; // Weekend
      const mins = nyDate.getHours() * 60 + nyDate.getMinutes();
      return mins >= 9 * 60 + 30 && mins <= 16 * 60;
    } catch {
      const day = now.getUTCDay();
      if (day === 0 || day === 6) return false;
      return true;
    }
  }
  return true;
}
