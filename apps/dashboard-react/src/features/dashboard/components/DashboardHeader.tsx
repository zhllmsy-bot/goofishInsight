import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Bell, Moon, Monitor, Search, Sun, UserCircle } from 'lucide-react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../../../shared/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../shared/components/ui/select';
import { DEFAULT_QUERY_STATE, buildWorkspaceLocation } from '../lib/urlState';
import { useDashboardUiStore } from '../store/dashboardUiStore';

const THEME_KEY = 'goofish-theme-mode';
type ThemeMode = 'system' | 'light' | 'dark';

const CATEGORY_OPTIONS = [
  { label: 'Apple 电脑', value: 'apple_computer' },
  { label: 'Garmin 手表', value: 'garmin_watch' },
  { label: '相机品类', value: 'camera' },
] as const;

function isTextEditingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return tagName === 'input' || tagName === 'textarea' || tagName === 'select' || target.isContentEditable;
}

function nextTheme(current: ThemeMode): ThemeMode {
  if (current === 'system') {
    return 'light';
  }
  if (current === 'light') {
    return 'dark';
  }
  return 'system';
}

function resolveSearchTarget(raw: string, query: typeof DEFAULT_QUERY_STATE): ReturnType<typeof buildWorkspaceLocation> | string {
  const value = raw.trim();
  if (!value) {
    return buildWorkspaceLocation('/', query);
  }
  if (/^opp-[a-z0-9-]+$/i.test(value)) {
    return buildWorkspaceLocation(`/opportunity/${value}`, query);
  }
  if (/^item-[a-z0-9-]+$/i.test(value)) {
    return buildWorkspaceLocation(`/items/${value}`, query);
  }
  if (value.startsWith('/') || /^https?:\/\//i.test(value)) {
    try {
      const parsed = new URL(value, window.location.href);
      const path = parsed.pathname.replace(/\/{2,}/g, '/');
      if (path.startsWith('/opportunity/')) {
        return buildWorkspaceLocation(path, query);
      }
      if (path.startsWith('/buy/opportunities/')) {
        return buildWorkspaceLocation(`/opportunity/${path.replace('/buy/opportunities/', '')}`, query);
      }
      if (path.startsWith('/items/')) {
        return buildWorkspaceLocation(path, query);
      }
      if (path) {
        return buildWorkspaceLocation(path, query);
      }
    } catch {
      // ignore parse failures and fall back to product keyword fallback
    }
  }
  return buildWorkspaceLocation('/', {
    ...query,
    productLabel: value,
  });
}

