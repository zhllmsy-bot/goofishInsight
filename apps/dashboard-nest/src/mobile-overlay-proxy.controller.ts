import { Body, Controller, Get, Post } from '@nestjs/common';

import { DashboardProxyService } from './dashboard-proxy.service';

@Controller('api/mobile-overlay')
export class MobileOverlayProxyController {
  constructor(private readonly dashboardProxyService: DashboardProxyService) {}

  @Get('healthz')
  getHealthz() {
    return this.dashboardProxyService.forwardDashboardPath('/api/mobile-overlay/healthz');
  }

  @Post('analyze')
  postAnalyze(@Body() body: unknown) {
    return this.dashboardProxyService.forwardDashboardPath('/api/mobile-overlay/analyze', {}, {
      body,
      method: 'POST',
    });
  }
}
