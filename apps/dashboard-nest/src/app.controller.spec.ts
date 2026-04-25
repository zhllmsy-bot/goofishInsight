import { AppController } from './app.controller';
import { AppService } from './app.service';

describe('AppController', () => {
  let appController: AppController;

  beforeEach(() => {
    appController = new AppController(new AppService());
  });

  it('returns health payload', () => {
    expect(appController.getHealth()).toEqual(
      expect.objectContaining({
        ok: true,
      }),
    );
  });
});