export function DashboardHeader() {
  const query = useDashboardUiStore((state) => state.query);
  const setQuery = useDashboardUiStore((state) => state.setQuery);
  const todayOpportunityTarget = buildWorkspaceLocation('/', query);
  const marketTarget = buildWorkspaceLocation('/market', query);
  const watchTarget = buildWorkspaceLocation('/watch', query);
  const opsTarget = buildWorkspaceLocation('/ops', query);
  const agentHarnessTarget = buildWorkspaceLocation('/agent-harness', query);
  const configTarget = buildWorkspaceLocation('/config/categories', query);
  const navigate = useNavigate();
  const location = useLocation();

  const [searchDraft, setSearchDraft] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const goPrefixRef = useRef(false);
  const goPrefixTimeoutRef = useRef<number | null>(null);
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    if (typeof window === 'undefined') {
      return 'system';
    }
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored === 'system' || stored === 'light' || stored === 'dark') {
      return stored;
    }
    return 'system';
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setIsSearchOpen(true);
        return;
      }
      if (event.key === 'Escape' && isSearchOpen) {
        setIsSearchOpen(false);
        goPrefixRef.current = false;
        return;
      }
      if (isTextEditingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === 'g') {
        event.preventDefault();
        goPrefixRef.current = true;
        if (goPrefixTimeoutRef.current !== null) {
          window.clearTimeout(goPrefixTimeoutRef.current);
        }
        goPrefixTimeoutRef.current = window.setTimeout(() => {
          goPrefixRef.current = false;
          goPrefixTimeoutRef.current = null;
        }, 900);
        return;
      }
      if (goPrefixRef.current) {
        const destination = key === 'o'
          ? todayOpportunityTarget
          : key === 'm'
            ? marketTarget
            : key === 'c'
              ? configTarget
              : null;
        goPrefixRef.current = false;
        if (goPrefixTimeoutRef.current !== null) {
          window.clearTimeout(goPrefixTimeoutRef.current);
          goPrefixTimeoutRef.current = null;
        }
        if (destination) {
          event.preventDefault();
          void navigate(destination);
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      if (goPrefixTimeoutRef.current !== null) {
        window.clearTimeout(goPrefixTimeoutRef.current);
      }
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [configTarget, isSearchOpen, marketTarget, navigate, todayOpportunityTarget]);

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }
    const nextTheme = themeMode === 'system' ? 'system' : themeMode;
    document.documentElement.setAttribute('data-theme', nextTheme);
    window.localStorage.setItem(THEME_KEY, themeMode);
  }, [themeMode]);

  useEffect(() => {
    if (!isSearchOpen || !searchInputRef.current) {
      return;
    }
    searchInputRef.current.focus();
  }, [isSearchOpen]);

  const themeLabel = themeMode === 'system' ? '系统' : themeMode === 'light' ? '浅色' : '深色';
  const themeIcon = useMemo(() => {
    if (themeMode === 'light') {
      return <Sun aria-hidden="true" data-icon="inline-start" />;
    }
    if (themeMode === 'dark') {
      return <Moon aria-hidden="true" data-icon="inline-start" />;
    }
    return <Monitor aria-hidden="true" data-icon="inline-start" />;
  }, [themeMode]);

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = searchDraft.trim();
    const destination = resolveSearchTarget(trimmed || query.productLabel || '', query);
    void navigate(typeof destination === 'string' ? destination : destination);
    setSearchDraft('');
    setIsSearchOpen(false);
  }

  function handleCategoryChange(categoryCode: string) {
    const nextQuery = { ...query, categoryCode };
    setQuery(nextQuery);
    void navigate(buildWorkspaceLocation(location.pathname, nextQuery), { replace: true });
  }

  return (
    <header className="app-header">
      <div className="app-header-brand">
        <div className="app-logo">GF</div>
        <div>
          <p className="eyebrow">买方决策台</p>
          <h1>Goofish Insight</h1>
        </div>
      </div>
      <nav className="app-header-nav" aria-label="顶部导航">
        <NavLink
          aria-label="前往今日机会"
          className={({ isActive }) => `nav-pill is-action ${isActive ? 'is-active' : ''}`}
          to={todayOpportunityTarget}
        >
          今日机会
        </NavLink>
        <NavLink
          aria-label="前往市场大盘"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={marketTarget}
        >
          市场大盘
        </NavLink>
        <NavLink
          aria-label="打开关注与基线"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={watchTarget}
        >
          关注与基线
        </NavLink>
        <NavLink
          aria-label="前往运维后台"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={opsTarget}
        >
          运维后台
        </NavLink>
        <NavLink
          aria-label="打开配置后台"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={configTarget}
        >
          配置后台
        </NavLink>
        <NavLink aria-label="前往 AI 试验台" className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`} to={agentHarnessTarget}>
          AI 试验台
        </NavLink>
      </nav>
      <div className="app-header-tools" aria-label="全局工具">
        <Dialog open={isSearchOpen} onOpenChange={setIsSearchOpen}>
          <DialogTrigger asChild>
            <button
              aria-label="打开全局搜索"
              className="topbar-search-trigger"
              onClick={() => {
                setSearchDraft(query.productLabel || '');
              }}
              type="button"
            >
              <Search aria-hidden="true" data-icon="inline-start" />
              搜索
              <kbd>⌘K</kbd>
            </button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>全局搜索</DialogTitle>
              <DialogDescription>支持直接跳转机会 ID / 商品 ID / 全路径，或以关键字快速过滤今日机会。</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSearchSubmit}>
              <label className="search-dialog-label" htmlFor="global-search">
                输入关键字
              </label>
              <input
                autoComplete="off"
                autoCorrect="off"
                className="search-dialog-input"
                id="global-search"
                onChange={(event) => {
                  setSearchDraft(event.target.value);
                }}
                ref={searchInputRef}
                type="search"
                value={searchDraft}
              />
              <button className="nav-pill is-active search-dialog-submit" type="submit">
                立即跳转
              </button>
            </form>
          </DialogContent>
        </Dialog>
        <Select value={query.categoryCode} onValueChange={handleCategoryChange}>
          <SelectTrigger aria-label="品类快切" className="category-switch">
            <SelectValue placeholder="品类" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {CATEGORY_OPTIONS.map((category) => (
                <SelectItem key={category.value} value={category.value}>
                  {category.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <button aria-label="查看通知" className="icon-button" type="button">
          <Bell aria-hidden="true" data-icon="inline-start" />
        </button>
        <button aria-label="切换主题" className="icon-button theme-button" type="button" onClick={() => setThemeMode((current) => nextTheme(current))}>
          {themeIcon}
          <span>{themeLabel}</span>
        </button>
        <button aria-label="用户菜单" className="icon-button" type="button">
          <UserCircle aria-hidden="true" data-icon="inline-start" />
        </button>
      </div>
    </header>
  );
}
