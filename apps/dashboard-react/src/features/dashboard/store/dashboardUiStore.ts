import { create } from 'zustand';

import { DEFAULT_QUERY_STATE, readInitialQuery } from '../lib/urlState';
import type { DashboardQueryUpdater, QueryState, ReferenceTab } from '../types/dashboard';

type DashboardUiStore = {
  query: QueryState;
  referenceTab: ReferenceTab;
  setQuery: (updater: DashboardQueryUpdater) => void;
  setReferenceTab: (tab: ReferenceTab) => void;
  resetQuery: () => void;
};

function resolveInitialQuery(): QueryState {
  return typeof window === 'undefined' ? DEFAULT_QUERY_STATE : readInitialQuery();
}

const initialQueryState = resolveInitialQuery();

export const useDashboardUiStore = create<DashboardUiStore>((set) => ({
  query: initialQueryState,
  referenceTab: 'trend',
  setQuery: (updater) =>
    set((state) => ({
      query: typeof updater === 'function' ? updater(state.query) : updater,
    })),
  setReferenceTab: (referenceTab) => set({ referenceTab }),
  resetQuery: () =>
    set({
      query: DEFAULT_QUERY_STATE,
      referenceTab: 'trend',
    }),
}));
