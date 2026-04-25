import { Body, Controller, Get, Param, Post, Query } from '@nestjs/common';
import { DashboardProxyService } from './dashboard-proxy.service';

@Controller('api/dashboard')
export class DashboardProxyController {
  constructor(private readonly dashboardProxyService: DashboardProxyService) {}

  @Get('sections/:section')
  getSection(
    @Param('section') section: string,
    @Query() query: Record<string, string | string[] | undefined>,
  ) {
    return this.dashboardProxyService.forwardSection(section, query);
  }

  @Get('llm-traces/:traceKey')
  getTraceDetail(@Param('traceKey') traceKey: string) {
    return this.dashboardProxyService.forwardDashboardPath(`/api/dashboard/llm-traces/${encodeURIComponent(traceKey)}`);
  }

  @Get('runtime/status')
  getRuntimeStatus(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardRuntimeStatus(query);
  }

  @Get('agent-harness/status')
  getAgentHarnessStatus() {
    return this.dashboardProxyService.forwardAgentHarnessStatus();
  }

  @Post('runtime/actions')
  postRuntimeAction(@Body() body: unknown) {
    return this.dashboardProxyService.forwardRuntimeAction(body);
  }

  @Post('listing-preferences')
  postListingPreference(@Body() body: unknown) {
    return this.dashboardProxyService.forwardListingPreference(body);
  }

  @Get('items/:itemId')
  getItemDetail(@Param('itemId') itemId: string) {
    return this.dashboardProxyService.forwardDashboardPath(`/api/dashboard/items/${encodeURIComponent(itemId)}`);
  }
}
