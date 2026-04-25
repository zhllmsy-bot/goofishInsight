import { Controller, Get, Param } from '@nestjs/common';

import { DashboardProxyService } from './dashboard-proxy.service';

@Controller('api/raw-responses')
export class RawResponseProxyController {
  constructor(private readonly dashboardProxyService: DashboardProxyService) {}

  @Get(':rawResponseId')
  getRawResponse(@Param('rawResponseId') rawResponseId: string) {
    return this.dashboardProxyService.forwardDashboardPath(
      `/api/raw-responses/${encodeURIComponent(rawResponseId)}`,
    );
  }
}
