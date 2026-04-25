import type { z } from 'zod';

import {
  runtimeActionRequestSchema,
  runtimeActionResultSchema,
  runtimeActionSchema,
  runtimeCheckSchema,
  runtimeGroupSchema,
  runtimeStatSchema,
  runtimeStatusSchema,
} from '../api/runtimeSchemas';

export type RuntimeCheck = z.infer<typeof runtimeCheckSchema>;
export type RuntimeStat = z.infer<typeof runtimeStatSchema>;
export type RuntimeAction = z.infer<typeof runtimeActionSchema>;
export type RuntimeGroup = z.infer<typeof runtimeGroupSchema>;
export type RuntimeStatus = z.infer<typeof runtimeStatusSchema>;
export type RuntimeActionRequest = z.infer<typeof runtimeActionRequestSchema>;
export type RuntimeActionResult = z.infer<typeof runtimeActionResultSchema>;

export type RuntimeFeedback = {
  kind: 'idle' | 'pending' | 'success' | 'error';
  message: string;
};

export type RuntimeActivityEntry = {
  id: string;
  groupKey: string;
  groupTitle: string;
  actionLabel: string;
  status: 'success' | 'error';
  message: string;
  createdAt: string;
};
