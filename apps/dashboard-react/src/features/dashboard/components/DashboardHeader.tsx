import { NavLink } from 'react-router-dom';

import { buildWorkspaceLocation } from '../lib/urlState';
import { useDashboardUiStore } from '../store/dashboardUiStore';

export function DashboardHeader() {
  const query = useDashboardUiStore((state) => state.query);
  const dashboardTarget = buildWorkspaceLocation('/', query);
  const llmOpsTarget = buildWorkspaceLocation('/llm-devops', query);
  const runtimeTarget = buildWorkspaceLocation('/runtime', query);
  const agentHarnessTarget = buildWorkspaceLocation('/agent-harness', query);
  const buyWorkbenchTarget = buildWorkspaceLocation('/buy/opportunities', query);
  const buyTargetsTarget = buildWorkspaceLocation('/buy/targets', query);
  const buyBaselinesTarget = buildWorkspaceLocation('/buy/baselines', query);
  const progressTarget = buildWorkspaceLocation('/progress', query);
  const onboardingTarget = buildWorkspaceLocation('/onboarding/xianyu', query);
  const configTarget = buildWorkspaceLocation('/config/categories', query);
  const mobileOverlayTarget = buildWorkspaceLocation('/mobile-overlay', query);

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
          aria-label="打开机会队列"
          className={({ isActive }) => `nav-pill is-action ${isActive ? 'is-active' : ''}`}
          to={buyWorkbenchTarget}
        >
          机会队列
        </NavLink>
        <NavLink
          aria-label="打开买入目标页"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={buyTargetsTarget}
        >
          买入目标
        </NavLink>
        <NavLink
          aria-label="打开价格基线页"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={buyBaselinesTarget}
        >
          价格基线
        </NavLink>
        <NavLink
          aria-label="前往证据看板"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={dashboardTarget}
        >
          证据看板
        </NavLink>
        <NavLink
          aria-label="前往运行后台"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={runtimeTarget}
        >
          运行后台
        </NavLink>
        <NavLink
          aria-label="打开配置后台"
          className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`}
          to={configTarget}
        >
          配置后台
        </NavLink>
        <NavLink aria-label="打开回刷进度" className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`} to={progressTarget}>
          回刷进度
        </NavLink>
        <NavLink aria-label="打开品类开通" className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`} to={onboardingTarget}>
          品类开通
        </NavLink>
        <NavLink aria-label="打开移动端校准" className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`} to={mobileOverlayTarget}>
          移动端校准
        </NavLink>
        <NavLink aria-label="前往 LLM DevOps" className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`} to={llmOpsTarget}>
          LLM DevOps
        </NavLink>
        <NavLink aria-label="前往 Agent Harness" className={({ isActive }) => `nav-pill ${isActive ? 'is-active' : ''}`} to={agentHarnessTarget}>
          Agent Harness
        </NavLink>
      </nav>
    </header>
  );
}
