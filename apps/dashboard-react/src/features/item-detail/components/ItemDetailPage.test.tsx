import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderDashboardApp } from '../../../test/renderApp';
import { requestUrl } from '../../../test/fetchMock';

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ItemDetailPage', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('renders item detail inside React shell and keeps workspace query', async () => {
    fetchMock.mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);

      if (url.pathname === '/api/dashboard/items/abc') {
        return jsonResponse({
          item: {
            item_id: 'abc',
            title: 'Fenix 8 Sapphire',
            business_domain: 'garmin_watch',
            categoryCode: 'garmin_watch',
            categoryName: 'Garmin手表',
            domain_label: 'Garmin手表',
            price: 5880,
            region: '上海',
            publish_time: '2026-04-18T10:00:00Z',
            first_seen_at: '2026-04-18T10:05:00Z',
            last_seen_at: '2026-04-19T01:00:00Z',
            listing_url: 'https://example.com/item/abc',
            image_urls: ['https://example.com/image.jpg'],
            condition_tags: ['箱说全'],
            normalized_brand: 'Garmin',
            normalized_model_family: 'Fenix 8',
            normalized_model: 'Fenix 8 Sapphire',
            normalized_chip: 'Garmin Gen 5',
            normalized_memory_gb: 2,
            normalized_storage_gb: 32,
            source_keyword: 'fenix 8',
            task_display_name: 'garmin_watch.main',
            raw_response_id: 'raw-1',
            has_video: true,
            is_ad: false,
          },
          spec: {
            status: 'ready',
            confidence: 0.93,
            extractor_type: 'template',
            product_line: 'Fenix',
            model_name: 'Fenix 8',
            generation: '8',
            case_size_mm: 47,
            is_solar: true,
            display_type: 'AMOLED',
            screen_size_in: 1.4,
            chip_family: 'Garmin Gen 5',
            cpu_cores: 4,
            gpu_cores: 2,
            memory_gb: 2,
            storage_gb: 32,
            edition_tags: ['Sapphire'],
            needs_review: false,
          },
          seller: {
            seller_name: '张三',
            seller_id: 'seller-1',
            region: '上海',
          },
          snapshots: [
            {
              snapshot_at: '2026-04-19T01:00:00Z',
              price: 5880,
              region: '上海',
              publish_time: '2026-04-18T10:00:00Z',
              condition_tags: [],
              extra_json: {
                page_number: 1,
                source_keyword: 'fenix 8',
              },
            },
          ],
          raw_response_body: '{"ok": true}',
        });
      }

      throw new Error(`Unexpected request: ${url.pathname}`);
    });

    renderDashboardApp(
      '/items/abc?category_code=garmin_watch&product_label=Fenix+7+Pro&spec_label=47mm&pricing_scope=actionable&pricing_freshness_days=60',
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Fenix 8 Sapphire' })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: '返回看板' })).toHaveAttribute(
      'href',
      expect.stringContaining('product_label=Fenix+7+Pro'),
    );
    expect(screen.getByText('商品信息')).toBeInTheDocument();
    expect(screen.getByText('卖家与快照')).toBeInTheDocument();
  });
});
