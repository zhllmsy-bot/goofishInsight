import type { ListingDecision } from '../types/dashboard';

export const CATEGORY_LABELS: Record<string, string> = {
  apple_computer: 'Apple电脑',
  camera_body: '相机机身',
  camera_interchangeable_lens: '可换镜头',
  garmin_watch: 'Garmin手表',
};

export const STATUS_LABELS: Record<string, string> = {
  completed: '完成',
  running: '运行中',
  failed: '失败',
  pending: '等待中',
  authenticated: '已登录',
  login_required: '需要登录',
};

export const LISTING_SECTION_META: Record<
  ListingDecision['kind'],
  { title: string; badge: string; max: number }
> = {
  buy: { title: '低于安全收货价', badge: '低价机会', max: 6 },
  watch: { title: '进入正常收货线', badge: '可谈标的', max: 6 },
  market: { title: '贴近市场中位价', badge: '观察标的', max: 4 },
  high: { title: '高于正常收货线', badge: '暂缓', max: 4 },
  neutral: { title: '最新挂牌', badge: '最新', max: 8 },
};

export const DASHBOARD_QUERY_STALE_TIME = 30_000;
export const SIDEBAR_QUERY_STALE_TIME = 5 * 60_000;
