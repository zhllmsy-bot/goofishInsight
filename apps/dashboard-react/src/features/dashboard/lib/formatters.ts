import { legacyDashboardLink } from '../../../shared/lib/dashboardApiConfig';
import { CATEGORY_LABELS, STATUS_LABELS } from './constants';

export function categoryLabel(code: string | undefined | null): string {
  if (!code) {
    return '全部市场';
  }
  return CATEGORY_LABELS[code] ?? code;
}

export function statusLabel(value: string | undefined | null): string {
  if (!value) {
    return '未知';
  }
  return STATUS_LABELS[value] ?? value;
}

export function formatCurrency(value: number | null | undefined): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  if (Math.abs(numeric) >= 10000) {
    return `¥${(numeric / 10000).toFixed(2)}w`;
  }
  return `¥${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(numeric)}`;
}

export function formatDeltaCurrency(value: number | null | undefined): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  return `¥${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(Math.abs(Math.round(numeric)))}`;
}

export function formatNumber(value: number | null | undefined): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(numeric);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  return `${numeric.toFixed(digits)}%`;
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const deltaSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (deltaSeconds < 60) {
    return `${deltaSeconds}秒前`;
  }
  if (deltaSeconds < 3600) {
    return `${Math.floor(deltaSeconds / 60)}分钟前`;
  }
  if (deltaSeconds < 86400) {
    return `${Math.floor(deltaSeconds / 3600)}小时前`;
  }
  return `${Math.floor(deltaSeconds / 86400)}天前`;
}

export function gaugePosition(value: number, minimum: number, maximum: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(minimum) || !Number.isFinite(maximum) || maximum <= minimum) {
    return 0;
  }

  return Math.max(0, Math.min(100, ((value - minimum) / (maximum - minimum)) * 100));
}

export function legacyLink(path: string): string {
  return legacyDashboardLink(path);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '加载失败';
}
