import { Controller, Get, Param, Query } from '@nestjs/common';

import { DashboardProxyService } from './dashboard-proxy.service';

@Controller('api/progress')
export class ProgressProxyController {
  constructor(private readonly dashboardProxyService: DashboardProxyService) {}

  @Get('sections/:section')
  getSection(
    @Param('section') section: string,
    @Query() query: Record<string, string | string[] | undefined>,
  ) {
    return this.dashboardProxyService.forwardProgressSection(section, query);
  }
}
