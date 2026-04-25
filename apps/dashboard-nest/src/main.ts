import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AppModule } from './app.module';
import { AppService } from './app.service';

async function bootstrap() {
  const app = await NestFactory.create<NestExpressApplication>(AppModule);
  const appService = app.get(AppService);

  app.useStaticAssets(appService.frontendDistPath);
  await app.listen(process.env.PORT ?? 3000);
}
bootstrap();
