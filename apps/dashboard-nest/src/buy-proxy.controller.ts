import { Body, Controller, Get, Param, Post, Query } from '@nestjs/common';
import { DashboardProxyService } from './dashboard-proxy.service';

@Controller('api/buy')
export class BuyProxyController {
  constructor(private readonly dashboardProxyService: DashboardProxyService) {}

  @Get('opportunities')
  getOpportunities(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/opportunities', query);
  }

  @Get('data-value')
  getDataValue(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/data-value', query);
  }

  @Get('targets')
  getTargets(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/targets', query);
  }

  @Get('baselines')
  getBaselines(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/baselines', query);
  }

  @Get('opportunities/:opportunityId')
  getOpportunityDetail(
    @Param('opportunityId') opportunityId: string,
    @Query() query: Record<string, string | string[] | undefined>,
  ) {
    return this.dashboardProxyService.forwardDashboardPath(
      `/api/buy/opportunities/${encodeURIComponent(opportunityId)}`,
      query,
    );
  }

  @Post('feedback')
  postFeedback(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/feedback', query, {
      body,
      method: 'POST',
    });
  }

  @Get('feedback-quality')
  getFeedbackQuality(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/feedback-quality', query);
  }

  @Get('feedback-calibration')
  getFeedbackCalibration(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/feedback-calibration', query);
  }

  @Post('feedback-calibration/apply')
  applyFeedbackCalibration(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/feedback-calibration/apply', query, {
      body,
      method: 'POST',
    });
  }

  @Get('template-monitoring')
  getTemplateMonitoring(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/buy/template-monitoring', query);
  }
}
