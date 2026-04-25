import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { BuyProxyController } from './buy-proxy.controller';
import { ConfigProxyController } from './config-proxy.controller';
import { DashboardProxyController } from './dashboard-proxy.controller';
import { DashboardProxyService } from './dashboard-proxy.service';
import { MobileOverlayProxyController } from './mobile-overlay-proxy.controller';
import { OnboardingProxyController } from './onboarding-proxy.controller';
import { ProgressProxyController } from './progress-proxy.controller';
import { RawResponseProxyController } from './raw-response-proxy.controller';

@Module({
  imports: [],
  controllers: [
    AppController,
    DashboardProxyController,
    ProgressProxyController,
    OnboardingProxyController,
    BuyProxyController,
    ConfigProxyController,
    MobileOverlayProxyController,
    RawResponseProxyController,
  ],
  providers: [AppService, DashboardProxyService],
})
export class AppModule {}
