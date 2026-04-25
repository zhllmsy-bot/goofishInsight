import { Link, Outlet, useLocation } from 'react-router-dom';

import { PageHero } from '../../../shared/components/PageHero';
import { AppFrame } from '../../../shared/components/AppFrame';
import { buildWorkspaceLocation } from '../../dashboard/lib/urlState';
import { useDashboardUiStore } from '../../dashboard/store/dashboardUiStore';

type OpsTab = {
  key: 'runtime' | 'llm-devops' | 'progress';
  label: string;
  description: string;
};

const OPS_TABS: OpsTab[] = [
  {
    key: 'runtime',
    label: '运行时任务',
    description: '检查采集、模型和任务运行健康度，支持一键重启与日志追踪。',
  },
  {
    key: 'llm-devops',
    label: 'LLM DevOps',
    description: '查看调用链路、Token 消耗与 trace 明细。',
  },
  {
    key: 'progress',
    label: '回刷进度',
    description: '追踪 review、second-pass 与使用量指标。',
  },
];

export function OpsWorkbenchPage() {
  const location = useLocation();
  const query = useDashboardUiStore((state) => state.query);
  const dashboardTarget = buildWorkspaceLocation('/', query);

  const activeTab = location.pathname.endsWith('/llm-devops')
    ? 'llm-devops'
    : location.pathname.endsWith('/progress')
      ? 'progress'
      : 'runtime';

  const activeTabDescription = OPS_TABS.find((tab) => tab.key === activeTab)?.description ?? OPS_TABS[0].description;

  return (
    <AppFrame>
      <main className="workspace">
        <div className="workspace-scroll">
          <div className="page-stack">
            <PageHero
              eyebrow="Ops"
              title="运维后台"
              description="把运行、LLM 与回刷进度放到同一个入口，保留上下文并减少跳转成本。"
              meta={
                <>
                  <span className="soft-pill">模块 {activeTab}</span>
                  <span className="soft-pill">保留查询上下文</span>
                </>
              }
            >
              <Link className="nav-pill" to={dashboardTarget}>
                回到机会台
              </Link>
              {OPS_TABS.map((tab) => (
                <Link
                  aria-label={`切换到 ${tab.label}`}
                  className={`nav-pill ${activeTab === tab.key ? 'is-active' : ''}`}
                  key={tab.key}
                  to={buildWorkspaceLocation(`/ops/${tab.key}`, query)}
                >
                  {tab.label}
                </Link>
              ))}
            </PageHero>

            <section className="panel">
              <p className="panel-subtitle">{activeTabDescription}</p>
            </section>

            <Outlet />
          </div>
        </div>
      </main>
    </AppFrame>
  );
}
