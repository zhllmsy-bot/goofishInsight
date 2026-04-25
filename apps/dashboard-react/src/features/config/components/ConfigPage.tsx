import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { AppFrame } from '../../../shared/components/AppFrame';
import { PageHero } from '../../../shared/components/PageHero';
import { buildWorkspaceLocation } from '../../dashboard/lib/urlState';
import { useDashboardUiStore } from '../../dashboard/store/dashboardUiStore';

import '../../dashboard/styles/dashboard.css';
import '../styles/config.css';

const CONFIG_TABS = [
  { path: '/config/categories', label: '大类', description: 'Runtime、Prompt、模板绑定' },
  { path: '/config/templates', label: '模板', description: '属性编排与发布版本' },
  { path: '/config/tasks', label: '任务', description: 'Batch collect 与 query 同步' },
] as const;

const LEGACY_ADMIN_TABS = [
  { href: '/config/attributes', label: '属性池（Legacy）' },
  { href: '/config/models', label: '型号库（Legacy）' },
  { href: '/config/raw-cate-policy', label: 'Raw Cate 策略（Legacy）' },
] as const;

export function ConfigPage() {
  const query = useDashboardUiStore((state) => state.query);
  const location = useLocation();

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack config-page-shell">
            <PageHero
              eyebrow="Config Studio"
              title="配置中心"
              description="大类运行配置、模板编排和采集任务管理已收回 React 主工作台。属性池、型号库和 Raw Cate 策略保留在 Legacy 管理页，仅用于 admin/support 兼容操作。"
              meta={
                <>
                  {CONFIG_TABS.map((tab) => {
                    const isActive = location.pathname.startsWith(tab.path);
                    return (
                      <span className={`soft-pill ${isActive ? 'is-accent' : ''}`} key={tab.path}>
                        {tab.label}
                      </span>
                    );
                  })}
                </>
              }
            >
              <NavLink className="nav-pill" to={buildWorkspaceLocation('/', query)}>
                返回看板
              </NavLink>
            </PageHero>

            <nav className="config-subnav-bar" aria-label="配置中心导航">
              {CONFIG_TABS.map((tab) => (
                <NavLink
                  className={({ isActive }) =>
                    `config-subnav-tab ${isActive ? 'is-active' : ''}`
                  }
                  key={tab.path}
                  to={buildWorkspaceLocation(tab.path, query)}
                >
                  <span>{tab.label}</span>
                  <small>{tab.description}</small>
                </NavLink>
              ))}
            </nav>

            <section className="panel config-legacy-panel" aria-label="Legacy admin pages">
              <p className="eyebrow">Legacy Admin</p>
              <h3>旧模板页（仅 admin/support）</h3>
              <p className="panel-subtitle">以下页面仍由 Jinja 模板承载，不属于主运营工作台路径。</p>
              <div className="config-legacy-links">
                {LEGACY_ADMIN_TABS.map((tab) => (
                  <a className="config-legacy-link" href={tab.href} key={tab.href}>
                    {tab.label}
                  </a>
                ))}
              </div>
            </section>

            <Outlet />
          </div>
        </div>
      </main>
    </AppFrame>
  );
}
