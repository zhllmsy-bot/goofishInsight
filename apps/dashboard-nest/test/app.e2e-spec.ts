import { INestApplication } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { App } from 'supertest/types';
import { AppModule } from './../src/app.module';

describe('AppController (e2e)', () => {
  let app: INestApplication<App>;

  beforeEach(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  it('/healthz (GET)', () => {
    return request(app.getHttpServer()).get('/healthz').expect(200);
  });

  it('/ (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/').expect(200).expect('Content-Type', /html/);
  });

  it('/items/:id (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/items/abc123').expect(200).expect('Content-Type', /html/);
  });

  it('/buy/opportunities (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/buy/opportunities').expect(200).expect('Content-Type', /html/);
  });

  it('/buy/opportunities/:id (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/buy/opportunities/opp-1').expect(200).expect('Content-Type', /html/);
  });

  it('/buy/targets (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/buy/targets').expect(200).expect('Content-Type', /html/);
  });

  it('/buy/baselines (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/buy/baselines').expect(200).expect('Content-Type', /html/);
  });

  it('/runtime (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/runtime').expect(200).expect('Content-Type', /html/);
  });

  it('/onboarding/xianyu (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/onboarding/xianyu').expect(200).expect('Content-Type', /html/);
  });

  it('/progress (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/progress').expect(200).expect('Content-Type', /html/);
  });

  it('/config/categories (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/config/categories').expect(200).expect('Content-Type', /html/);
  });

  it('/config/templates (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/config/templates').expect(200).expect('Content-Type', /html/);
  });

  it('/config/tasks (GET) should return React shell', () => {
    return request(app.getHttpServer()).get('/config/tasks').expect(200).expect('Content-Type', /html/);
  });

  it('/api/dashboard/runtime/status (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/dashboard/runtime/status').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/onboarding/xianyu/coverage (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/onboarding/xianyu/coverage?source_keyword=test').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/onboarding/xianyu/queue (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/onboarding/xianyu/queue').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/onboarding/xianyu/discovery (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/onboarding/xianyu/discovery')
      .send({ source_keyword: 'garmin' })
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/onboarding/xianyu/queue/sync (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/onboarding/xianyu/queue/sync')
      .send({})
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/onboarding/xianyu/queue/status (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/onboarding/xianyu/queue/status')
      .send({})
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/onboarding/xianyu/draft (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/onboarding/xianyu/draft')
      .send({})
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/onboarding/xianyu/persist (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/onboarding/xianyu/persist')
      .send({})
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/buy/opportunities (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/buy/opportunities').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/buy/opportunities/:id (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/buy/opportunities/opp-1').expect((res) => {
      if (res.status !== 200 && res.status !== 404 && res.status !== 504) {
        throw new Error(`Expected 200, 404 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/buy/targets (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/buy/targets').expect((res) => {
      if (res.status !== 200 && res.status !== 404 && res.status !== 504) {
        throw new Error(`Expected 200, 404 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/buy/baselines (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/buy/baselines').expect((res) => {
      if (res.status !== 200 && res.status !== 404 && res.status !== 504) {
        throw new Error(`Expected 200, 404 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/buy/feedback (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/buy/feedback')
      .send({})
      .expect((res) => {
        if (
          res.status !== 200 &&
          res.status !== 201 &&
          res.status !== 400 &&
          res.status !== 422 &&
          res.status !== 504
        ) {
          throw new Error(`Expected 200, 201, 400, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/buy/feedback-calibration/apply (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/buy/feedback-calibration/apply')
      .send({ categoryCode: 'apple_computer' })
      .expect((res) => {
        if (
          res.status !== 200 &&
          res.status !== 201 &&
          res.status !== 400 &&
          res.status !== 422 &&
          res.status !== 504
        ) {
          throw new Error(`Expected 200, 201, 400, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/config/categories (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/config/categories').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/config/templates (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/config/templates').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/config/tasks (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/config/tasks').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/config/categories (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/config/categories')
      .send({})
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/config/templates/:id (GET) should proxy to backend', () => {
    return request(app.getHttpServer())
      .get('/api/config/templates/template-1')
      .expect((res) => {
        if (res.status !== 200 && res.status !== 404 && res.status !== 500 && res.status !== 504) {
          throw new Error(`Expected 200, 404, 500 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/config/templates (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/config/templates')
      .send({})
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/config/templates/diff-preview (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/config/templates/diff-preview')
      .send({ payload: {} })
      .expect((res) => {
        if (
          res.status !== 200 &&
          res.status !== 201 &&
          res.status !== 400 &&
          res.status !== 422 &&
          res.status !== 504
        ) {
          throw new Error(`Expected 200, 201, 400, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/config/tasks (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/config/tasks')
      .send({})
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/mobile-overlay/healthz (GET) should proxy to backend', () => {
    return request(app.getHttpServer()).get('/api/mobile-overlay/healthz').expect((res) => {
      if (res.status !== 200 && res.status !== 504) {
        throw new Error(`Expected 200 or 504, got ${res.status}`);
      }
    });
  });

  it('/api/mobile-overlay/analyze (POST) should proxy to backend', () => {
    return request(app.getHttpServer())
      .post('/api/mobile-overlay/analyze')
      .send({ ocr_lines: [] })
      .expect((res) => {
        if (res.status !== 200 && res.status !== 201 && res.status !== 422 && res.status !== 504) {
          throw new Error(`Expected 200, 201, 422 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/raw-responses/:id (GET) should proxy to backend', () => {
    return request(app.getHttpServer())
      .get('/api/raw-responses/00000000-0000-0000-0000-000000000000')
      .expect((res) => {
        if (res.status !== 200 && res.status !== 404 && res.status !== 504) {
          throw new Error(`Expected 200, 404 or 504, got ${res.status}`);
        }
      });
  });

  it('/api/dashboard/items/:id (GET) should proxy to backend', () => {
    return request(app.getHttpServer())
      .get('/api/dashboard/items/abc123')
      .expect((res) => {
        if (res.status !== 200 && res.status !== 401 && res.status !== 404 && res.status !== 504) {
          throw new Error(`Expected 200, 401, 404 or 504, got ${res.status}`);
        }
      });
  });

  afterEach(async () => {
    await app.close();
  });
});
