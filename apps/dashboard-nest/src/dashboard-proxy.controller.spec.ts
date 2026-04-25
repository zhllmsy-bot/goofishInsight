import { DashboardProxyController } from './dashboard-proxy.controller';
import { DashboardProxyService } from './dashboard-proxy.service';

describe('DashboardProxyController', () => {
  let controller: DashboardProxyController;
  let service: jest.Mocked<DashboardProxyService>;

  beforeEach(() => {
    service = {
      forwardSection: jest.fn(),
      forwardRuntimeStatus: jest.fn(),
      forwardAgentHarnessStatus: jest.fn(),
      forwardRuntimeAction: jest.fn(),
      forwardListingPreference: jest.fn(),
      forwardProgressSection: jest.fn(),
      forwardDashboardPath: jest.fn(),
    } as unknown as jest.Mocked<DashboardProxyService>;
    controller = new DashboardProxyController(service);
  });

  it('forwards runtime status query including category scope', async () => {
    const query = { category_code: 'apple_computer', pricing_scope: 'actionable' };
    service.forwardRuntimeStatus.mockResolvedValue({ ok: true });

    const result = await controller.getRuntimeStatus(query);

    expect(result).toEqual({ ok: true });
    expect(service.forwardRuntimeStatus).toHaveBeenCalledWith(query);
  });

  it('forwards runtime action body unchanged', async () => {
    const body = {
      target: 'buy_jobs',
      action: 'build-buy-baselines',
      categoryCode: 'apple_computer',
    };
    service.forwardRuntimeAction.mockResolvedValue({ ok: true });

    const result = await controller.postRuntimeAction(body);

    expect(result).toEqual({ ok: true });
    expect(service.forwardRuntimeAction).toHaveBeenCalledWith(body);
  });
});
