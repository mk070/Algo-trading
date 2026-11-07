import {
  Activity,
  BarChart2,
  BookOpen,
  Clock,
  Compass,
  FlaskConical,
  LayoutGrid,
  LucideIcon,
  Newspaper,
  Settings,
  ShieldCheck,
} from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
}

export interface NavGroup {
  group: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    group: 'Markets',
    items: [
      { to: '/', label: 'Overview', icon: Compass },
      { to: '/watchlist', label: 'Watchlist & Live', icon: Clock },
      { to: '/heatmap', label: 'Market Heatmap', icon: LayoutGrid },
    ],
  },
  {
    group: 'Portfolio',
    items: [
      { to: '/positions', label: 'Positions & Valuation', icon: BarChart2 },
      { to: '/paper-trading', label: 'Paper Trading Lab', icon: FlaskConical },
      { to: '/journal', label: 'Journal & Stats', icon: BookOpen },
    ],
  },
  {
    group: 'Research',
    items: [
      { to: '/backtests', label: 'Backtests', icon: Activity },
      { to: '/news', label: 'News & Sentiment', icon: Newspaper },
    ],
  },
  {
    group: 'System',
    items: [
      { to: '/settings', label: 'Settings', icon: Settings },
      { to: '/system', label: 'System Health', icon: ShieldCheck },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
