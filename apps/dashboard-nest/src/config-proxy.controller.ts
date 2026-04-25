import { Body, Controller, Get, Param, Post, Query } from '@nestjs/common';

import { DashboardProxyService } from './dashboard-proxy.service';

@Controller('api/config')
export class ConfigProxyController {
  constructor(private readonly dashboardProxyService: DashboardProxyService) {}

  @Get('categories')
  getCategories(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/config/categories', query);
  }

  @Post('categories')
  postCategories(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/config/categories', query, {
      body,
      method: 'POST',
    });
  }

  @Get('tasks')
  getTasks(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/config/tasks', query);
  }

  @Post('tasks')
  postTasks(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/config/tasks', query, {
      body,
      method: 'POST',
    });
  }

  @Get('templates')
  getTemplates(@Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/config/templates', query);
  }

  @Post('templates')
  postTemplates(@Body() body: unknown, @Query() query: Record<string, string | string[] | undefined>) {
    return this.dashboardProxyService.forwardDashboardPath('/api/config/templates', query, {
      body,
      method: 'POST',
    });
  }

  @Get('templates/:templateId')
  getTemplateDetail(
    @Param('templateId') templateId: string,
    @Query() query: Record<string, string | string[] | undefined>,
  ) {
    return this.dashboardProxyService.forwardDashboardPath(
      `/api/config/templates/${encodeURIComponent(templateId)}`,
      query,
    );
  }

  @Post('templates/diff-preview')
  postTemplateDiffPreview(
    @Body() body: unknown,
    @Query() query: Record<string, string | string[] | undefined>,
  ) {
    return this.dashboardProxyService.forwardDashboardPath('/api/config/templates/diff-preview', query, {
      body,
      method: 'POST',
    });
  }
}
