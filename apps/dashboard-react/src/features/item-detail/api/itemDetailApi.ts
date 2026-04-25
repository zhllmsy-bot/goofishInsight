import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';
import { itemDetailSchema } from './itemDetailSchemas';

export async function fetchItemDetail(itemId: string, signal?: AbortSignal) {
  return itemDetailSchema.parse(
    await fetchJson(dashboardApiUrl(`/api/dashboard/items/${encodeURIComponent(itemId)}`), {
      errorPrefix: `/api/dashboard/items/${itemId}`,
      signal,
    }),
  );
}

export function itemDetailQueryKey(itemId: string) {
  return ['item-detail', itemId] as const;
}
