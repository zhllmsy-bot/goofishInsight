import { Body, Controller, Get, Param, Post, Query } from '@nestjs/common';
import { DashboardProxyService } from './dashboard-proxy.service';

@Controller('api/onboarding')
export class OnboardingProxyController {
  constructor(private readonly dashboardProxyService: DashboardProxyService) {}

  @Get('xianyu/coverage')
  getXianyuCoverage(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/onboarding/xianyu/coverage', query);
  }

  @Get('xianyu/queue')
  getXianyuQueue(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/onboarding/xianyu/queue', query);
  }

  @Post('xianyu/queue/sync')
  postXianyuQueueSync(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/onboarding/xianyu/queue/sync', query, {
      body,
      method: 'POST',
    });
  }

  @Post('xianyu/queue/status')
  postXianyuQueueStatus(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/onboarding/xianyu/queue/status', query, {
      body,
      method: 'POST',
    });
  }

  @Post('xianyu/discovery')
  postXianyuDiscovery(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/onboarding/xianyu/discovery', query, {
      body,
      method: 'POST',
    });
  }

  @Post('xianyu/draft')
  postXianyuDraft(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/onboarding/xianyu/draft', query, {
      body,
      method: 'POST',
    });
  }

  @Post('xianyu/persist')
  postXianyuPersist(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/onboarding/xianyu/persist', query, {
      body,
      method: 'POST',
    });
  }
}
