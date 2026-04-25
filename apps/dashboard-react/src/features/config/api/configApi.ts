import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';
import {
  categoryConfigListSchema,
  categoryConfigUpsertResultSchema,
  templateConfigListSchema,
  templateConfigDetailSchema,
  templateConfigUpsertResultSchema,
  templateConfigDiffPreviewResultSchema,
  taskConfigListSchema,
  taskConfigUpsertResultSchema,
} from './configSchemas';

export type ConfigListFilters = {
  status?: string;
  categoryCode?: string;
};

export async function fetchCategoryConfigs(filters: ConfigListFilters = {}, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/config/categories');
  if (filters.status) {
    url.searchParams.set('status', filters.status);
  }
  return categoryConfigListSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/config/categories',
      signal,
    }),
  );
}

export async function upsertCategoryConfig(
  input: {
    operatorId: string;
    payload: Record<string, unknown>;
    apply: boolean;
  },
  signal?: AbortSignal,
) {
  return categoryConfigUpsertResultSchema.parse(
    await fetchJson(dashboardApiUrl('/api/config/categories'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
      errorPrefix: 'POST /api/config/categories',
      signal,
    }),
  );
}

export async function fetchTemplateConfigs(filters: ConfigListFilters = {}, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/config/templates');
  if (filters.status) {
    url.searchParams.set('status', filters.status);
  }
  if (filters.categoryCode) {
    url.searchParams.set('category_code', filters.categoryCode);
  }
  return templateConfigListSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/config/templates',
      signal,
    }),
  );
}

export async function fetchTemplateConfigDetail(
  templateId: string,
  compareToTemplateId?: string,
  signal?: AbortSignal,
) {
  const url = dashboardApiUrl(`/api/config/templates/${encodeURIComponent(templateId)}`);
  if (compareToTemplateId) {
    url.searchParams.set('compare_to_template_id', compareToTemplateId);
  }
  return templateConfigDetailSchema.parse(
    await fetchJson(url, {
      errorPrefix: `/api/config/templates/${templateId}`,
      signal,
    }),
  );
}

export async function upsertTemplateConfig(
  input: {
    operatorId: string;
    payload: Record<string, unknown>;
    apply: boolean;
  },
  signal?: AbortSignal,
) {
  return templateConfigUpsertResultSchema.parse(
    await fetchJson(dashboardApiUrl('/api/config/templates'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
      errorPrefix: 'POST /api/config/templates',
      signal,
    }),
  );
}

export async function previewTemplateConfigDiff(
  payload: Record<string, unknown>,
  signal?: AbortSignal,
) {
  return templateConfigDiffPreviewResultSchema.parse(
    await fetchJson(dashboardApiUrl('/api/config/templates/diff-preview'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload }),
      errorPrefix: 'POST /api/config/templates/diff-preview',
      signal,
    }),
  );
}

export async function fetchTaskConfigs(filters: ConfigListFilters = {}, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/config/tasks');
  if (filters.status) {
    url.searchParams.set('status', filters.status);
  }
  if (filters.categoryCode) {
    url.searchParams.set('category_code', filters.categoryCode);
  }
  return taskConfigListSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/config/tasks',
      signal,
    }),
  );
}

export async function upsertTaskConfig(
  input: {
    operatorId: string;
    payload: Record<string, unknown>;
    apply: boolean;
  },
  signal?: AbortSignal,
) {
  return taskConfigUpsertResultSchema.parse(
    await fetchJson(dashboardApiUrl('/api/config/tasks'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
      errorPrefix: 'POST /api/config/tasks',
      signal,
    }),
  );
}
