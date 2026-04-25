import type { z } from 'zod';

import { itemDetailSchema } from '../api/itemDetailSchemas';

export type ItemDetailPayload = z.infer<typeof itemDetailSchema>;
