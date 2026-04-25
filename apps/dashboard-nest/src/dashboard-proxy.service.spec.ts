import { DashboardProxyService } from './dashboard-proxy.service';

type MockResponse = {
  ok: boolean;
  status: number;
  text: () => Promise<string>;
};

describe('DashboardProxyService', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('forwards runtime status query params to backend', async () => {
    const fetchMock = jest.fn<Promise<MockResponse>, [URL, RequestInit]>().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ ok: true }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const service = new DashboardProxyService();

    await service.forwardRuntimeStatus({
      category_code: 'apple_computer',
      pricing_scope: 'actionable',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url.toString()).toContain('/api/dashboard/runtime/status');
    expect(url.searchParams.get('category_code')).toBe('apple_computer');
    expect(url.searchParams.get('pricing_scope')).toBe('actionable');
    expect(options.method).toBe('GET');
  });

  it('serializes repeated query params and post body', async () => {
    const fetchMock = jest.fn<Promise<MockResponse>, [URL, RequestInit]>().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ ok: true }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const service = new DashboardProxyService();

    await service.forwardDashboardPath(
      '/api/buy/feedback-calibration/apply',
      {
        category_code: 'apple_computer',
        tag: ['a', 'b'],
      },
      {
        method: 'POST',
        body: { categoryCode: 'apple_computer' },
      },
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url.searchParams.get('category_code')).toBe('apple_computer');
    expect(url.searchParams.getAll('tag')).toEqual(['a', 'b']);
    expect(options.method).toBe('POST');
    expect(options.body).toBe(JSON.stringify({ categoryCode: 'apple_computer' }));
    expect(options.headers).toEqual(
      expect.objectContaining({
        Accept: 'application/json',
        'Content-Type': 'application/json',
      }),
    );
  });
});
