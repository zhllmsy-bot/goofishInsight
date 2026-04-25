import { Controller, Get, Res } from '@nestjs/common';
import { existsSync } from 'node:fs';
import type { Response } from 'express';
import { AppService } from './app.service';

@Controller()
export class AppController {
  constructor(private readonly appService: AppService) {}

  @Get('healthz')
  getHealth() {
    return this.appService.getHealth();
  }

  @Get([
    '',
    'llm-ops',
    'llm-devops',
    'runtime',
    'buy/opportunities',
    'buy/targets',
    'buy/baselines',
    'agent-harness',
    'progress',
    'onboarding/xianyu',
    'mobile-overlay',
    'config',
    'config/categories',
    'config/templates',
    'config/tasks',
  ])
  getIndex(@Res() response: Response) {
    if (!existsSync(this.appService.frontendIndexPath)) {
      return response.status(503).send('React build missing. Run "npm run build -w dashboard-react" first.');
    }

    return response.sendFile(this.appService.frontendIndexPath);
  }

  @Get('items/:itemId')
  getItemDetail(@Res() response: Response) {
    if (!existsSync(this.appService.frontendIndexPath)) {
      return response.status(503).send('React build missing. Run "npm run build -w dashboard-react" first.');
    }

    return response.sendFile(this.appService.frontendIndexPath);
  }

  @Get('buy/opportunities/:opportunityId')
  getBuyOpportunityDetail(@Res() response: Response) {
    if (!existsSync(this.appService.frontendIndexPath)) {
      return response.status(503).send('React build missing. Run "npm run build -w dashboard-react" first.');
    }

    return response.sendFile(this.appService.frontendIndexPath);
  }

  @Get('buy/targets')
  getBuyTargets(@Res() response: Response) {
    if (!existsSync(this.appService.frontendIndexPath)) {
      return response.status(503).send('React build missing. Run "npm run build -w dashboard-react" first.');
    }

    return response.sendFile(this.appService.frontendIndexPath);
  }

  @Get('buy/baselines')
  getBuyBaselines(@Res() response: Response) {
    if (!existsSync(this.appService.frontendIndexPath)) {
      return response.status(503).send('React build missing. Run "npm run build -w dashboard-react" first.');
    }

    return response.sendFile(this.appService.frontendIndexPath);
  }
}
