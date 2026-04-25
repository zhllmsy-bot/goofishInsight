import { Injectable } from '@nestjs/common';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

@Injectable()
export class AppService {
  readonly frontendDistPath = join(__dirname, '..', '..', 'dashboard-react', 'dist');
  readonly frontendIndexPath = join(this.frontendDistPath, 'index.html');

  getHealth() {
    return {
      ok: true,
      frontendReady: existsSync(this.frontendIndexPath),
    };
  }
}
