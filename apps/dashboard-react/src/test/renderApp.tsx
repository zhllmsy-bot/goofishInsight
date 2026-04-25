import { render } from '@testing-library/react';

import App from '../App';
import { AppProviders } from '../app/providers/AppProviders';
import { DEFAULT_QUERY_STATE, readInitialQuery } from '../features/dashboard/lib/urlState';
import { useDashboardUiStore } from '../features/dashboard/store/dashboardUiStore';

export function resetDashboardStore() {
  useDashboardUiStore.setState({
    query: DEFAULT_QUERY_STATE,
    referenceTab: 'trend',
  });
}

export function renderDashboardApp(initialUrl: string) {
  window.history.replaceState({}, '', initialUrl);
  useDashboardUiStore.setState({
    query: readInitialQuery(window.location.search),
    referenceTab: 'trend',
  });
  return render(
    <AppProviders>
      <App />
    </AppProviders>,
  );
}
