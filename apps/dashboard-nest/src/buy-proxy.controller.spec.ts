import { BuyProxyController } from './buy-proxy.controller';
import { DashboardProxyService } from './dashboard-proxy.service';

describe('BuyProxyController', () => {
  let controller: BuyProxyController;
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
    controller = new BuyProxyController(service);
  });

  it('forwards buy opportunities query including category scope', async () => {
    const query = { category_code: 'garmin_watch', limit: '20' };
    service.forwardDashboardPath.mockResolvedValue({ items: [] });

    const result = await controller.getOpportunities(query);

    expect(result).toEqual({ items: [] });
    expect(service.forwardDashboardPath).toHaveBeenCalledWith('/api/buy/opportunities', query);
  });

  it('forwards buy data value report query', async () => {
    const query = { category_code: 'apple_computer' };
    service.forwardDashboardPath.mockResolvedValue({ summary: { itemCount: 100 } });

    const result = await controller.getDataValue(query);

    expect(result).toEqual({ summary: { itemCount: 100 } });
    expect(service.forwardDashboardPath).toHaveBeenCalledWith('/api/buy/data-value', query);
  });

  it('forwards feedback calibration apply body and query', async () => {
    const body = { categoryCode: 'apple_computer' };
    const query = { category_code: 'apple_computer' };
    service.forwardDashboardPath.mockResolvedValue({ applied: true });

    const result = await controller.applyFeedbackCalibration(body, query);

    expect(result).toEqual({ applied: true });
    expect(service.forwardDashboardPath).toHaveBeenCalledWith(
      '/api/buy/feedback-calibration/apply',
      query,
      {
        body,
        method: 'POST',
      },
    );
  });
});
