import { useMemo, type PropsWithChildren } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { useQueryErrorResetBoundary } from '@tanstack/react-query';

import { AppErrorBoundary } from '../shared/components/AppErrorBoundary';
import { RouteErrorState } from '../shared/components/RouteErrorState';
import { BuyBaselinesPage } from '../features/buy/components/BuyBaselinesPage';
import { BuyTargetsPage } from '../features/buy/components/BuyTargetsPage';
import { BuyOpportunityDetailPage } from '../features/buy/components/BuyOpportunityDetailPage';
import { BuyWorkbenchPage } from '../features/buy/components/BuyWorkbenchPage';
import { DashboardPage } from '../features/dashboard/components/DashboardPage';
import { buildWorkspaceLocation, readInitialQuery } from '../features/dashboard/lib/urlState';
import { AgentHarnessPage } from '../features/agent-harness/components/AgentHarnessPage';
import { CategoriesConfigPanel } from '../features/config/components/CategoriesConfigPanel';
import { ConfigPage } from '../features/config/components/ConfigPage';
import { TasksConfigPanel } from '../features/config/components/TasksConfigPanel';
import { TemplatesConfigPanel } from '../features/config/components/TemplatesConfigPanel';
import { ItemDetailPage } from '../features/item-detail/components/ItemDetailPage';
import { LlmOpsPage } from '../features/llm-ops/components/LlmOpsPage';
import { MobileOverlayPage } from '../features/mobile-overlay/components/MobileOverlayPage';
import { OnboardingPage } from '../features/onboarding/components/OnboardingPage';
import { ProgressPage } from '../features/progress/components/ProgressPage';
import { RuntimePage } from '../features/runtime/components/RuntimePage';

const ROUTE_LABELS: Record<string, string> = {
  '/': '证据看板',
  '/llm-devops': 'LLM DevOps',
  '/llm-ops': 'LLM DevOps',
  '/runtime': '运行后台',
  '/agent-harness': 'Agent Harness',
  '/buy/opportunities': '机会队列',
  '/buy/targets': '买入目标',
  '/buy/baselines': '价格基线',
  '/progress': '回刷进度',
  '/items': '商品详情',
  '/onboarding/xianyu': '品类开通',
  '/mobile-overlay': '移动端校准',
  '/config/categories': '配置后台',
  '/config/templates': '配置后台',
  '/config/tasks': '配置后台',
  '/config/attributes': 'Legacy 配置页',
  '/config/models': 'Legacy 配置页',
  '/config/raw-cate-policy': 'Legacy 配置页',
};

const DYNAMIC_ROUTE_LABELS = [
  ['/items/', '商品详情'],
  ['/buy/opportunities/', '机会详情'],
  ['/buy/targets/', '目标列表'],
  ['/buy/baselines/', '基线列表'],
] as const;

export default function App() {
  return (
    <BrowserRouter>
      <RouteRecoveryBoundary>
        <Routes>
          <Route element={<DashboardPage />} path="/" />
          <Route element={<RouteRedirect pathname="/llm-devops" />} path="/llm-ops" />
          <Route element={<LlmOpsPage />} path="/llm-devops" />
          <Route element={<RuntimePage />} path="/runtime" />
          <Route element={<AgentHarnessPage />} path="/agent-harness" />
          <Route element={<BuyWorkbenchPage />} path="/buy/opportunities" />
          <Route element={<BuyOpportunityDetailPage />} path="/buy/opportunities/:opportunityId" />
          <Route element={<BuyTargetsPage />} path="/buy/targets" />
          <Route element={<BuyBaselinesPage />} path="/buy/baselines" />
          <Route element={<ProgressPage />} path="/progress" />
          <Route element={<ItemDetailPage />} path="/items/:itemId" />
          <Route element={<OnboardingPage />} path="/onboarding/xianyu" />
          <Route element={<MobileOverlayPage />} path="/mobile-overlay" />
          <Route element={<ConfigPage />} path="/config">
            <Route element={<RouteRedirect pathname="/config/categories" />} index />
            <Route element={<CategoriesConfigPanel />} path="categories" />
            <Route element={<TemplatesConfigPanel />} path="templates" />
            <Route element={<TasksConfigPanel />} path="tasks" />
          </Route>
          <Route element={<RouteRedirect pathname="/" />} path="*" />
        </Routes>
      </RouteRecoveryBoundary>
    </BrowserRouter>
  );
}

function RouteRedirect(props: { pathname: string }) {
  const location = useLocation();
  const query = readInitialQuery(location.search);
  return <Navigate replace to={buildWorkspaceLocation(props.pathname, query)} />;
}

function RouteRecoveryBoundary(props: PropsWithChildren) {
  const location = useLocation();
  const navigate = useNavigate();
  const { reset } = useQueryErrorResetBoundary();
  const routeKey = `${location.pathname}${location.search}`;
  const routeLabel = useMemo(
    () => resolveRouteLabel(location.pathname),
    [location.pathname],
  );
  const preservedQuery = useMemo(() => readInitialQuery(location.search), [location.search]);
  const dashboardTarget = useMemo(
    () => buildWorkspaceLocation('/', preservedQuery),
    [preservedQuery],
  );
  const runtimeTarget = useMemo(
    () => buildWorkspaceLocation('/runtime', preservedQuery),
    [preservedQuery],
  );

  return (
    <AppErrorBoundary
      resetKeys={[routeKey]}
      onError={(error, errorInfo) => {
        console.error('Dashboard route boundary caught an error', {
          pathname: location.pathname,
          error,
          errorInfo,
        });
      }}
      fallback={({ error, reset: resetBoundary }) => (
        <RouteErrorState
          error={error}
          routeLabel={routeLabel}
          onGoHome={() => {
            reset();
            resetBoundary();
            navigate(dashboardTarget, { replace: true });
          }}
          onReload={() => {
            window.location.reload();
          }}
          onRetry={() => {
            reset();
            resetBoundary();
          }}
          onViewRuntime={() => {
            reset();
            resetBoundary();
            navigate(runtimeTarget, { replace: true });
          }}
        />
      )}
    >
      {props.children}
    </AppErrorBoundary>
  );
}

function resolveRouteLabel(pathname: string) {
  if (ROUTE_LABELS[pathname]) {
    return ROUTE_LABELS[pathname];
  }
  const dynamicMatch = DYNAMIC_ROUTE_LABELS.find(([prefix]) => pathname.startsWith(prefix));
  return dynamicMatch?.[1] ?? '当前路由';
}
