import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchCategoryConfigs,
  fetchTemplateConfigs,
  fetchTaskConfigs,
  upsertCategoryConfig,
  upsertTemplateConfig,
  upsertTaskConfig,
} from '../api/configApi';
import type { ConfigListFilters } from '../api/configApi';

const CONFIG_QUERY_KEY = 'config';

export function useCategoryConfigs(filters: ConfigListFilters = {}) {
  return useQuery({
    queryKey: [CONFIG_QUERY_KEY, 'categories', filters],
    queryFn: ({ signal }) => fetchCategoryConfigs(filters, signal),
  });
}

export function useTemplateConfigs(filters: ConfigListFilters = {}) {
  return useQuery({
    queryKey: [CONFIG_QUERY_KEY, 'templates', filters],
    queryFn: ({ signal }) => fetchTemplateConfigs(filters, signal),
  });
}

export function useTaskConfigs(filters: ConfigListFilters = {}) {
  return useQuery({
    queryKey: [CONFIG_QUERY_KEY, 'tasks', filters],
    queryFn: ({ signal }) => fetchTaskConfigs(filters, signal),
  });
}

export function useUpsertCategoryConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { operatorId: string; payload: Record<string, unknown>; apply: boolean }) =>
      upsertCategoryConfig(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [CONFIG_QUERY_KEY, 'categories'] });
    },
  });
}

export function useUpsertTemplateConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { operatorId: string; payload: Record<string, unknown>; apply: boolean }) =>
      upsertTemplateConfig(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [CONFIG_QUERY_KEY, 'templates'] });
    },
  });
}

export function useUpsertTaskConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { operatorId: string; payload: Record<string, unknown>; apply: boolean }) =>
      upsertTaskConfig(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [CONFIG_QUERY_KEY, 'tasks'] });
    },
  });
}
